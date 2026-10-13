"""Brightness coverage survives delayed reports without hiding other work."""

# pylint: disable=protected-access
import sys

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_TAKE_OVER_CONTROL,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    ColorMode,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import Context

from .support.native_lights import GROUP, RIGHT, TARGET_KELVIN
from .support.native_scenarios import (
    activate_scene,
    prepare_reported_members,
    setup_reported_group,
)


async def _brightness_only_setup(hass, **config):
    setup = await setup_reported_group(hass, **config)
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    await setup.switch.adapt_color_switch.async_turn_off()
    await hass.async_block_till_done()
    setup.commands.clear()
    return setup


async def _activate_brightness_scene(hass, setup):
    await activate_scene(
        hass,
        {
            member.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 150}
            for member in setup.members
        },
    )


async def test_delayed_brightness_activation_is_not_external_manual_control(
    hass,
    freezer,
):
    """A genuine group activation owns its late report with either axis covered."""
    setup = await _brightness_only_setup(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON: True,
        },
    )
    right = setup.members[1]
    right.hold_reports = True
    freezer.tick(11)

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert right.is_on
    assert right.brightness == 128
    assert hass.states.get(RIGHT).state == STATE_OFF
    commands_before_report = list(setup.commands)

    freezer.tick(60)
    right.hold_reports = False
    right.async_set_context(Context())
    right.async_write_ha_state()
    await hass.async_block_till_done()

    assert hass.states.get(RIGHT).state == STATE_ON
    assert setup.switch.manager.get_manual_control_attributes(RIGHT).has_none()
    assert setup.commands == commands_before_report


async def test_brightness_coverage_does_not_hide_later_supported_colour(hass, freezer):
    """An axis absent from the plan remains eligible when a report adds support."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    for light in (*setup.members, setup.group):
        light._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        light._attr_color_mode = ColorMode.BRIGHTNESS
        light.async_write_ha_state()
    await hass.async_block_till_done()
    right = setup.members[1]
    right.hold_reports = True
    setup.commands.clear()

    await _activate_brightness_scene(hass, setup)

    assert right.is_on
    assert right.brightness == 150
    assert right.physical_kelvin == 4000
    assert hass.states.get(RIGHT).state == STATE_OFF
    commands_before_report = len(setup.commands)

    freezer.tick(60)
    right._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    right._attr_color_mode = ColorMode.COLOR_TEMP
    right.hold_reports = False
    right.async_set_context(Context())
    right.async_write_ha_state()
    await hass.async_block_till_done()

    assert right.brightness == 150
    assert right.physical_kelvin == TARGET_KELVIN
    assert setup.commands[commands_before_report:] == [
        {
            "target": RIGHT,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
        },
    ]


async def test_new_off_retires_brightness_coverage_before_later_activation(hass):
    """A fresh activation can adapt brightness after an older scene claim ends."""
    setup = await _brightness_only_setup(hass)
    right = setup.members[1]
    right.hold_reports = True
    await _activate_brightness_scene(hass, setup)

    await hass.services.async_call(
        "light",
        "turn_off",
        {ATTR_ENTITY_ID: RIGHT},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert not right.is_on
    right.hold_reports = False
    setup.commands.clear()

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: RIGHT},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert right.is_on
    assert right.brightness == 128
    assert all(
        member.brightness == 150 for member in (setup.members[0], setup.members[2])
    )
    assert not setup.colour_commands
    assert all(call["target"] == RIGHT for call in setup.commands)
    assert len([call for call in setup.commands if ATTR_BRIGHTNESS in call]) == 1


@pytest.mark.parametrize("split", [False, True])
async def test_shared_computed_brightness_retains_member_colour_timing(
    hass,
    monkeypatch,
    split,
):
    """Grouping one axis cannot restart adaptation delay or lose split timing."""
    setup = await setup_reported_group(
        hass,
        **{
            CONF_ADAPT_DELAY: 0.2,
            CONF_SEPARATE_TURN_ON_COMMANDS: split,
            CONF_SEND_SPLIT_DELAY: 50,
        },
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    setup.members[1]._attr_max_color_temp_kelvin = 2800
    setup.members[1].async_write_ha_state()
    await hass.async_block_till_done()
    module = sys.modules[type(setup.switch.manager.native_groups).__module__]
    original_asyncio = module.asyncio
    delays = []

    class RecordingAsyncio:
        """Observe real planner waits without replacing their scheduling."""

        def __getattr__(self, name):
            return getattr(original_asyncio, name)

        async def sleep(self, delay, result=None):
            delays.append(
                (delay, any(ATTR_BRIGHTNESS in call for call in setup.commands)),
            )
            return await original_asyncio.sleep(delay, result)

    monkeypatch.setattr(module, "asyncio", RecordingAsyncio())
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP, ATTR_TRANSITION: 2},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.brightness == 128 for member in setup.members)
    assert [member.physical_kelvin for member in setup.members] == [3000, 2800, 3000]
    brightness_commands = [call for call in setup.commands if ATTR_BRIGHTNESS in call]
    assert brightness_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: 128,
            ATTR_TRANSITION: 1 if split else 2,
        },
    ]
    assert len(setup.colour_commands) == 3
    assert all(
        call[ATTR_TRANSITION] == (1 if split else 2) for call in setup.colour_commands
    )
    assert any(not brightness_sent and delay > 0.1 for delay, brightness_sent in delays)
    after_brightness = [delay for delay, brightness_sent in delays if brightness_sent]
    if split:
        assert after_brightness
        assert all(delay == pytest.approx(1.05, abs=0.02) for delay in after_brightness)
    else:
        assert all(delay < 0.1 for delay in after_brightness)


async def test_mixed_explicit_and_computed_commands_keep_individual_timing(hass):
    """Matching values do not erase explicit versus computed split policies."""
    setup = await setup_reported_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: True},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    explicit = setup.members[0]
    await activate_scene(
        hass,
        {
            member.entity_id: {
                "state": STATE_ON,
                **(
                    {ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN}
                    if member is explicit
                    else {}
                ),
            }
            for member in setup.members
        },
        transition=2,
    )

    assert all(member.is_on and member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    assert not any(call["target"] == GROUP for call in setup.commands)
    assert [
        call for call in setup.commands if call["target"] == explicit.entity_id
    ] == [
        {
            "target": explicit.entity_id,
            "service": "turn_on",
            ATTR_BRIGHTNESS: 128,
            ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
            ATTR_TRANSITION: 2,
        },
    ]
    for member in setup.members[1:]:
        adjustments = [
            call
            for call in setup.commands
            if call["target"] == member.entity_id
            and (ATTR_BRIGHTNESS in call or ATTR_COLOR_TEMP_KELVIN in call)
        ]
        assert adjustments == [
            {
                "target": member.entity_id,
                "service": "turn_on",
                ATTR_BRIGHTNESS: 128,
                ATTR_TRANSITION: 1,
            },
            {
                "target": member.entity_id,
                "service": "turn_on",
                ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
                ATTR_TRANSITION: 1,
            },
        ]
