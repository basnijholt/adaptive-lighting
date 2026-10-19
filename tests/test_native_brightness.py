"""Native scenes consolidate brightness and colour independently."""

import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_TAKE_OVER_CONTROL,
    CONF_TAKE_OVER_CONTROL_MODE,
    TakeOverControlMode,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    Profile,
)
from homeassistant.components.light.const import DATA_PROFILES
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import Context

from .support.async_helpers import DelayBarrier
from .support.native_lights import GROUP, LEFT, OFF_MEMBER, RIGHT, TARGET_KELVIN
from .support.native_scenarios import (
    activate_scene,
    prepare_reported_members,
    scene_state,
    set_manual,
    setup_reported_group,
)


@pytest.mark.parametrize("service", ["apply", "turn_on"])
async def test_native_scene_matching_brightness_groups_with_different_colours(
    hass,
    service,
):
    """Colour disagreement cannot prevent a shared, explicit brightness command."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(True, False, False),
        brightness_adaptation=True,
    )
    colours = {LEFT: 3500, RIGHT: 3000, OFF_MEMBER: 4500}

    await activate_scene(
        hass,
        {entity_id: scene_state(kelvin, 100) for entity_id, kelvin in colours.items()},
        service=service,
        transition=3,
    )

    assert all(member.is_on and member.brightness == 100 for member in setup.members)
    assert {
        member.entity_id: member.physical_kelvin for member in setup.members
    } == colours
    assert [call for call in setup.commands if ATTR_BRIGHTNESS in call] == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: 100,
            ATTR_TRANSITION: 3,
        },
    ]
    assert {
        call["target"]: call[ATTR_COLOR_TEMP_KELVIN] for call in setup.colour_commands
    } == colours
    assert len(setup.colour_commands) == 3, setup.commands
    assert all(ATTR_BRIGHTNESS not in call for call in setup.colour_commands)


@pytest.mark.parametrize("split", [False, True])
async def test_native_scene_matching_explicit_axes_share_one_group_command(hass, split):
    """The split policy governs computed adaptation, not explicit scene values."""
    setup = await setup_reported_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: split},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(True, False, False),
        brightness_adaptation=True,
    )

    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in setup.members},
        transition=3,
    )

    assert all(member.is_on and member.brightness == 100 for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    adjustments = [
        call
        for call in setup.commands
        if ATTR_BRIGHTNESS in call or ATTR_COLOR_TEMP_KELVIN in call
    ]
    assert adjustments == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: 100,
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 3,
        },
    ]


@pytest.mark.parametrize("explicit", [False, True])
async def test_native_scene_brightness_only_groups_with_colour_adaptation_disabled(
    hass,
    explicit,
):
    """Disabling colour leaves native brightness consolidation available."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    await setup.switch.adapt_color_switch.async_turn_off()
    setup.commands.clear()

    await activate_scene(
        hass,
        {
            member.entity_id: {
                "state": STATE_ON,
                **({ATTR_BRIGHTNESS: 100} if explicit else {}),
            }
            for member in setup.members
        },
        transition=2,
    )

    expected_brightness = 100 if explicit else 128
    assert all(member.is_on for member in setup.members)
    assert all(member.brightness == expected_brightness for member in setup.members)
    assert all(member.physical_kelvin == 4000 for member in setup.members)
    assert not setup.colour_commands
    assert [call for call in setup.commands if ATTR_BRIGHTNESS in call] == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: expected_brightness,
            ATTR_TRANSITION: 2,
        },
    ]


