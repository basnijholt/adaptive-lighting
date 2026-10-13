"""Native-group manual control behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    LightControlAttributes,
)
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_ADAPT_ONLY_ON_BARE_TURN_ON,
    CONF_AUTORESET_CONTROL,
    CONF_DETECT_NON_HA_CHANGES,
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MANUAL_CONTROL,
    CONF_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON,
    CONF_ONLY_ONCE,
    CONF_TAKE_OVER_CONTROL,
    CONF_TAKE_OVER_CONTROL_MODE,
    CONF_TURN_ON_LIGHTS,
    DOMAIN,
    SERVICE_APPLY,
    SERVICE_SET_MANUAL_CONTROL,
    TURNING_OFF_DELAY,
    TakeOverControlMode,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_LIGHTS,
    CONF_NAME,
)
from homeassistant.core import Context

from .support.adaptive import setup_switch, track_adaptive_light_calls
from .support.async_helpers import DelayBarrier
from .support.native_lights import (
    GROUP,
    LEFT,
    OFF_MEMBER,
    RIGHT,
    TARGET_KELVIN,
    RecordingGroup,
    RecordingMember,
)
from .support.native_scenarios import (
    activate_scene,
    add_subgroup,
    prepare_all_off,
    prepare_reported_members,
    scene_state,
    set_manual,
    setup_native_group,
    setup_reported_group,
    setup_scene_group,
    turn_on_member,
)


async def test_native_group_member_preserves_explicit_manual_brightness(hass):
    """Member activation keeps supplied brightness and repairs only colour."""
    setup = await setup_native_group(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value,
            CONF_ADAPT_ONLY_ON_BARE_TURN_ON: True,
            CONF_DETECT_NON_HA_CHANGES: True,
        },
    )
    await setup.switch.adapt_brightness_switch.async_turn_on()
    calls = track_adaptive_light_calls(hass)
    await turn_on_member(hass, **{ATTR_BRIGHTNESS: 37})
    assert setup.right.brightness == 37
    assert setup.right.physical_kelvin == TARGET_KELVIN
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == RIGHT
    assert ATTR_BRIGHTNESS not in calls[0]
    assert (
        LightControlAttributes.BRIGHTNESS
        in setup.switch.manager.get_manual_control_attributes(RIGHT)
    )
    assert setup.left.brightness == 80
    assert setup.off_member.is_on is False

    # Periodic native-group brightness would override the member's explicit
    # brightness. Keep that axis paused while allowing grouped colour updates.
    calls.clear()
    setup.group._attr_color_temp_kelvin = 4000
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == GROUP
    assert calls[0][ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN
    assert ATTR_BRIGHTNESS not in calls[0]
    assert setup.right.brightness == 37
    assert setup.left.brightness == 80
    assert setup.off_member.is_on is False


async def test_native_group_manual_control_reset_resumes_observed_members(hass):
    """A profile-wide manual reset clears member overrides as well as groups."""
    setup = await setup_native_group(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value,
            CONF_ADAPT_ONLY_ON_BARE_TURN_ON: True,
            CONF_DETECT_NON_HA_CHANGES: True,
        },
    )
    await setup.switch.adapt_brightness_switch.async_turn_on()
    await turn_on_member(hass, **{ATTR_BRIGHTNESS: 37})
    assert setup.right.brightness == 37
    assert (
        LightControlAttributes.BRIGHTNESS
        in setup.switch.manager.get_manual_control_attributes(RIGHT)
    )
    calls = track_adaptive_light_calls(hass)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {
            ATTR_ENTITY_ID: setup.switch.entity_id,
            CONF_MANUAL_CONTROL: False,
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert (
        setup.switch.manager.get_manual_control_attributes(RIGHT)
        == LightControlAttributes.NONE
    )
    assert setup.switch.manager.get_manual_control_attributes(GROUP).has_none()
    assert setup.right.brightness == 128
    assert any(
        call[ATTR_ENTITY_ID] == GROUP and call.get(ATTR_BRIGHTNESS) == 128
        for call in calls
    )


async def test_manual_colour_member_is_excluded_from_adaptive_group_correction(hass):
    """A bare all-member activation cannot broadcast over a manual colour."""
    setup = await setup_scene_group(hass)
    await prepare_all_off(setup, hass)
    setup.switch.manager.set_manual_control_attributes(
        RIGHT,
        LightControlAttributes.COLOR,
    )

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [LEFT, RIGHT, OFF_MEMBER]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.is_on for member in setup.members)
    assert setup.members[0].physical_kelvin == TARGET_KELVIN
    assert setup.members[1].physical_kelvin == 4000
    assert setup.members[2].physical_kelvin == TARGET_KELVIN
    assert len(setup.colour_commands) == 2, setup.commands
    assert {call["target"] for call in setup.colour_commands} == {LEFT, OFF_MEMBER}
    assert (
        LightControlAttributes.COLOR
        in setup.switch.manager.get_manual_control_attributes(RIGHT)
    )


async def test_brightness_only_manual_member_does_not_prevent_colour_group(hass):
    """Independent brightness control cannot unnecessarily split common colour."""
    setup = await setup_scene_group(hass)
    await setup.switch.adapt_brightness_switch.async_turn_on()
    await prepare_all_off(setup, hass)
    setup.switch._take_over_control_mode = TakeOverControlMode.PAUSE_CHANGED
    setup.switch.manager.set_manual_control_attributes(
        RIGHT,
        LightControlAttributes.BRIGHTNESS,
    )
    brightness = setup.members[1].brightness

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [LEFT, RIGHT, OFF_MEMBER]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    assert setup.members[1].brightness == brightness
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == GROUP
    assert ATTR_BRIGHTNESS not in setup.colour_commands[0]
    assert (
        LightControlAttributes.BRIGHTNESS
        in setup.switch.manager.get_manual_control_attributes(RIGHT)
    )


async def test_covered_scene_preserves_deferred_manual_control_marking(hass):
    """Skipping duplicate corrections must still establish manual scene control."""
    setup = await setup_scene_group(hass)
    await setup.switch.adapt_brightness_switch.async_turn_on()
    await prepare_all_off(setup, hass)
    setup.switch._take_over_control = True
    setup.switch._adapt_only_on_bare_turn_on = True
    brightness = {LEFT: 90, RIGHT: 140, OFF_MEMBER: 35}

    await activate_scene(
        hass,
        {eid: scene_state(3500, level) for eid, level in brightness.items()},
    )

    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert {
        member.entity_id: member.brightness for member in setup.members
    } == brightness
    assert all(
        setup.switch.manager.get_manual_control_attributes(member.entity_id)
        == LightControlAttributes.ALL
        for member in setup.members
    )
    setup.commands.clear()
    await setup.switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert setup.commands == []
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert {
        member.entity_id: member.brightness for member in setup.members
    } == brightness


@pytest.mark.parametrize("independent", ["none", "before", "after"])
async def test_subgroup_selective_pause_replaces_only_its_own_contribution(
    hass,
    independent,
):
    """Narrowing a subgroup pause retains an independently established axis."""
    setup = await setup_reported_group(
        hass,
        **{CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value},
    )
    subgroup = await add_subgroup(hass, setup)
    if independent == "before":
        await set_manual(hass, setup.switch, RIGHT, "color")
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    if independent == "after":
        await set_manual(hass, setup.switch, RIGHT, "color")
        assert (
            setup.switch.manager.get_manual_control_attributes(RIGHT)
            == LightControlAttributes.ALL
        )
    await set_manual(hass, setup.switch, subgroup.entity_id, "brightness")
    await hass.async_block_till_done()

    manager = setup.switch.manager
    expected = (
        LightControlAttributes.BRIGHTNESS
        if independent == "none"
        else LightControlAttributes.ALL
    )
    assert manager.get_manual_control_attributes(RIGHT) == expected
    assert (
        manager.get_manual_control_attributes(OFF_MEMBER)
        == LightControlAttributes.BRIGHTNESS
    )
    assert (
        manager.get_manual_control_attributes(subgroup.entity_id)
        == LightControlAttributes.BRIGHTNESS
    )
    assert (
        LightControlAttributes.COLOR
        in manager.get_adaption_control_attributes(setup.switch, GROUP)
    ) == (independent == "none")
    attrs = hass.states.get(setup.switch.entity_id).attributes
    assert set(attrs["manual_control_brightness"]) == {
        subgroup.entity_id,
        RIGHT,
        OFF_MEMBER,
    }
    assert attrs["manual_control_color"] == ([] if independent == "none" else [RIGHT])

    # Existing explicit group reset semantics clear both the group's pause and
    # independent overrides on its members, allowing requested group adaptation.
    await set_manual(hass, setup.switch, subgroup.entity_id, False)
    assert all(
        manager.get_manual_control_attributes(entity).has_none()
        for entity in (subgroup.entity_id, RIGHT, OFF_MEMBER)
    )


async def test_subgroup_replacement_preserves_a_tracked_member_manual_change(
    hass,
    freezer,
):
    """An ordinary light service adds a distinct source even during a group pause."""
    setup = await setup_reported_group(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value,
        },
    )
    # Arrange an established ON member outside the recent-OFF polling window.
    freezer.tick(TURNING_OFF_DELAY + 1)
    await prepare_reported_members(hass, setup, on=(True, True, False))
    subgroup = await add_subgroup(hass, setup)
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    # A service to an already-ON member records its independent colour override.
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: RIGHT, ATTR_COLOR_TEMP_KELVIN: 4500},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    await set_manual(hass, setup.switch, subgroup.entity_id, "brightness")

    manager = setup.switch.manager
    assert manager.get_manual_control_attributes(RIGHT) == LightControlAttributes.ALL
    assert (
        manager.get_manual_control_attributes(OFF_MEMBER)
        == LightControlAttributes.BRIGHTNESS
    )
    # Recording the independent colour change must not have copied inherited
    # brightness into the member's own override while the subgroup paused both.
    await set_manual(hass, setup.switch, subgroup.entity_id, "color")
    assert manager.get_manual_control_attributes(RIGHT) == LightControlAttributes.COLOR
    assert (
        manager.get_manual_control_attributes(OFF_MEMBER)
        == LightControlAttributes.COLOR
    )
    # Clearing the member must clear every source for that member, while a
    # sibling's subgroup pause remains active until the subgroup is reset.
    await set_manual(hass, setup.switch, RIGHT, False)
    assert manager.get_manual_control_attributes(RIGHT).has_none()
    assert (
        manager.get_manual_control_attributes(OFF_MEMBER)
        == LightControlAttributes.COLOR
    )
    await set_manual(hass, setup.switch, subgroup.entity_id, False)
    assert manager.get_manual_control_attributes(OFF_MEMBER).has_none()


async def test_subgroup_pause_keeps_member_auto_reset(hass):
    """Contributed member flags retain the profile's existing auto-reset timers."""
    setup = await setup_reported_group(hass, **{CONF_AUTORESET_CONTROL: 1})
    subgroup = await add_subgroup(hass, setup)
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    await set_manual(hass, setup.switch, subgroup.entity_id, "brightness")
    manager = setup.switch.manager
    timers = [
        manager.auto_reset_manual_control_timers[light] for light in (RIGHT, OFF_MEMBER)
    ]
    assert all(timer.is_running() for timer in timers)
    await asyncio.gather(*(timer.task for timer in timers))
    await hass.async_block_till_done()
    assert manager.get_manual_control_attributes(RIGHT).has_none()
    assert manager.get_manual_control_attributes(OFF_MEMBER).has_none()
    assert not manager.auto_reset_manual_control_timers
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: subgroup.entity_id},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members[1:])
    assert manager.get_manual_control_attributes(subgroup.entity_id).has_none()


