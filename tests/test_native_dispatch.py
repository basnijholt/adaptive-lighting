"""Native-group dispatch behavior at HA and device boundaries."""

# pylint: disable=protected-access
from contextlib import nullcontext

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_INITIAL_TRANSITION,
    CONF_INTERCEPT,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_ONLY_ONCE,
    CONF_SLEEP_COLOR_TEMP,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    Profile,
)
from homeassistant.components.light.const import DATA_COMPONENT, DATA_PROFILES
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_LIGHTS,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.color import color_temperature_to_rgbww

from .support.adaptive import setup_switch
from .support.native_lights import (
    GROUP,
    LEFT,
    OFF_MEMBER,
    RIGHT,
    TARGET_KELVIN,
    RecordingMember,
)
from .support.native_scenarios import (
    activate_scene,
    prepare_reported_members,
    scene_state,
    setup_reported_group,
    setup_scene_group,
)


async def test_unavailable_native_group_falls_back_to_available_members(hass):
    """An unavailable group cannot silently swallow its available members' colour."""
    setup = await setup_scene_group(hass)
    setup.group._attr_available = False
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.get(GROUP).state == STATE_UNAVAILABLE
    assert all(member.available for member in setup.members)
    setup.commands.clear()

    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in setup.members},
    )

    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert len(setup.colour_commands) == 3, setup.commands
    assert {call["target"] for call in setup.colour_commands} == {
        LEFT,
        RIGHT,
        OFF_MEMBER,
    }
    assert not any(call["target"] == GROUP for call in setup.commands)


