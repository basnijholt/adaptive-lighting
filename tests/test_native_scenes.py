"""Native-group scenes behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_COLOR_TEMP,
    CONF_ONLY_ONCE,
    CONF_SLEEP_COLOR_TEMP,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    Profile,
)
from homeassistant.components.light.const import DATA_COMPONENT, DATA_PROFILES
from homeassistant.components.light.const import DATA_COMPONENT as LIGHT_COMPONENT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_LIGHTS,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context
from homeassistant.setup import async_setup_component

from .support.adaptive import setup_switch
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
    prepare_reported_members,
    scene_state,
    setup_reported_group,
    setup_scene_group,
)


async def test_explicit_scene_brightness_survives_enabled_brightness_adaptation(hass):
    """Covered activations retain each requested scene level without extra repairs."""
    setup = await setup_scene_group(hass)
    await setup.switch.adapt_brightness_switch.async_turn_on()
    setup.commands.clear()
    brightness = {LEFT: 90, RIGHT: 140, OFF_MEMBER: 35}

    await activate_scene(
        hass,
        {eid: scene_state(3500, level) for eid, level in brightness.items()},
    )

    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert {
        member.entity_id: member.brightness for member in setup.members
    } == brightness
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == GROUP
    assert ATTR_BRIGHTNESS not in setup.colour_commands[0]
    assert len([call for call in setup.commands if ATTR_BRIGHTNESS in call]) == 3


async def test_scene_zero_brightness_is_off_intent_not_colour_coverage(hass):
    """A zero-brightness turn-on must stay OFF and receive no colour correction."""
    setup = await setup_scene_group(hass)
    await activate_scene(
        hass,
        {
            LEFT: scene_state(3500, 100),
            RIGHT: scene_state(3500, 120),
            OFF_MEMBER: scene_state(3500, 0),
        },
    )

    assert setup.members[0].physical_kelvin == 3500
    assert setup.members[1].physical_kelvin == 3500
    assert not setup.members[2].is_on
    assert setup.members[2].physical_kelvin == 4000
    assert len(setup.colour_commands) == 2, setup.commands
    assert {call["target"] for call in setup.colour_commands} == {LEFT, RIGHT}
    assert not any(call["target"] == GROUP for call in setup.commands)


async def test_native_scene_preserves_unrelated_light_and_nonlight_targets(hass):
    """A mixed scene groups eligible colour without taking over other targets."""
    setup = await setup_scene_group(hass)
    outside = RecordingMember("light.outside_native_group", setup.commands)
    await hass.data[LIGHT_COMPONENT].async_add_entities([outside])
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"native_scene_unrelated": {"initial": False}}},
    )
    entities = {member.entity_id: scene_state(3500, 100) for member in setup.members}
    entities[outside.entity_id] = scene_state(4500, 77)
    entities["input_boolean.native_scene_unrelated"] = {"state": STATE_ON}

    await activate_scene(hass, entities, transition=2)

    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert outside.is_on
    assert outside.physical_kelvin == 4500
    assert outside.brightness == 77
    assert hass.states.is_state("input_boolean.native_scene_unrelated", STATE_ON)
    colours = {call["target"]: call for call in setup.colour_commands}
    assert set(colours) == {GROUP, outside.entity_id}, setup.commands
    assert colours[outside.entity_id][ATTR_COLOR_TEMP_KELVIN] == 4500
    assert colours[outside.entity_id]["brightness"] == 77
    assert colours[outside.entity_id][ATTR_TRANSITION] == 2


async def test_native_group_explicit_colour_preserves_off_members(hass):
    """An existing CT-only native broadcast must never gain a bare power command."""
    setup = await setup_scene_group(hass)
    original_brightness = [member.brightness for member in setup.members]
    assert [member.is_on for member in setup.members] == [True, False, False]

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
    assert [member.brightness for member in setup.members] == original_brightness
    assert [member.physical_kelvin for member in setup.members] == [3500, 4000, 4000]
    assert hass.states.is_state(RIGHT, STATE_OFF)


@pytest.mark.parametrize("rgb_input", ["tuple", "list"])
async def test_native_scene_matching_rgb_is_one_group_command(hass, rgb_input):
    """Compatible RGB requests preserve their colour representation at dispatch."""
    setup = await setup_scene_group(hass)
    for entity in [setup.group, *setup.members]:
        entity._attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGB}
        entity._attr_color_mode = ColorMode.RGB
        entity._attr_rgb_color = (10, 20, 30)
        entity.async_write_ha_state()
    await hass.async_block_till_done()
    setup.commands.clear()
    requested_rgb = (40, 80, 160)
    levels = [80, 110, 26]

    await activate_scene(
        hass,
        {
            member.entity_id: {
                "state": STATE_ON,
                "color_mode": ColorMode.RGB,
                ATTR_RGB_COLOR: (
                    requested_rgb if rgb_input == "tuple" else list(requested_rgb)
                ),
                "brightness": level,
            }
            for member, level in zip(setup.members, levels, strict=True)
        },
        transition=3,
    )

    colour_commands = [
        call
        for call in setup.commands
        if ATTR_RGB_COLOR in call or ATTR_COLOR_TEMP_KELVIN in call
    ]
    assert len(colour_commands) == 1, setup.commands
    command = colour_commands[0]
    assert command["target"] == GROUP
    assert tuple(command[ATTR_RGB_COLOR]) == requested_rgb
    assert command[ATTR_TRANSITION] == 3
    assert "brightness" not in command
    assert ATTR_COLOR_TEMP_KELVIN not in command
    assert all(member.is_on for member in setup.members)
    assert [member.brightness for member in setup.members] == levels


async def test_native_scene_uses_fully_covered_existing_subgroup(hass):
    """A complete smaller group can serve an incomplete larger-group request."""
    setup = await setup_scene_group(hass)
    subset = RecordingGroup(setup.members[:2], setup.commands)
    subset.entity_id = "light.native_front_subset"
    await hass.data[LIGHT_COMPONENT].async_add_entities([subset])
    await setup.switch.async_turn_off()
    _, combined = await setup_switch(
        hass,
        {
            CONF_NAME: "native_group_and_subgroup",
            CONF_LIGHTS: [GROUP, subset.entity_id],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_COLOR_TEMP: 3000,
            CONF_MAX_COLOR_TEMP: 3000,
            CONF_SLEEP_COLOR_TEMP: 3000,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    await combined.adapt_brightness_switch.async_turn_off()
    await hass.async_block_till_done()
    untouched = setup.members[2]
    original = (untouched.is_on, untouched.brightness, untouched.physical_kelvin)
    setup.commands.clear()

    await activate_scene(
        hass,
        {
            setup.members[0].entity_id: scene_state(3500, 81),
            setup.members[1].entity_id: scene_state(3500, 111),
        },
        transition=2,
    )

    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == subset.entity_id
    assert setup.colour_commands[0][ATTR_COLOR_TEMP_KELVIN] == 3500
    assert setup.colour_commands[0][ATTR_TRANSITION] == 2
    assert "brightness" not in setup.colour_commands[0]
    assert [member.physical_kelvin for member in setup.members[:2]] == [3500, 3500]
    assert [member.brightness for member in setup.members[:2]] == [81, 111]
    assert (
        untouched.is_on,
        untouched.brightness,
        untouched.physical_kelvin,
    ) == original
    assert not any(
        call["target"] in {GROUP, untouched.entity_id} for call in setup.commands
    )


@pytest.mark.parametrize("durations", [(3, 5, 7), (3, 3, 3)])
async def test_native_scene_preserves_effective_default_transitions(hass, durations):
    """Only matching effective transitions permit a shared scene colour command."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    for member, duration in zip(setup.members, durations, strict=True):
        profile = f"{member.entity_id}.default"
        hass.data[DATA_PROFILES].data[profile] = Profile(
            profile,
            None,
            None,
            None,
            duration,
        )
    await hass.services.async_call(
        "scene",
        "apply",
        {
            "entities": {
                member.entity_id: {"state": STATE_ON, ATTR_COLOR_TEMP_KELVIN: 3500}
                for member in setup.members
            },
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    if len(set(durations)) == 1:
        expected = {GROUP: durations[0]}
    else:
        expected = {
            member.entity_id: duration
            for member, duration in zip(setup.members, durations, strict=True)
        }
    assert {
        call["target"]: call.get(ATTR_TRANSITION) for call in setup.colour_commands
    } == expected, setup.commands
    assert len(setup.colour_commands) == len(expected)


async def test_native_only_once_scene_repairs_only_newly_on_member(hass):
    """An existing colour on lit siblings survives one member joining a scene."""
    setup = await setup_reported_group(hass, **{CONF_ONLY_ONCE: True})
    await prepare_reported_members(hass, setup, on=(True, False, True), kelvin=3500)
    await activate_scene(
        hass,
        {
            member.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 70}
            for member in setup.members
        },
        transition=0,
    )
    assert all(member.is_on for member in setup.members)
    assert [member.physical_kelvin for member in setup.members] == [3500, 3000, 3500]
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == RIGHT


async def test_native_only_once_allows_explicit_scene_colour(hass):
    """Only-once adaptation must not block the user's explicit scene colour."""
    setup = await setup_reported_group(hass, **{CONF_ONLY_ONCE: True})
    await prepare_reported_members(hass, setup, on=(True, True, True), kelvin=3500)
    await activate_scene(
        hass,
        {
            member.entity_id: {"state": STATE_ON, ATTR_COLOR_TEMP_KELVIN: 4500}
            for member in setup.members
        },
        transition=0,
    )
    assert [member.physical_kelvin for member in setup.members] == [4500] * 3
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == GROUP


async def test_native_scene_subgroup_repairs_only_its_members(hass, freezer):
    """A native subgroup activation inherits its configured parent adaptation."""
    setup = await setup_reported_group(hass, **{CONF_TAKE_OVER_CONTROL: True})
    subgroup = RecordingGroup(setup.members[1:], setup.commands)
    subgroup.entity_id = "light.review_scene_subset"
    subgroup._attr_is_on = False
    await hass.data[DATA_COMPONENT].async_add_entities([subgroup])
    await hass.async_block_till_done()
    setup.commands.clear()
    freezer.tick(11)
    await activate_scene(
        hass,
        {subgroup.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 90}},
        transition=0,
    )
    assert all(member.is_on for member in setup.members[1:])
    assert all(member.brightness == 90 for member in setup.members[1:])
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members[1:])
    assert setup.members[0].brightness == 80
    assert setup.members[0].physical_kelvin == 4000
    assert not any(call["target"] == GROUP for call in setup.commands)