@pytest.mark.parametrize(
    "reset",
    [
        "manual_service",
        "profile_cycle",
        "parent_group",
        "parent_after_members",
        "parent_with_member",
    ],
)
@pytest.mark.parametrize("explicit_subgroup_reset", [False, True])
async def test_profile_reset_clears_derived_subgroup_pause(
    hass,
    freezer,
    reset,
    explicit_subgroup_reset,
):
    """An empty profile pause list also means its scene subgroup can adapt again."""
    setup = await setup_reported_group(hass, **{CONF_TAKE_OVER_CONTROL: True})
    subgroup = await add_subgroup(hass, setup)
    await set_manual(hass, setup.switch, subgroup.entity_id, True)

    if reset == "manual_service":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MANUAL_CONTROL,
            {
                ATTR_ENTITY_ID: setup.switch.entity_id,
                CONF_MANUAL_CONTROL: False,
            },
            blocking=True,
        )
    elif reset == "profile_cycle":
        await setup.switch.async_turn_off()
        await setup.switch.async_turn_on(adapt_lights=False)
    else:
        if reset == "parent_after_members":
            for member in (RIGHT, OFF_MEMBER):
                await set_manual(hass, setup.switch, member, False)
            # Individual resets keep the subgroup's own pause until its group
            # or profile is reset, even when all contributions were removed.
            assert (
                setup.switch.manager.get_manual_control_attributes(
                    subgroup.entity_id,
                )
                == LightControlAttributes.ALL
            )
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MANUAL_CONTROL,
            {
                ATTR_ENTITY_ID: setup.switch.entity_id,
                CONF_LIGHTS: (
                    [GROUP, RIGHT] if reset == "parent_with_member" else [GROUP]
                ),
                CONF_MANUAL_CONTROL: False,
            },
            blocking=True,
        )
    await hass.async_block_till_done()

    manager = setup.switch.manager
    assert manager.get_manual_control_attributes(RIGHT).has_none()
    assert manager.get_manual_control_attributes(OFF_MEMBER).has_none()
    assert hass.states.get(setup.switch.entity_id).attributes["manual_control"] == []
    if explicit_subgroup_reset:
        # Positive control: explicitly naming the subgroup already releases it.
        await set_manual(hass, setup.switch, subgroup.entity_id, False)
        for member in setup.members[1:]:
            member.physical_kelvin = 4000
    freezer.tick(11)
    setup.commands.clear()
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: subgroup.entity_id},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(
        member.physical_kelvin == TARGET_KELVIN for member in setup.members[1:]
    ), setup.commands
    assert manager.get_manual_control_attributes(subgroup.entity_id).has_none()
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == subgroup.entity_id


