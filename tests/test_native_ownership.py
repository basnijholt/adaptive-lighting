"""Native-group ownership behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    LightControlAttributes,
)
from homeassistant.components.adaptive_lighting.const import (
    CONF_AUTORESET_CONTROL,
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MANUAL_CONTROL,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_COLOR_TEMP,
    CONF_ONLY_ONCE,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
    DOMAIN,
    SERVICE_SET_MANUAL_CONTROL,
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
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context, Event, HomeAssistant, State

from .support.adaptive import setup_switch, track_adaptive_light_calls
from .support.async_helpers import DelayBarrier
from .support.native_lights import (
    GROUP,
    LEFT,
    RIGHT,
    TARGET_KELVIN,
    RecordingGroup,
    RecordingMember,
)
from .support.native_scenarios import (
    set_manual,
    setup_native_group,
    setup_reported_group,
    setup_scene_group,
    turn_on_member,
)


@pytest.mark.parametrize("unload", [False, True])
@pytest.mark.parametrize("owner_enabled", [False, True])
async def test_retiring_command_group_preserves_foreign_derived_pause(
    hass,
    unload,
    owner_enabled,
):
    """Retiring a configured group cannot erase a surviving profile's source."""
    setup = await setup_reported_group(hass)
    foreign = RecordingMember("light.foreign_member", setup.commands)
    broad = RecordingGroup([*setup.members, foreign], setup.commands)
    broad.entity_id = "light.broader_group"
    await hass.data[DATA_COMPONENT].async_add_entities([foreign, broad])
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "broader_owner",
            CONF_LIGHTS: [broad.entity_id],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_ONLY_ONCE: True,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_AUTORESET_CONTROL: 60,
        },
    )
    if not owner_enabled:
        await other.async_turn_off()
    await set_manual(hass, other, GROUP, "color")
    manager = setup.switch.manager
    retained = [GROUP, *(member.entity_id for member in setup.members)]
    assert all(
        manager.get_manual_control_attributes(entity) == LightControlAttributes.COLOR
        for entity in retained
    )
    timers = {
        member.entity_id: manager.auto_reset_manual_control_timers[member.entity_id]
        for member in setup.members
    }

    if unload:
        entry = next(
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if hass.data[DOMAIN][entry.entry_id]["switch"] is setup.switch
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert other.is_on is owner_enabled
    assert all(
        manager.get_manual_control_attributes(entity) == LightControlAttributes.COLOR
        for entity in retained
    )
    for member, timer in timers.items():
        assert manager.auto_reset_manual_control_timers[member] is timer
        assert timer.is_running()


async def test_native_group_member_removal_preserves_other_profile(hass):
    """Retiring group membership cannot retire another profile's direct light."""
    setup = await setup_native_group(hass)
    _, other_switch = await setup_switch(
        hass,
        {
            CONF_NAME: "direct_member_owner",
            CONF_LIGHTS: [RIGHT],
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_COLOR_TEMP: TARGET_KELVIN,
            CONF_MAX_COLOR_TEMP: TARGET_KELVIN,
            CONF_SLEEP_COLOR_TEMP: TARGET_KELVIN,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_SKIP_REDUNDANT_COMMANDS: True,
        },
    )
    await other_switch.adapt_brightness_switch.async_turn_off()
    setup.group.members.remove(setup.right)
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    calls = track_adaptive_light_calls(hass)
    await turn_on_member(hass)
    assert setup.right.physical_kelvin == TARGET_KELVIN
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == RIGHT
    assert setup.switch.lights == [GROUP]
    assert other_switch.lights == [RIGHT]
    assert setup.off_member.is_on is False


async def test_native_group_with_two_colour_owners_does_not_choose_one(hass):
    """Competing profiles cannot be resolved by arbitrary group-owner iteration."""
    setup = await setup_scene_group(hass)
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "conflicting_native_colour_owner",
            CONF_LIGHTS: [GROUP],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_COLOR_TEMP: 4500,
            CONF_MAX_COLOR_TEMP: 4500,
            CONF_SLEEP_COLOR_TEMP: 4500,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    await other.adapt_brightness_switch.async_turn_off()
    await hass.async_block_till_done()
    assert setup.switch.is_on
    assert other.is_on
    assert setup.switch.adapt_color_switch.is_on
    assert other.adapt_color_switch.is_on
    setup.commands.clear()

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [member.entity_id for member in setup.members]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.is_on for member in setup.members)
    # Existing per-member conflict handling is outside this optimization. Only
    # assert that it does not invent one arbitrarily owned group correction.
    assert not any(
        call["target"] == GROUP for call in setup.colour_commands
    ), setup.commands