@pytest.mark.parametrize(
    ("default_brightness", "default_transition", "group_on"),
    [(None, 7, True), (200, None, False)],
)
async def test_native_scene_ignores_unrequested_group_defaults(
    hass,
    default_brightness,
    default_transition,
    group_on,
):
    """Broadcasting cannot add the native target's own brightness or transition."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    setup.group._attr_is_on = group_on
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    setup.commands.clear()
    profile = f"{GROUP}.default"
    hass.data[DATA_PROFILES].data[profile] = Profile(
        profile,
        None,
        None,
        default_brightness,
        default_transition,
    )
    levels = (90, 140, 35)
    await hass.services.async_call(
        "scene",
        "apply",
        {
            "entities": {
                member.entity_id: {
                    "state": STATE_ON,
                    ATTR_BRIGHTNESS: level,
                    ATTR_COLOR_TEMP_KELVIN: 3500,
                }
                for member, level in zip(setup.members, levels, strict=True)
            },
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert tuple(member.brightness for member in setup.members) == levels
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert all(ATTR_TRANSITION not in call for call in setup.commands)
    assert {call["target"] for call in setup.colour_commands} == {
        member.entity_id for member in setup.members
    }
    assert len(setup.colour_commands) == len(setup.members)


@pytest.mark.parametrize("service", ["apply", "turn_on"])
@pytest.mark.parametrize("kelvin", [TARGET_KELVIN, 3500])
async def test_scene_complete_matching_colour_uses_one_native_group_command(
    hass,
    service,
    kelvin,
):
    """Already-ON and newly-ON members share one complete scene colour command."""
    setup = await setup_scene_group(hass)
    brightness = {LEFT: 90, RIGHT: 140, OFF_MEMBER: 35}
    await activate_scene(
        hass,
        {eid: scene_state(kelvin, level) for eid, level in brightness.items()},
        service=service,
        transition=2,
    )

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == kelvin for member in setup.members)
    assert all(
        member.brightness == brightness[member.entity_id] for member in setup.members
    )
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0] == {
        "target": GROUP,
        "service": "turn_on",
        ATTR_COLOR_TEMP_KELVIN: kelvin,
        ATTR_TRANSITION: 2,
    }
    assert setup.switch.lights == [GROUP]


@pytest.mark.parametrize("service", ["apply", "turn_on"])
async def test_scene_partial_colour_targets_only_included_member(hass, service):
    """A partial scene cannot broadcast over a lit or excluded OFF sibling."""
    setup = await setup_scene_group(hass)
    left, right, off_member = setup.members
    await activate_scene(
        hass,
        {RIGHT: scene_state(3500, 37), OFF_MEMBER: {"state": STATE_OFF}},
        service=service,
        transition=3,
    )

    assert right.is_on
    assert right.physical_kelvin == 3500
    assert right.brightness == 37
    assert left.is_on
    assert left.physical_kelvin == 4000
    assert left.brightness == 80
    assert not off_member.is_on
    assert off_member.physical_kelvin == 4000
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == RIGHT
    assert setup.colour_commands[0][ATTR_COLOR_TEMP_KELVIN] == 3500
    assert setup.colour_commands[0][ATTR_TRANSITION] == 3
    assert not any(call["target"] == GROUP for call in setup.commands)


async def test_scene_different_colours_remain_individual(hass):
    """Complete membership alone is insufficient if requested colours differ."""
    setup = await setup_scene_group(hass)
    colours = {LEFT: 3500, RIGHT: 3000, OFF_MEMBER: 4500}
    await activate_scene(
        hass,
        {eid: scene_state(kelvin, 100) for eid, kelvin in colours.items()},
    )

    assert all(
        member.physical_kelvin == colours[member.entity_id] for member in setup.members
    )
    assert len(setup.colour_commands) == len(setup.members), setup.commands
    assert {
        call["target"]: call[ATTR_COLOR_TEMP_KELVIN] for call in setup.colour_commands
    } == colours
    assert not any(call["target"] == GROUP for call in setup.commands)


async def test_scene_native_group_colour_already_covers_member_activation(hass):
    """A scene's own native broadcast must not be followed by member repairs."""
    setup = await setup_scene_group(hass)
    await activate_scene(hass, {GROUP: scene_state(3500, 100)}, transition=3)

    assert all(
        member.is_on and member.physical_kelvin == 3500 for member in setup.members
    )
    assert all(member.brightness == 100 for member in setup.members)
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == GROUP
    assert setup.colour_commands[0][ATTR_COLOR_TEMP_KELVIN] == 3500
    assert setup.colour_commands[0][ATTR_TRANSITION] == 3