@pytest.mark.parametrize("off_path", ["turn_off", "toggle", "report"])
@pytest.mark.parametrize("explicit_reset", [False, True])
async def test_subgroup_light_cycle_releases_pause(
    hass,
    freezer,
    off_path,
    explicit_reset,
):
    """A derived group's own OFF lifecycle releases its entire manual pause."""
    setup = await setup_reported_group(hass, **{CONF_TAKE_OVER_CONTROL: True})
    freezer.tick(11)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    subgroup = await add_subgroup(hass, setup)
    subgroup._attr_is_on = True
    subgroup.async_write_ha_state()
    await hass.async_block_till_done()
    await set_manual(hass, setup.switch, subgroup.entity_id, True)

    if off_path == "report":
        await subgroup.async_turn_off()
    else:
        await hass.services.async_call(
            "light",
            off_path,
            {ATTR_ENTITY_ID: subgroup.entity_id},
            blocking=True,
            context=Context(),
        )
    await hass.async_block_till_done()
    manager = setup.switch.manager
    assert all(not member.is_on for member in subgroup.members)
    assert manager.get_manual_control_attributes(RIGHT).has_none()
    assert manager.get_manual_control_attributes(OFF_MEMBER).has_none()
    if explicit_reset:
        # Control: a separate manual-reset service already releases this pause.
        await set_manual(hass, setup.switch, subgroup.entity_id, False)
    freezer.tick(11)
    setup.commands.clear()
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: subgroup.entity_id},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(
        member.physical_kelvin == TARGET_KELVIN for member in subgroup.members
    ), setup.commands
    assert manager.get_manual_control_attributes(subgroup.entity_id).has_none()
    assert hass.states.get(setup.switch.entity_id).attributes["manual_control"] == []