@pytest.mark.parametrize("reset_action", ["disable", "enable", "sleep", "manual_reset"])
async def test_native_profile_reset_preserves_another_owner_member_split(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    reset_action: str,
) -> None:
    """An observed member's colour phase belongs to its still-enabled owner."""
    setup = await setup_native_group(hass)
    if reset_action == "enable":
        await setup.switch.async_turn_off()
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "direct_member_owner",
            CONF_LIGHTS: [LEFT],
            CONF_TAKE_OVER_CONTROL: False,
            CONF_ONLY_ONCE: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_SEND_SPLIT_DELAY: 1234,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    delay = DelayBarrier(monkeypatch, other, "_execute_adaptation_calls")
    calls = track_adaptive_light_calls(hass)
    adapting = hass.async_create_task(
        other._adapt_light(LEFT, other.create_context("test"), 0, force=True),
    )
    await asyncio.wait_for(delay.entered.wait(), 2)
    assert delay.delay == 1.234
    assert len(calls) == 1
    assert ATTR_BRIGHTNESS in calls[0]
    try:
        if reset_action == "disable":
            await setup.switch.async_turn_off()
        elif reset_action == "enable":
            await setup.switch.async_turn_on(adapt_lights=False)
        elif reset_action == "sleep":
            await setup.switch._sleep_mode_switch_state_event_action(
                Event(
                    "state_changed",
                    {
                        "entity_id": setup.switch.sleep_mode_switch.entity_id,
                        "old_state": State(
                            setup.switch.sleep_mode_switch.entity_id,
                            STATE_OFF,
                        ),
                        "new_state": State(
                            setup.switch.sleep_mode_switch.entity_id,
                            STATE_ON,
                        ),
                    },
                ),
            )
        else:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_MANUAL_CONTROL,
                {
                    ATTR_ENTITY_ID: setup.switch.entity_id,
                    CONF_LIGHTS: [GROUP],
                    CONF_MANUAL_CONTROL: False,
                },
                blocking=True,
            )
    finally:
        delay.release.set()
        await adapting
    await hass.async_block_till_done()

    member_calls = [call for call in calls if call[ATTR_ENTITY_ID] == LEFT]
    assert other.is_on
    assert len(member_calls) == 2, calls
    assert ATTR_COLOR_TEMP_KELVIN in member_calls[-1]
    assert not setup.switch.manager.adaptation_task_owners