@pytest.mark.parametrize("split", [False, True])
async def test_native_scene_computed_axes_follow_configured_split_policy(hass, split):
    """A full scene shares computed brightness and colour without member repairs."""
    setup = await setup_reported_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: split},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )

    await activate_scene(
        hass,
        {member.entity_id: {"state": STATE_ON} for member in setup.members},
        transition=2,
    )

    assert all(member.is_on and member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    adjustments = [
        call
        for call in setup.commands
        if ATTR_BRIGHTNESS in call or ATTR_COLOR_TEMP_KELVIN in call
    ]
    shared = {"target": GROUP, "service": "turn_on"}
    if split:
        assert adjustments == [
            {**shared, ATTR_BRIGHTNESS: 128, ATTR_TRANSITION: 1},
            {**shared, ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN, ATTR_TRANSITION: 1},
        ]
    else:
        assert adjustments == [
            {
                **shared,
                ATTR_BRIGHTNESS: 128,
                ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
                ATTR_TRANSITION: 2,
            },
        ]


async def test_native_scene_different_brightness_keeps_shared_colour(hass):
    """Brightness disagreement leaves each level intact and colour consolidated."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(True, False, False),
        brightness_adaptation=True,
    )
    levels = {LEFT: 90, RIGHT: 140, OFF_MEMBER: 35}

    await activate_scene(
        hass,
        {entity_id: scene_state(3500, level) for entity_id, level in levels.items()},
        transition=3,
    )

    assert {member.entity_id: member.brightness for member in setup.members} == levels
    assert all(
        member.is_on and member.physical_kelvin == 3500 for member in setup.members
    )
    brightness_commands = [call for call in setup.commands if ATTR_BRIGHTNESS in call]
    assert {
        call["target"]: call[ATTR_BRIGHTNESS] for call in brightness_commands
    } == levels
    assert len(brightness_commands) == 3
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 3,
        },
    ]


@pytest.mark.parametrize("excluded", ["omitted", "off", "zero_brightness"])
async def test_native_scene_incomplete_on_coverage_cannot_group_brightness(
    hass,
    excluded,
):
    """A shared brightness command must never activate an excluded sibling."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(True, False, False),
        brightness_adaptation=True,
    )
    entities = {LEFT: scene_state(3500, 100), RIGHT: scene_state(3500, 100)}
    if excluded == "off":
        entities[OFF_MEMBER] = {"state": STATE_OFF}
    elif excluded == "zero_brightness":
        entities[OFF_MEMBER] = scene_state(3500, 0)

    await activate_scene(hass, entities)

    assert all(
        member.is_on and member.brightness == 100 for member in setup.members[:2]
    )
    assert all(member.physical_kelvin == 3500 for member in setup.members[:2])
    untouched = setup.members[2]
    assert not untouched.is_on
    assert untouched.brightness == 26
    assert untouched.physical_kelvin == 4000
    assert not any(call["target"] == GROUP for call in setup.commands)
    assert {
        call["target"]: call[ATTR_BRIGHTNESS]
        for call in setup.commands
        if ATTR_BRIGHTNESS in call
    } == {LEFT: 100, RIGHT: 100}


@pytest.mark.parametrize("durations", [(3, 5, 7), (3, 3, 3)])
async def test_native_scene_brightness_uses_effective_member_transitions(
    hass,
    durations,
):
    """Only matching effective transitions permit shared brightness dispatch."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(True, True, True),
        brightness_adaptation=True,
    )
    await setup.switch.adapt_color_switch.async_turn_off()
    for member, duration in zip(setup.members, durations, strict=True):
        profile = f"{member.entity_id}.default"
        hass.data[DATA_PROFILES].data[profile] = Profile(
            profile,
            None,
            None,
            None,
            duration,
        )
    setup.commands.clear()

    await hass.services.async_call(
        "scene",
        "apply",
        {
            "entities": {
                member.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 100}
                for member in setup.members
            },
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.is_on and member.brightness == 100 for member in setup.members)
    assert all(member.physical_kelvin == 4000 for member in setup.members)
    brightness_commands = [call for call in setup.commands if ATTR_BRIGHTNESS in call]
    expected = (
        {GROUP: 3}
        if len(set(durations)) == 1
        else {
            member.entity_id: duration
            for member, duration in zip(setup.members, durations, strict=True)
        }
    )
    assert {
        call["target"]: call[ATTR_TRANSITION] for call in brightness_commands
    } == expected
    assert len(brightness_commands) == len(expected)


@pytest.mark.parametrize("manual_axis", ["brightness", "color"])
async def test_native_scene_manual_axis_does_not_prevent_other_axis_group(
    hass,
    manual_axis,
):
    """Selective manual control blocks only that member's computed axis."""
    setup = await setup_reported_group(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value,
        },
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    await set_manual(hass, setup.switch, RIGHT, manual_axis)
    setup.commands.clear()

    await activate_scene(
        hass,
        {member.entity_id: {"state": STATE_ON} for member in setup.members},
    )

    assert all(member.is_on for member in setup.members)
    right = setup.members[1]
    assert right.brightness == (110 if manual_axis == "brightness" else 128)
    assert right.physical_kelvin == (4000 if manual_axis == "color" else TARGET_KELVIN)
    assert all(
        member.brightness == 128 for member in (setup.members[0], setup.members[2])
    )
    assert all(
        member.physical_kelvin == TARGET_KELVIN
        for member in (setup.members[0], setup.members[2])
    )
    individual_axis = (
        ATTR_BRIGHTNESS if manual_axis == "brightness" else ATTR_COLOR_TEMP_KELVIN
    )
    grouped_axis = (
        ATTR_COLOR_TEMP_KELVIN if manual_axis == "brightness" else ATTR_BRIGHTNESS
    )
    individual = [call for call in setup.commands if individual_axis in call]
    grouped = [call for call in setup.commands if grouped_axis in call]
    assert len(individual) == 2, setup.commands
    assert {call["target"] for call in individual} == {LEFT, OFF_MEMBER}
    assert len(grouped) == 1, setup.commands
    assert grouped[0]["target"] == GROUP
    assert individual_axis not in grouped[0]