async def test_native_scene_member_ct_range_uses_individual_clamping(hass):
    """Different per-member adaptive clamps prevent an incorrect common colour."""
    setup = await setup_scene_group(hass)
    setup.members[1]._attr_max_color_temp_kelvin = 2800
    setup.members[1].async_write_ha_state()
    await hass.async_block_till_done()
    setup.commands.clear()

    await activate_scene(
        hass,
        {
            member.entity_id: {"state": STATE_ON, "brightness": 100}
            for member in setup.members
        },
        transition=2,
    )

    assert len(setup.colour_commands) == 3, setup.commands
    assert {call["target"] for call in setup.colour_commands} == {
        member.entity_id for member in setup.members
    }
    assert not any(call["target"] == GROUP for call in setup.commands)
    assert [member.physical_kelvin for member in setup.members] == [3000, 2800, 3000]
    assert all(member.brightness == 100 for member in setup.members)
    assert all(call[ATTR_TRANSITION] == 2 for call in setup.colour_commands)


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("failed_index", [0, 1], ids=["failed-first", "healthy-first"])
async def test_healthy_target_survives_sibling_device_failure(
    hass: HomeAssistant,
    planner_enabled: bool,
    failed_index: int,
):
    """A sibling failure cannot suppress accepted power, brightness, or colour."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    message = "device unreachable"
    device_error = HomeAssistantError(message)

    async def broken():
        raise device_error

    setup.members[failed_index].before_turn_on = broken
    failed = setup.members[failed_index]
    attempts_before = len(failed.attempts)
    with pytest.raises(HomeAssistantError, match="device unreachable") as error:
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                ATTR_ENTITY_ID: [LEFT, RIGHT],
                ATTR_BRIGHTNESS: 150,
                ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
                ATTR_TRANSITION: 3,
            },
            blocking=True,
            context=Context(),
        )
    await hass.async_block_till_done()
    assert error.value is device_error

    assert len(failed.attempts) == attempts_before + 1, failed.attempts
    assert not failed.is_on
    assert failed.brightness == (80, 110)[failed_index]
    assert failed.physical_kelvin == 4000
    assert not any(call["target"] == failed.entity_id for call in setup.commands)

    healthy = setup.members[1 - failed_index]
    assert healthy.is_on, setup.commands
    assert healthy.brightness == 150, setup.commands
    assert healthy.physical_kelvin == TARGET_KELVIN, setup.commands
    healthy_commands = [
        call for call in setup.commands if call["target"] == healthy.entity_id
    ]
    # Without the planner, the original combined command is followed by the
    # existing OFF-to-ON correction. With it, power and colour are split.
    assert len(healthy_commands) == 2, setup.commands
    assert healthy_commands[0][ATTR_TRANSITION] == 3
    assert any(
        call.get(ATTR_COLOR_TEMP_KELVIN) == TARGET_KELVIN
        and call.get(ATTR_TRANSITION) == 3
        for call in healthy_commands
    ), setup.commands


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("failed_index", [0, 1], ids=["failed-first", "healthy-first"])
async def test_healthy_colour_survives_sibling_colour_failure(
    hass: HomeAssistant,
    planner_enabled: bool,
    failed_index: int,
):
    """A colour-only device failure cannot discard a healthy target's colour."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    message = "colour device unreachable"
    device_error = HomeAssistantError(message)

    async def broken():
        raise device_error

    setup.members[failed_index].before_turn_on = broken
    failed = setup.members[failed_index]
    attempts_before = len(failed.attempts)
    with pytest.raises(HomeAssistantError, match="colour device unreachable") as error:
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                ATTR_ENTITY_ID: [LEFT, RIGHT],
                ATTR_COLOR_TEMP_KELVIN: 3500,
                ATTR_TRANSITION: 3,
            },
            blocking=True,
            context=Context(),
        )
    await hass.async_block_till_done()
    assert error.value is device_error

    assert len(failed.attempts) == attempts_before + 1, failed.attempts
    assert failed.is_on
    assert failed.brightness == (80, 110)[failed_index]
    assert failed.physical_kelvin == 4000
    assert not any(call["target"] == failed.entity_id for call in setup.commands)

    healthy = setup.members[1 - failed_index]
    assert healthy.physical_kelvin == 3500, setup.commands
    healthy_commands = [
        call for call in setup.colour_commands if call["target"] == healthy.entity_id
    ]
    assert len(healthy_commands) == 1, setup.commands
    assert healthy_commands[0][ATTR_TRANSITION] == 3


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("transition", [None, 4])
async def test_default_colour_is_not_sent_twice(
    hass: HomeAssistant,
    planner_enabled: bool,
    transition: int | None,
):
    """A bare ON must apply each light's default colour and transition once."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    for member in setup.members:
        name = f"{member.entity_id}.default"
        hass.data[DATA_PROFILES].data[name] = Profile(
            name,
            0.3,
            0.3,
            None,
            transition,
        )

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [member.entity_id for member in setup.members]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert len(setup.colour_commands) == 3, setup.commands
    assert {call["target"] for call in setup.colour_commands} == {
        member.entity_id for member in setup.members
    }
    assert all(
        call.get(ATTR_TRANSITION) == transition for call in setup.colour_commands
    ), setup.commands


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("transition", [0, 3])
async def test_nonoptimistic_rgbww_preserves_requested_brightness(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    planner_enabled: bool,
    transition: int,
):
    """Kelvin conversion uses requested brightness before a device report arrives."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    member = setup.members[0]
    member._attr_supported_color_modes = {ColorMode.RGBWW}
    member._attr_color_mode = ColorMode.RGBWW
    member._attr_rgbww_color = (0, 0, 0, 40, 40)
    member.async_write_ha_state()
    await hass.async_block_till_done()
    device_calls = []

    async def record_without_immediate_state_report(**kwargs):
        device_calls.append(kwargs)

    monkeypatch.setattr(member, "async_turn_on", record_without_immediate_state_report)
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: member.entity_id,
            ATTR_BRIGHTNESS: 150,
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: transition,
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    expected = color_temperature_to_rgbww(3500, 150, 2000, 6500)
    colour_calls = [data for data in device_calls if ATTR_RGBWW_COLOR in data]
    assert [data[ATTR_RGBWW_COLOR] for data in colour_calls] == [expected], device_calls
    assert all(data[ATTR_TRANSITION] == transition for data in colour_calls)