async def test_scene_covered_late_member_report_does_not_duplicate_colour(hass):
    """A real activation report arriving after scene completion remains covered."""
    setup = await setup_scene_group(hass)
    setup.members[1].hold_reports = True
    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in setup.members},
    )
    assert hass.states.get(RIGHT).state == STATE_OFF
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    before_report = list(setup.commands)

    # The device has already accepted power and colour. Only its report arrives
    # late, without reissuing the scene or inventing another user activation.
    setup.members[1].hold_reports = False
    setup.members[1].async_write_ha_state()
    await hass.async_block_till_done()

    assert hass.states.get(RIGHT).state == STATE_ON
    assert setup.commands == before_report
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == GROUP


@pytest.mark.parametrize("service", ["apply", "turn_on"])
async def test_scene_complete_colour_intent_survives_fully_matching_ha_cache(
    hass,
    service,
):
    """HA's scene no-op optimization cannot discard complete colour intent."""
    setup = await setup_scene_group(hass)
    await setup.switch.async_turn_off()
    for member in setup.members:
        member._attr_is_on = True
        member.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch.async_turn_on(adapt_lights=False)
    setup.commands.clear()

    # Every desired attribute equals HA's optimistic cache, including power and
    # brightness. Only the complete scene request exposes colour intent; there
    # are no downstream light calls from HA's default reproduction path.
    await activate_scene(
        hass,
        {
            member.entity_id: {
                "state": STATE_ON,
                **hass.states.get(member.entity_id).attributes,
            }
            for member in setup.members
        },
        service=service,
    )

    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    assert [member.brightness for member in setup.members] == [80, 110, 26]
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
            ATTR_TRANSITION: 2,
        },
    ]


