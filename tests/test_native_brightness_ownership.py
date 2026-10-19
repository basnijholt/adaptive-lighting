"""Independent brightness ownership preserves native colour consolidation."""

import sys

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_BRIGHTNESS,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
)
from homeassistant.const import CONF_LIGHTS, CONF_NAME, STATE_ON

from .support.adaptive import setup_switch
from .support.native_lights import GROUP, LEFT, OFF_MEMBER, RIGHT, TARGET_KELVIN
from .support.native_scenarios import (
    activate_scene,
    prepare_reported_members,
    scene_state,
    setup_reported_group,
)


async def _setup_independent_owners(
    hass,
    brightness_target=GROUP,
    *,
    brightness_delay=0,
    colour_delay=0,
):
    """Install a colour-only native profile and independent brightness owner."""
    setup = await setup_reported_group(hass, **{CONF_ADAPT_DELAY: colour_delay})
    _, brightness_owner = await setup_switch(
        hass,
        {
            CONF_NAME: "independent_brightness_owner",
            CONF_LIGHTS: [brightness_target],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_BRIGHTNESS: 50,
            CONF_MAX_BRIGHTNESS: 50,
            CONF_TAKE_OVER_CONTROL: False,
            CONF_ADAPT_DELAY: brightness_delay,
        },
    )
    await brightness_owner.async_turn_off()
    await brightness_owner.adapt_color_switch.async_turn_off()
    await brightness_owner.adapt_brightness_switch.async_turn_on()
    await prepare_reported_members(hass, setup, on=(True, True, True))
    await brightness_owner.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()
    assert setup.switch.adapt_color_switch.is_on
    assert not setup.switch.adapt_brightness_switch.is_on
    assert brightness_owner.is_on
    assert brightness_owner.adapt_brightness_switch.is_on
    assert not brightness_owner.adapt_color_switch.is_on
    setup.commands.clear()
    return setup, brightness_owner


@pytest.mark.parametrize("brightness_target", [GROUP, RIGHT])
async def test_noncompeting_brightness_owner_preserves_native_colour_group(
    hass,
    brightness_target,
):
    """A brightness-only owner does not compete for the group's colour command."""
    setup, _ = await _setup_independent_owners(hass, brightness_target)
    levels = {LEFT: 90, RIGHT: 140, OFF_MEMBER: 35}

    await activate_scene(
        hass,
        {entity: scene_state(3500, level) for entity, level in levels.items()},
        transition=2,
    )

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert {member.entity_id: member.brightness for member in setup.members} == levels
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 2,
        },
    ]
    assert len([call for call in setup.commands if ATTR_BRIGHTNESS in call]) == 3


@pytest.mark.parametrize("explicit", [False, True])
async def test_independent_group_owners_send_each_attribute_once(hass, explicit):
    """Distinct profiles retain separate broadcasts even when both values match."""
    setup, brightness_owner = await _setup_independent_owners(hass)
    await brightness_owner.async_turn_off()
    await prepare_reported_members(hass, setup, on=(False, False, False))
    await brightness_owner.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()
    setup.commands.clear()

    await activate_scene(
        hass,
        {
            member.entity_id: (
                scene_state(3500, 100) if explicit else {"state": STATE_ON}
            )
            for member in setup.members
        },
        transition=2,
    )

    level = 100 if explicit else 128
    kelvin = 3500 if explicit else TARGET_KELVIN
    assert all(member.is_on and member.brightness == level for member in setup.members)
    assert all(member.physical_kelvin == kelvin for member in setup.members)
    assert [
        call
        for call in setup.commands
        if ATTR_BRIGHTNESS in call or ATTR_COLOR_TEMP_KELVIN in call
    ] == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: level,
            ATTR_TRANSITION: 2,
        },
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: kelvin,
            ATTR_TRANSITION: 2,
        },
    ]


@pytest.mark.parametrize("competing_attribute", ["brightness", "color"])
async def test_competing_member_owner_only_prevents_its_own_group_attribute(
    hass,
    competing_attribute,
):
    """A direct owner of one attribute cannot block the other native broadcast."""
    setup, _ = await _setup_independent_owners(hass)
    _, competing = await setup_switch(
        hass,
        {
            CONF_NAME: "competing_direct_owner",
            CONF_LIGHTS: [RIGHT],
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    if competing_attribute == "brightness":
        await competing.adapt_color_switch.async_turn_off()
    else:
        await competing.adapt_brightness_switch.async_turn_off()
    await hass.async_block_till_done()
    setup.commands.clear()

    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in setup.members},
        transition=2,
    )

    assert all(member.is_on and member.brightness == 100 for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    grouped, individual = (
        (ATTR_COLOR_TEMP_KELVIN, ATTR_BRIGHTNESS)
        if competing_attribute == "brightness"
        else (ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN)
    )
    shared = [call for call in setup.commands if grouped in call]
    assert len(shared) == 1, setup.commands
    assert shared[0]["target"] == GROUP
    assert individual not in shared[0]
    separate = [call for call in setup.commands if individual in call]
    assert len(separate) == len(setup.members), setup.commands
    assert {call["target"] for call in separate} == {LEFT, RIGHT, OFF_MEMBER}


@pytest.mark.parametrize("first_attribute", ["brightness", "color"])
async def test_independent_owners_each_receive_their_adaptive_delay(
    hass,
    monkeypatch,
    first_attribute,
):
    """One owner's short wait cannot consume another owner's longer delay."""
    setup, brightness_owner = await _setup_independent_owners(
        hass,
        brightness_delay=0.1 if first_attribute == "brightness" else 1,
        colour_delay=0.1 if first_attribute == "color" else 1,
    )
    await brightness_owner.async_turn_off()
    await prepare_reported_members(hass, setup, on=(False, False, False))
    await brightness_owner.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()
    setup.commands.clear()
    planner = setup.switch.manager.native_groups
    module = sys.modules[type(planner).__module__]
    original_asyncio = module.asyncio
    waits = []

    class RecordingAsyncio:
        """Record only the planner's waits while leaving HA's scheduler unchanged."""

        def __getattr__(self, name):
            return getattr(original_asyncio, name)

        async def sleep(self, delay, result=None):
            waits.append(delay)
            return await original_asyncio.sleep(0, result)

    monkeypatch.setattr(module, "asyncio", RecordingAsyncio())

    await activate_scene(
        hass,
        {member.entity_id: {"state": STATE_ON} for member in setup.members},
        transition=2,
    )

    assert waits == pytest.approx([0.1, 0.9])
    assert all(member.is_on and member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    first, second = (
        (ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN)
        if first_attribute == "brightness"
        else (ATTR_COLOR_TEMP_KELVIN, ATTR_BRIGHTNESS)
    )
    commands = [
        call
        for call in setup.commands
        if ATTR_BRIGHTNESS in call or ATTR_COLOR_TEMP_KELVIN in call
    ]
    assert len(commands) == 2, setup.commands
    assert all(call["target"] == GROUP for call in commands)
    assert first in commands[0]
    assert second not in commands[0]
    assert second in commands[1]
    assert first not in commands[1]