@pytest.mark.parametrize("explicit_colour", [False, True])
async def test_bare_scene_preserves_healthy_colour_when_sibling_fails(
    hass,
    explicit_colour,
):
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    error = HomeAssistantError("unreachable member")

    async def broken():
        raise error

    setup.members[0].before_turn_on = broken
    failed = setup.members[0]
    attempts_before = len(failed.attempts)
    entities = {
        member.entity_id: {
            "state": STATE_ON,
            ATTR_BRIGHTNESS: 150,
            **({ATTR_COLOR_TEMP_KELVIN: 3000} if explicit_colour else {}),
        }
        for member in setup.members
    }
    with pytest.raises(HomeAssistantError, match="unreachable member") as exc_info:
        await hass.services.async_call(
            "scene",
            "apply",
            {"entities": entities},
            blocking=True,
            context=Context(),
        )
    assert exc_info.value is error
    await hass.async_block_till_done()
    assert len(failed.attempts) == attempts_before + 1, failed.attempts
    assert not failed.is_on
    assert failed.brightness == 80
    assert failed.physical_kelvin == 4000
    assert not any(call["target"] == failed.entity_id for call in setup.commands)
    assert [member.physical_kelvin for member in setup.members[1:]] == [
        3000,
        3000,
    ], setup.commands
    for member in setup.members[1:]:
        assert (
            len(
                [call for call in setup.commands if call["target"] == member.entity_id],
            )
            == 2
        ), setup.commands