async def test_scene_partial_colour_intent_survives_matching_ha_cache(hass):
    """An already-ON individual target still receives its explicit scene colour."""
    setup = await setup_scene_group(hass)
    await activate_scene(
        hass,
        {LEFT: {"state": STATE_ON, **hass.states.get(LEFT).attributes}},
    )

    left, right, off_member = setup.members
    assert left.physical_kelvin == TARGET_KELVIN
    assert left.brightness == 80
    assert not right.is_on
    assert not off_member.is_on
    assert right.physical_kelvin == 4000
    assert off_member.physical_kelvin == 4000
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == LEFT
    assert setup.colour_commands[0][ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN
    assert not any(call["target"] == GROUP for call in setup.commands)


@pytest.mark.parametrize("change", ["membership", "disable_profile"])
async def test_scene_revalidates_group_before_sending_broadcast(hass, change):
    """A changed group or disabled profile cannot receive a planned broadcast."""
    setup = await setup_scene_group(hass)
    outside = RecordingMember("light.scene_outside_control", setup.commands)
    await hass.data[DATA_COMPONENT].async_add_entities([outside])

    async def change_during_dispatch():
        if change == "membership":
            setup.group.members.append(outside)
            setup.group.async_write_ha_state()
        else:
            await setup.switch.async_turn_off()

    # A scene with newly ON lights must dispatch their power before a colour-
    # only native broadcast can reach them. Change the plan's preconditions at
    # that real device boundary, without relying on a future private API.
    setup.members[0].before_turn_on = change_during_dispatch
    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in setup.members},
    )

    assert all(member.is_on for member in setup.members[:3])
    assert all(member.physical_kelvin == 3500 for member in setup.members[:3])
    assert not outside.is_on
    assert outside.physical_kelvin == 4000
    assert not any(call["target"] == GROUP for call in setup.commands)
    assert {call["target"] for call in setup.colour_commands} == {
        LEFT,
        RIGHT,
        OFF_MEMBER,
    }