@pytest.mark.parametrize("release", ["profile", "group_off"])
async def test_derived_group_pause_remains_visible_after_individual_resets(
    hass,
    release,
):
    """Resetting every member does not hide a still-owned subgroup pause."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    await set_manual(hass, setup.switch, subgroup.entity_id, "color")
    for member in subgroup.members:
        await set_manual(hass, setup.switch, member.entity_id, False)
    await hass.async_block_till_done()

    state = hass.states.get(setup.switch.entity_id)
    assert state.attributes["manual_control"] == [subgroup.entity_id]
    assert state.attributes["manual_control_color"] == [subgroup.entity_id]
    assert state.attributes["manual_control_brightness"] == []

    if release == "profile":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MANUAL_CONTROL,
            {ATTR_ENTITY_ID: setup.switch.entity_id, CONF_MANUAL_CONTROL: False},
            blocking=True,
        )
    else:
        await hass.services.async_call(
            "light",
            "turn_off",
            {ATTR_ENTITY_ID: subgroup.entity_id},
            blocking=True,
        )
    await hass.async_block_till_done()
    assert hass.states.get(setup.switch.entity_id).attributes["manual_control"] == []


@pytest.mark.parametrize("release", ["reset", "expiry", "replacement"])
async def test_last_source_release_retires_former_command_member(hass, release):
    """Source ownership retains tracking only while its contribution is alive."""
    setup = await setup_reported_group(hass, **{CONF_AUTORESET_CONTROL: 1})
    subgroup = await add_subgroup(hass, setup)
    retired_member = setup.members[1]
    await set_manual(hass, setup.switch, subgroup.entity_id, "color")
    manager = setup.switch.manager
    await turn_on_member(hass)
    assert RIGHT in manager.turn_on_event
    setup.group.members.remove(retired_member)
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    assert RIGHT not in setup.switch._tracked_lights
    assert RIGHT in manager.lights
    assert manager.get_manual_control_attributes(RIGHT) == LightControlAttributes.COLOR

    if release == "reset":
        await set_manual(hass, setup.switch, subgroup.entity_id, False)
    elif release == "expiry":
        timers = list(manager.auto_reset_manual_control_timers.values())
        await asyncio.gather(*(timer.task for timer in timers))
    else:
        subgroup.members.remove(retired_member)
        subgroup.async_write_ha_state()
        await hass.async_block_till_done()
        await set_manual(hass, setup.switch, subgroup.entity_id, "color")
    await hass.async_block_till_done()

    assert RIGHT not in manager.lights
    assert RIGHT not in manager.auto_reset_manual_control_timers
    assert RIGHT not in manager.auto_reset_manual_control_times
    assert RIGHT not in manager.turn_on_event
    assert RIGHT not in manager.off_to_on_event
    assert RIGHT not in manager.last_service_data
    # Explicit resets may retain a NONE entry in the legacy raw direct mapping.
    assert manager.get_manual_control_attributes(RIGHT).has_none()
    entry = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if hass.data[DOMAIN][entry.entry_id]["switch"] is setup.switch
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not manager.lights


@pytest.mark.parametrize("release", ["reset", "off"])
async def test_last_direct_pause_release_retires_former_source_member(hass, release):
    """Final direct release ends tracking retained after derived ownership ended."""
    setup = await setup_reported_group(hass, **{CONF_AUTORESET_CONTROL: 60})
    subgroup = await add_subgroup(hass, setup)
    retired_member = setup.members[1]
    await set_manual(hass, setup.switch, subgroup.entity_id, "color")
    await set_manual(hass, setup.switch, RIGHT, "brightness")
    await turn_on_member(hass)
    setup.group.members.remove(retired_member)
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch.async_turn_off()
    await hass.async_block_till_done()
    manager = setup.switch.manager
    assert RIGHT not in setup.switch._tracked_lights
    assert RIGHT in manager.lights
    assert manager.get_manual_control_attributes(RIGHT) == (
        LightControlAttributes.BRIGHTNESS
    )

    if release == "reset":
        await set_manual(hass, setup.switch, RIGHT, False)
    else:
        await hass.services.async_call(
            "light",
            "turn_off",
            {ATTR_ENTITY_ID: RIGHT},
            blocking=True,
        )
    await hass.async_block_till_done()

    assert RIGHT not in manager.lights
    assert RIGHT not in manager.turn_on_event
    assert RIGHT not in manager.turn_off_event
    assert RIGHT not in manager.off_to_on_event
    assert RIGHT not in manager.auto_reset_manual_control_timers
    assert RIGHT not in manager.auto_reset_manual_control_times
    assert manager.manual_control[RIGHT] == LightControlAttributes.NONE
    entry = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if hass.data[DOMAIN][entry.entry_id]["switch"] is setup.switch
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not manager.lights


@pytest.mark.parametrize("release", ["reset", "off"])
async def test_unconfigured_apply_can_restart_after_tracking_retires(hass, release):
    """Explicit application registers one-shot targets again after OFF or reset."""
    setup = await setup_reported_group(hass)
    light = RecordingMember("light.explicit_apply_target", setup.commands)
    await hass.data[DATA_COMPONENT].async_add_entities([light])
    manager = setup.switch.manager
    data = {
        ATTR_ENTITY_ID: setup.switch.entity_id,
        CONF_LIGHTS: [light.entity_id],
        CONF_TURN_ON_LIGHTS: True,
    }
    await hass.services.async_call(DOMAIN, SERVICE_APPLY, data, blocking=True)
    await hass.async_block_till_done()
    assert light.is_on
    assert light.physical_kelvin == TARGET_KELVIN
    assert light.entity_id in manager.lights
    await set_manual(hass, setup.switch, light.entity_id, True)

    if release == "reset":
        await set_manual(hass, setup.switch, light.entity_id, False)
    else:
        await hass.services.async_call(
            "light",
            "turn_off",
            {ATTR_ENTITY_ID: light.entity_id},
            blocking=True,
        )
    await hass.async_block_till_done()
    assert light.entity_id not in manager.lights
    assert manager.manual_control[light.entity_id] == LightControlAttributes.NONE

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: light.entity_id, ATTR_COLOR_TEMP_KELVIN: 4200},
        blocking=True,
    )
    assert light.physical_kelvin == 4200
    await hass.services.async_call(DOMAIN, SERVICE_APPLY, data, blocking=True)
    await hass.async_block_till_done()
    assert light.entity_id in manager.lights
    assert light.physical_kelvin == TARGET_KELVIN


@pytest.mark.parametrize(
    "reset",
    ["manual_service", "profile_cycle", "unload", "parent_group", "parent_with_member"],
)
@pytest.mark.parametrize("relationship", ["same", "overlapping", "disjoint"])
async def test_profile_reset_preserves_another_profiles_subgroup_pause(
    hass,
    reset,
    relationship,
):
    """A profile reset releases its sources without erasing another profile's."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    foreign = RecordingMember("light.foreign_member", setup.commands)
    broad = RecordingGroup([*setup.members, foreign], setup.commands)
    broad.entity_id = "light.foreign_group"
    await hass.data[DATA_COMPONENT].async_add_entities([foreign, broad])
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "other_subgroup_owner",
            CONF_LIGHTS: [broad.entity_id],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_ONLY_ONCE: True,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_AUTORESET_CONTROL: 60,
        },
    )
    if relationship == "same":
        other_subgroup = subgroup
    else:
        members = (
            [setup.members[2], foreign] if relationship == "overlapping" else [foreign]
        )
        other_subgroup = RecordingGroup(members, setup.commands)
        other_subgroup.entity_id = "light.foreign_subset"
        await hass.data[DATA_COMPONENT].async_add_entities([other_subgroup])
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    await set_manual(hass, other, other_subgroup.entity_id, "color")
    await set_manual(hass, other, foreign.entity_id, "brightness")
    await set_manual(hass, other, RIGHT, "brightness")
    manager = setup.switch.manager
    preserved_timers = {
        member.entity_id: manager.auto_reset_manual_control_timers[member.entity_id]
        for member in [*other_subgroup.members, foreign]
        if not (reset == "parent_with_member" and member.entity_id == RIGHT)
    }

    if reset == "manual_service":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MANUAL_CONTROL,
            {
                ATTR_ENTITY_ID: setup.switch.entity_id,
                CONF_MANUAL_CONTROL: False,
            },
            blocking=True,
        )
    elif reset == "profile_cycle":
        await setup.switch.async_turn_off()
        await setup.switch.async_turn_on(adapt_lights=False)
    elif reset == "unload":
        entry = next(
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if hass.data[DOMAIN][entry.entry_id]["switch"] is setup.switch
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
    else:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MANUAL_CONTROL,
            {
                ATTR_ENTITY_ID: setup.switch.entity_id,
                CONF_LIGHTS: (
                    [GROUP, RIGHT] if reset == "parent_with_member" else [GROUP]
                ),
                CONF_MANUAL_CONTROL: False,
            },
            blocking=True,
        )
    await hass.async_block_till_done()

    assert manager.get_manual_control_attributes(other_subgroup.entity_id) == (
        LightControlAttributes.COLOR
    )
    assert manager.get_manual_control_attributes(subgroup.entity_id) == (
        LightControlAttributes.COLOR
        if relationship == "same"
        else LightControlAttributes.NONE
    )
    expected_right = (
        LightControlAttributes.COLOR
        if relationship == "same" and reset != "parent_with_member"
        else LightControlAttributes.NONE
    )
    if reset == "unload":
        expected_right |= LightControlAttributes.BRIGHTNESS
    assert manager.get_manual_control_attributes(RIGHT) == expected_right
    assert manager.get_manual_control_attributes(OFF_MEMBER) == (
        LightControlAttributes.NONE
        if relationship == "disjoint"
        else LightControlAttributes.COLOR
    )
    assert manager.get_manual_control_attributes(foreign.entity_id) == (
        LightControlAttributes.BRIGHTNESS
        if relationship == "same"
        else LightControlAttributes.ALL
    )
    # Direct overrides retain their established entity-global reset boundary.
    assert manager.manual_control[RIGHT] == (
        LightControlAttributes.BRIGHTNESS
        if reset == "unload"
        else LightControlAttributes.NONE
    )
    assert (
        manager.manual_control[foreign.entity_id] == LightControlAttributes.BRIGHTNESS
    )
    for entity, timer in preserved_timers.items():
        assert manager.auto_reset_manual_control_timers[entity] is timer
        assert timer.is_running()
    assert other.is_on