@pytest.mark.parametrize("adapt_colour", [False, True])
async def test_native_scene_late_report_retains_independent_axis_coverage(
    hass,
    adapt_colour,
):
    """Shared brightness cannot hide missing colour or cause a second correction."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    if not adapt_colour:
        await setup.switch.adapt_color_switch.async_turn_off()
    setup.commands.clear()
    right = setup.members[1]
    right.hold_reports = True

    await activate_scene(
        hass,
        {
            member.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 100}
            for member in setup.members
        },
        transition=2,
    )

    assert hass.states.is_state(RIGHT, STATE_OFF)
    assert all(member.is_on and member.brightness == 100 for member in setup.members)
    expected_kelvin = TARGET_KELVIN if adapt_colour else 4000
    assert all(member.physical_kelvin == expected_kelvin for member in setup.members)
    brightness_commands = [call for call in setup.commands if ATTR_BRIGHTNESS in call]
    assert len(brightness_commands) == 1, setup.commands
    assert brightness_commands[0]["target"] == GROUP
    assert len(setup.colour_commands) == int(adapt_colour), setup.commands
    if adapt_colour:
        assert setup.colour_commands[0]["target"] == GROUP
    before_report = list(setup.commands)

    right.hold_reports = False
    right.async_write_ha_state()
    await hass.async_block_till_done()

    assert hass.states.is_state(RIGHT, STATE_ON)
    assert setup.commands == before_report
    assert all(member.brightness == 100 for member in setup.members)
    assert all(member.physical_kelvin == expected_kelvin for member in setup.members)


async def test_native_colour_only_group_call_does_not_gain_brightness(hass):
    """An enabled brightness axis cannot turn OFF siblings on during a colour update."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(True, False, False),
        brightness_adaptation=True,
    )

    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: GROUP,
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 3,
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert setup.commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 3,
        },
    ]
    assert [member.is_on for member in setup.members] == [True, False, False]
    assert [member.brightness for member in setup.members] == [80, 110, 26]
    assert [member.physical_kelvin for member in setup.members] == [3500, 4000, 4000]


@pytest.mark.parametrize("adapt_delay", [0, 1])
async def test_native_scene_explicit_colour_keeps_shared_computed_brightness(
    hass,
    monkeypatch,
    adapt_delay,
):
    """Explicit member colours remain immediate while shared brightness adapts."""
    setup = await setup_reported_group(hass, **{CONF_ADAPT_DELAY: adapt_delay})
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    barrier = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    task = asyncio.create_task(
        activate_scene(
            hass,
            {
                member.entity_id: {
                    "state": STATE_ON,
                    ATTR_COLOR_TEMP_KELVIN: 3500,
                }
                for member in setup.members
            },
            transition=2,
        ),
    )
    try:
        if adapt_delay:
            await asyncio.wait_for(barrier.entered.wait(), 2)
            assert barrier.delay == adapt_delay
            assert len(setup.colour_commands) == 1, setup.commands
            assert setup.colour_commands[0]["target"] == GROUP
            assert all(member.physical_kelvin == 3500 for member in setup.members)
            assert not any(ATTR_BRIGHTNESS in call for call in setup.commands)
            assert not task.done()
    finally:
        barrier.release.set()
        await task
    await hass.async_block_till_done()

    assert all(member.is_on and member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert [call for call in setup.commands if ATTR_BRIGHTNESS in call] == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: 128,
            ATTR_TRANSITION: 2,
        },
    ]
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 2,
        },
    ]