async def test_scene_off_member_colour_attribute_is_not_broadcast_coverage(hass):
    """A stored colour on an OFF scene target does not request a colour update."""
    setup = await setup_scene_group(hass)
    await activate_scene(
        hass,
        {
            LEFT: scene_state(3500, 100),
            RIGHT: scene_state(3500, 120),
            OFF_MEMBER: {"state": STATE_OFF, ATTR_COLOR_TEMP_KELVIN: 3500},
        },
    )

    left, right, off_member = setup.members
    assert left.physical_kelvin == 3500
    assert right.physical_kelvin == 3500
    assert not off_member.is_on
    assert off_member.physical_kelvin == 4000
    assert len(setup.colour_commands) == 2, setup.commands
    assert {call["target"] for call in setup.colour_commands} == {LEFT, RIGHT}
    assert not any(call["target"] == GROUP for call in setup.commands)


@pytest.mark.parametrize("capability", ["colour_mode", "temperature_range"])
async def test_scene_incompatible_group_capability_uses_individual_targets(
    hass,
    capability,
):
    """Group coverage does not guarantee it supports the members' colour request."""
    setup = await setup_scene_group(hass)
    if capability == "colour_mode":
        setup.group._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        setup.group._attr_color_mode = ColorMode.BRIGHTNESS
    else:
        setup.group._attr_max_color_temp_kelvin = 3200
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
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


async def test_independent_colour_calls_with_different_transitions_are_not_grouped(
    hass,
):
    """A shared context cannot erase different transition intent across calls."""
    setup = await setup_scene_group(hass)
    transitions = {LEFT: 1, RIGHT: 3, OFF_MEMBER: 5}
    context = Context()
    await asyncio.gather(
        *(
            hass.services.async_call(
                "light",
                "turn_on",
                {
                    ATTR_ENTITY_ID: member.entity_id,
                    ATTR_COLOR_TEMP_KELVIN: 3500,
                    ATTR_TRANSITION: transitions[member.entity_id],
                },
                blocking=True,
                context=context,
            )
            for member in setup.members
        ),
    )
    await hass.async_block_till_done()

    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert len(setup.colour_commands) == 3, setup.commands
    assert {
        call["target"]: call[ATTR_TRANSITION] for call in setup.colour_commands
    } == transitions
    assert not any(call["target"] == GROUP for call in setup.commands)