async def test_profile_reset_preserves_independent_direct_subgroup_pause(hass):
    """Releasing a derived pause leaves another profile's direct group flag intact."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "direct_subgroup_owner",
            CONF_LIGHTS: [subgroup.entity_id],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_ONLY_ONCE: True,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_AUTORESET_CONTROL: 60,
        },
    )
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    await set_manual(hass, other, subgroup.entity_id, "color")
    manager = setup.switch.manager
    timer = manager.auto_reset_manual_control_timers[subgroup.entity_id]

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {ATTR_ENTITY_ID: setup.switch.entity_id, CONF_MANUAL_CONTROL: False},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert manager.get_manual_control_attributes(subgroup.entity_id) == (
        LightControlAttributes.COLOR
    )

    assert manager.manual_control[subgroup.entity_id] == LightControlAttributes.COLOR
    assert manager.get_manual_control_attributes(RIGHT).has_none()
    assert manager.get_manual_control_attributes(OFF_MEMBER).has_none()
    assert manager.auto_reset_manual_control_timers[subgroup.entity_id] is timer
    assert timer.is_running()
    assert other.is_on


@pytest.mark.parametrize("retirement_enabled", [False, True])
@pytest.mark.parametrize("release", ["off", "unload"])
async def test_source_release_preserves_an_explicit_unconfigured_direct_pause(
    hass,
    monkeypatch,
    retirement_enabled,
    release,
):
    """Source retirement cannot erase an independent explicit manual override."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "explicit_direct_owner",
            CONF_LIGHTS: [LEFT],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_ONLY_ONCE: True,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    await set_manual(hass, other, subgroup.entity_id, "color")
    manager = setup.switch.manager
    assert manager.manual_control[subgroup.entity_id] == LightControlAttributes.COLOR
    if not retirement_enabled:
        # Control: preserve the former clear_owner path without reconciliation.
        monkeypatch.setattr(
            manager,
            "_unowned_entities",
            lambda *_args, **_kwargs: set(),
        )

    if release == "off":
        await setup.switch.async_turn_off()
    else:
        entry = next(
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if hass.data[DOMAIN][entry.entry_id]["switch"] is setup.switch
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert manager.get_manual_control_attributes(subgroup.entity_id) == (
        LightControlAttributes.COLOR
    )
    assert other.is_on

    await hass.services.async_call(
        "light",
        "turn_off",
        {ATTR_ENTITY_ID: subgroup.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert manager.get_manual_control_attributes(subgroup.entity_id).has_none()
    assert manager.manual_control[subgroup.entity_id] == LightControlAttributes.NONE
    assert subgroup.entity_id not in manager.lifecycle_entities()


async def test_unloading_source_owner_retires_derived_group_history(hass):
    """The source reset itself cleans a derived target with no remaining owner."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: subgroup.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    manager = setup.switch.manager
    assert subgroup.entity_id in manager.turn_on_event
    entry = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if hass.data[DOMAIN][entry.entry_id]["switch"] is setup.switch
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert subgroup.entity_id not in manager.lifecycle_entities()
    assert subgroup.entity_id not in manager.turn_on_event
    assert subgroup.entity_id not in manager.off_to_on_event
    assert subgroup.entity_id not in manager.auto_reset_manual_control_timers
    assert manager.get_manual_control_attributes(subgroup.entity_id).has_none()


async def test_explicit_subgroup_reset_clears_every_owners_source(hass):
    """An explicitly named subgroup retains the existing global reset contract."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "same_group_owner",
            CONF_LIGHTS: [GROUP],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_ONLY_ONCE: True,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_AUTORESET_CONTROL: 60,
        },
    )
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    await set_manual(hass, other, subgroup.entity_id, "color")

    await set_manual(hass, setup.switch, subgroup.entity_id, False)
    await hass.async_block_till_done()

    manager = setup.switch.manager
    assert all(
        manager.get_manual_control_attributes(entity).has_none()
        for entity in (subgroup.entity_id, RIGHT, OFF_MEMBER)
    )
    assert not manager.auto_reset_manual_control_timers


@pytest.mark.parametrize("detect_changes", [False, True])
@pytest.mark.parametrize("external_pause", [False, True])
async def test_explicit_external_member_pause_survives_periodic_group(
    hass,
    freezer,
    detect_changes,
    external_pause,
):
    """The opt-in pause survives periodic broadcasts; the default stays unpaused."""
    setup = await setup_reported_group(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_DETECT_NON_HA_CHANGES: detect_changes,
            CONF_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON: external_pause,
        },
    )
    freezer.tick(11)
    right = setup.members[1]
    right.async_set_context(Context())
    right._attr_is_on = True
    right.async_write_ha_state()
    await hass.async_block_till_done()
    assert right.physical_kelvin == (
        TARGET_KELVIN if detect_changes and not external_pause else 4000
    )
    assert (
        bool(setup.switch.manager.get_manual_control_attributes(RIGHT))
        is external_pause
    )

    await setup.switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert right.physical_kelvin == (4000 if external_pause else TARGET_KELVIN)
    if external_pause:
        assert setup.commands == []
        await set_manual(hass, setup.switch, RIGHT, False)
        await setup.switch._async_update_at_interval_action()
        await hass.async_block_till_done()
        assert right.physical_kelvin == TARGET_KELVIN