async def test_disabling_native_profile_still_cancels_its_own_member_split(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserving foreign tasks must not let the disabled profile finish its own."""
    setup = await setup_native_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: True, CONF_SEND_SPLIT_DELAY: 1234},
    )
    _, other = await setup_switch(
        hass,
        {CONF_NAME: "other_member_owner", CONF_LIGHTS: [LEFT], CONF_ONLY_ONCE: True},
    )
    await setup.switch.adapt_brightness_switch.async_turn_on()
    delay = DelayBarrier(monkeypatch, setup.switch, "_execute_adaptation_calls")
    calls = track_adaptive_light_calls(hass)
    adapting = hass.async_create_task(
        setup.switch._adapt_light(
            LEFT,
            setup.switch.create_context("test"),
            0,
            force=True,
        ),
    )
    await asyncio.wait_for(delay.entered.wait(), 2)
    assert delay.delay == 1.234
    try:
        await setup.switch.async_turn_off()
    finally:
        delay.release.set()
        await adapting
    await hass.async_block_till_done()

    assert other.is_on
    assert len(calls) == 1, calls
    assert ATTR_BRIGHTNESS in calls[0]
    assert not setup.switch.manager.adaptation_task_owners


@pytest.mark.parametrize("other_owner", [False, True])
async def test_member_retirement_cancels_only_retiring_owner_split(
    hass,
    monkeypatch,
    other_owner,
):
    """Another profile retaining the member cannot keep the retired colour task alive."""
    setup = await setup_native_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: True, CONF_SEND_SPLIT_DELAY: 1234},
    )
    if other_owner:
        _, other = await setup_switch(
            hass,
            {
                CONF_NAME: "other_member_owner",
                CONF_LIGHTS: [RIGHT],
                CONF_ONLY_ONCE: True,
            },
        )
        await other.async_turn_off()
    await setup.switch.adapt_brightness_switch.async_turn_on()
    delay = DelayBarrier(monkeypatch, setup.switch, "_execute_adaptation_calls")
    calls = track_adaptive_light_calls(hass)
    turning_on = hass.async_create_task(turn_on_member(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1.234
        retired = asyncio.Event()
        original_expand = setup.switch._expand_light_groups

        def observe_retirement():
            original_expand()
            if RIGHT not in setup.switch._tracked_lights:
                retired.set()

        monkeypatch.setattr(setup.switch, "_expand_light_groups", observe_retirement)
        setup.group.members.remove(setup.right)
        setup.group.async_write_ha_state()
        await asyncio.wait_for(retired.wait(), 2)
        assert RIGHT not in setup.switch._tracked_lights
        if other_owner:
            # Shared records are still useful to the remaining owner.
            assert RIGHT in other._tracked_lights
            assert RIGHT in setup.switch.manager.lights
            assert RIGHT in setup.switch.manager.last_service_data
    finally:
        delay.release.set()
        await turning_on
    await hass.async_block_till_done()
    assert len(calls) == 1, calls
    assert ATTR_BRIGHTNESS in calls[0]
    assert not setup.switch.manager.adaptation_task_owners


async def test_member_retirement_preserves_remaining_owner_split(hass, monkeypatch):
    """Retiring the observer leaves an independent active owner's delayed task intact."""
    setup = await setup_native_group(hass)
    await setup.switch.async_turn_off()
    _, other = await setup_switch(
        hass,
        {
            CONF_NAME: "remaining_member_owner",
            CONF_LIGHTS: [RIGHT],
            CONF_ONLY_ONCE: True,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_SEND_SPLIT_DELAY: 1234,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    delay = DelayBarrier(monkeypatch, other, "_execute_adaptation_calls")
    calls = track_adaptive_light_calls(hass)
    turning_on = hass.async_create_task(turn_on_member(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1.234
        retired = asyncio.Event()
        original_expand = setup.switch._expand_light_groups

        def observe_retirement():
            original_expand()
            if RIGHT not in setup.switch._tracked_lights:
                retired.set()

        monkeypatch.setattr(setup.switch, "_expand_light_groups", observe_retirement)
        setup.group.members.remove(setup.right)
        setup.group.async_write_ha_state()
        await asyncio.wait_for(retired.wait(), 2)
        assert RIGHT not in setup.switch._tracked_lights
        assert RIGHT in other._tracked_lights
        assert other in setup.switch.manager.adaptation_task_owners.values()
    finally:
        delay.release.set()
        await turning_on
    await hass.async_block_till_done()

    assert len(calls) == 2, calls
    assert ATTR_BRIGHTNESS in calls[0]
    assert ATTR_COLOR_TEMP_KELVIN in calls[1]
    assert not setup.switch.manager.adaptation_task_owners