@pytest.mark.parametrize("unmanaged_fails", [False, True])
async def test_mixed_target_failure_preserves_healthy_adaptive_colour(
    hass,
    unmanaged_fails,
):
    """An unrelated failing target cannot suppress healthy native-member colour."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    unmanaged = RecordingMember("light.unmanaged_review", setup.commands)
    await hass.data[DATA_COMPONENT].async_add_entities([unmanaged])
    error = HomeAssistantError("unmanaged member unreachable")

    if unmanaged_fails:

        async def broken():
            raise error

        unmanaged.before_turn_on = broken
    entities = [member.entity_id for member in setup.members] + [unmanaged.entity_id]
    expectation = (
        pytest.raises(HomeAssistantError, match="unmanaged member unreachable")
        if unmanaged_fails
        else nullcontext()
    )
    with expectation as exc_info:
        await hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: entities, ATTR_BRIGHTNESS: 150},
            blocking=True,
            context=Context(),
        )
    if unmanaged_fails:
        assert exc_info.value is error
    await hass.async_block_till_done()
    assert len(unmanaged.attempts) == 1, unmanaged.attempts
    assert unmanaged.is_on == (not unmanaged_fails)
    assert unmanaged.brightness == (110 if unmanaged_fails else 150)
    assert unmanaged.physical_kelvin == 4000
    assert len(
        [call for call in setup.commands if call["target"] == unmanaged.entity_id],
    ) == (0 if unmanaged_fails else 1)
    assert [member.physical_kelvin for member in setup.members] == [
        3000,
    ] * 3, setup.commands
    assert [member.brightness for member in setup.members] == [150] * 3, setup.commands
    assert len(setup.commands) == (4 if unmanaged_fails else 5), setup.commands


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_unrelated_direct_profile_does_not_leak_brightness(hass, planner_enabled):
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    direct = RecordingMember("light.aaa_direct_review", setup.commands)
    await hass.data[DATA_COMPONENT].async_add_entities([direct])
    await setup_switch(
        hass,
        {
            CONF_NAME: "direct_review",
            CONF_LIGHTS: [direct.entity_id],
            CONF_INTERCEPT: True,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_BRIGHTNESS: 20,
            CONF_MAX_BRIGHTNESS: 20,
            CONF_MIN_COLOR_TEMP: 5000,
            CONF_MAX_COLOR_TEMP: 5000,
            CONF_SLEEP_COLOR_TEMP: 5000,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    setup.switch.manager.native_groups.disabled = not planner_enabled
    setup.commands.clear()
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: [
                direct.entity_id,
                *[member.entity_id for member in setup.members],
            ],
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert direct.brightness == 51, setup.commands
    assert [member.brightness for member in setup.members] == [
        80,
        110,
        26,
    ], setup.commands


async def test_deferred_colour_preserves_brightness_with_delayed_entity_report(
    hass,
    monkeypatch,
):
    """An OFF cache must not reapply default brightness over explicit scene intent."""
    setup = await setup_scene_group(hass)
    right = setup.members[1]
    profile = f"{RIGHT}.default"
    hass.data[DATA_PROFILES].data[profile] = Profile(profile, None, None, 200, None)
    physical = {"on": False, "brightness": right.brightness, "kelvin": 4000}

    async def delayed_turn_on(**kwargs):
        # Non-optimistic MQTT entities retain both LightEntity.is_on and the HA
        # state until a report arrives, while the physical bulb accepts writes.
        setup.commands.append({"target": RIGHT, "service": "turn_on", **kwargs})
        physical["on"] = True
        if ATTR_BRIGHTNESS in kwargs:
            physical["brightness"] = kwargs[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            physical["kelvin"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

    monkeypatch.setattr(right, "async_turn_on", delayed_turn_on)
    await activate_scene(hass, {RIGHT: scene_state(3500, 80)})

    assert not right.is_on
    assert hass.states.get(RIGHT).state == STATE_OFF
    assert physical == {"on": True, "brightness": 80, "kelvin": 3500}, setup.commands


async def test_native_colour_only_call_preserves_existing_brightness_defaults(hass):
    """Colour splitting must not apply a default brightness to an already-ON bulb."""
    setup = await setup_reported_group(hass)
    profile = f"{LEFT}.default"
    hass.data[DATA_PROFILES].data[profile] = Profile(profile, None, None, 200, None)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [LEFT, RIGHT], ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert setup.members[0].brightness == 80, setup.commands
    assert all(member.physical_kelvin == 3500 for member in setup.members[:2])
    assert setup.members[1].is_on
    assert not setup.members[2].is_on


@pytest.mark.parametrize("service", ["group", "scene"])
async def test_native_only_once_brightness_update_keeps_existing_colour(hass, service):
    """Brightness-only requests do not re-adapt lights that were already ON."""
    setup = await setup_reported_group(hass, **{CONF_ONLY_ONCE: True})
    await prepare_reported_members(hass, setup, on=(True, True, True), kelvin=3500)
    if service == "group":
        await hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: GROUP, ATTR_BRIGHTNESS: 70},
            blocking=True,
            context=Context(),
        )
        await hass.async_block_till_done()
    else:
        await activate_scene(
            hass,
            {
                member.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 70}
                for member in setup.members
            },
        )
    assert all(member.brightness == 70 for member in setup.members)
    assert [member.physical_kelvin for member in setup.members] == [3500] * 3
    assert setup.colour_commands == [], setup.commands


@pytest.mark.parametrize("intercept", [False, True])
async def test_native_whole_group_brightness_adapts_once(hass, freezer, intercept):
    """A whole-group activation sends one brightness update, not one per member."""
    setup = await setup_reported_group(
        hass,
        **{CONF_TAKE_OVER_CONTROL: True, CONF_INTERCEPT: intercept},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    freezer.tick(11)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert all(member.is_on for member in setup.members)
    assert all(member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    brightness_commands = [call for call in setup.commands if ATTR_BRIGHTNESS in call]
    assert len(brightness_commands) == 1, setup.commands
    assert brightness_commands[0]["target"] == GROUP