@pytest.mark.parametrize("derived", [False, True])
async def test_group_brightness_respects_late_member_manual_control(
    hass,
    monkeypatch,
    derived,
):
    """A queued group brightness must not overwrite a newly paused member axis."""
    setup = await setup_reported_group(
        hass,
        **{
            CONF_ADAPT_DELAY: 1,
            CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value,
        },
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    target = (await add_subgroup(hass, setup)).entity_id if derived else GROUP
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    turning_on = hass.async_create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: target},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1
        await set_manual(hass, setup.switch, RIGHT, "brightness")
    finally:
        delay.release.set()
        await turning_on
    await hass.async_block_till_done()

    assert setup.members[1].brightness == 110, setup.commands
    assert setup.members[1].physical_kelvin == TARGET_KELVIN
    assert not any(
        call["target"] in (target, RIGHT) and ATTR_BRIGHTNESS in call
        for call in setup.commands
    ), setup.commands


@pytest.mark.parametrize("elapsed", [0, 11])
async def test_derived_group_manual_control_blocks_adaptive_member_fallback(
    hass,
    freezer,
    elapsed,
):
    """Pausing the explicitly targeted subgroup also pauses its adaptive repair."""
    setup = await setup_reported_group(hass)
    subgroup = await add_subgroup(hass, setup)
    await set_manual(hass, setup.switch, subgroup.entity_id, True)
    freezer.tick(elapsed)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: subgroup.entity_id},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.is_on for member in setup.members[1:])
    assert [member.physical_kelvin for member in setup.members] == [4000] * 3
    assert setup.colour_commands == [], setup.commands

    if elapsed:
        setup.commands.clear()
        await setup.switch._async_update_at_interval_action()
        await hass.async_block_till_done()
        assert setup.colour_commands == [], setup.commands
        assert [member.physical_kelvin for member in setup.members] == [4000] * 3

        await set_manual(hass, setup.switch, subgroup.entity_id, False)
        await hass.async_block_till_done()
        assert all(
            setup.switch.manager.get_manual_control_attributes(
                member.entity_id,
            ).has_none()
            for member in setup.members[1:]
        )
        assert setup.members[0].physical_kelvin == 4000
        assert all(
            member.physical_kelvin == TARGET_KELVIN for member in setup.members[1:]
        )
        assert [call["target"] for call in setup.colour_commands] == [
            subgroup.entity_id,
        ]
