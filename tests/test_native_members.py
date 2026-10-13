"""Native-group members behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_DETECT_NON_HA_CHANGES,
    CONF_TAKE_OVER_CONTROL,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context

from .support.adaptive import track_adaptive_light_calls
from .support.async_helpers import DelayBarrier
from .support.native_lights import GROUP, RIGHT, TARGET_KELVIN, NativeMember
from .support.native_scenarios import setup_native_group, turn_on_member


async def test_native_group_member_activation_repairs_stale_colour(hass):
    """A newly ON member is corrected even though its ON group cache matches."""
    setup = await setup_native_group(hass)
    calls = track_adaptive_light_calls(hass)
    assert setup.right.physical_kelvin == 4000
    assert hass.states.get(GROUP).attributes[ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN

    await turn_on_member(hass)

    assert hass.states.get(GROUP).state == STATE_ON
    assert hass.states.get(RIGHT).attributes[ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN
    assert setup.right.physical_kelvin == TARGET_KELVIN
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == RIGHT
    assert calls[0][ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN
    assert ATTR_BRIGHTNESS not in calls[0]
    assert setup.left.brightness == 80
    assert setup.right.brightness == 110
    assert setup.off_member.is_on is False
    assert setup.off_member.physical_kelvin == 3600
    assert setup.switch.lights == [GROUP]

    calls.clear()
    await setup.switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert calls == []

    setup.group._attr_color_temp_kelvin = 4000
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == GROUP


async def test_native_group_member_brightness_correction_does_not_wake_siblings(hass):
    """Brightness correction targets only the member which has turned on."""
    setup = await setup_native_group(hass)
    await setup.switch.adapt_brightness_switch.async_turn_on()
    calls = track_adaptive_light_calls(hass)
    await turn_on_member(hass)
    assert setup.right.physical_kelvin == TARGET_KELVIN
    assert setup.right.brightness == 128
    assert setup.left.brightness == 80
    assert setup.off_member.is_on is False
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == RIGHT


@pytest.mark.parametrize(
    "guard",
    ["profile_off", "color_off", "group_manual", "removed"],
)
async def test_native_group_member_activation_respects_guards(hass, guard):
    """Disabled, manually controlled, or retired targets receive no repair."""
    setup = await setup_native_group(hass)
    if guard == "profile_off":
        await setup.switch.async_turn_off()
    elif guard == "color_off":
        await setup.switch.adapt_color_switch.async_turn_off()
    elif guard == "group_manual":
        setup.switch.manager.set_manual_control_attributes(GROUP)
    else:
        setup.group.members.remove(setup.right)
        setup.group.async_write_ha_state()
        await hass.async_block_till_done()
    calls = track_adaptive_light_calls(hass)
    await turn_on_member(hass)
    assert calls == []
    assert setup.right.physical_kelvin == 4000
    assert setup.off_member.is_on is False


async def test_native_group_newly_discovered_member_is_observed(hass):
    """Updated HA membership starts tracking a new member without reloading."""
    setup = await setup_native_group(hass)
    new_member = NativeMember("light.new_native_member")
    await hass.data[DATA_COMPONENT].async_add_entities([new_member])
    setup.group.members.append(new_member)
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    calls = track_adaptive_light_calls(hass)
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: new_member.entity_id},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert new_member.physical_kelvin == TARGET_KELVIN
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == new_member.entity_id
    assert setup.switch.lights == [GROUP]
    assert setup.right.is_on is False
    assert setup.off_member.is_on is False


async def test_native_group_member_cache_reports_do_not_trigger_correction(hass):
    """An ON-to-ON report is not an activation and must not add traffic."""
    setup = await setup_native_group(hass)
    setup.right._attr_is_on = True
    await setup.switch.async_turn_off()
    setup.right.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch.async_turn_on(adapt_lights=False)
    calls = track_adaptive_light_calls(hass)
    setup.right._attr_brightness = 111
    setup.right.async_write_ha_state()
    await hass.async_block_till_done()
    assert calls == []
    assert setup.right.physical_kelvin == 4000


async def test_native_group_activation_does_not_misclassify_member_reports(
    hass,
    freezer,
):
    """Group service activation must not mark its independent member reports manual."""
    setup = await setup_native_group(
        hass,
        **{
            CONF_TAKE_OVER_CONTROL: True,
            CONF_DETECT_NON_HA_CHANGES: False,
        },
    )
    await setup.switch.async_turn_off()
    for member in (setup.left, setup.right, setup.off_member):
        member._attr_is_on = False
        member.physical_kelvin = 4000
        member._attr_color_temp_kelvin = TARGET_KELVIN
        member.async_write_ha_state()
    setup.group._attr_is_on = False
    setup.group.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch.async_turn_on(adapt_lights=False)
    # The group has been off longer than the turn-off artifact debounce window.
    freezer.tick(11)
    calls = track_adaptive_light_calls(hass)

    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: GROUP},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert hass.states.get(GROUP).state == STATE_ON
    for member in (setup.left, setup.right, setup.off_member):
        assert member.is_on is True
        assert member.physical_kelvin == TARGET_KELVIN
        assert setup.switch.manager.get_manual_control_attributes(
            member.entity_id,
        ).has_none()
    assert any(
        call[ATTR_ENTITY_ID] == GROUP
        and call.get(ATTR_COLOR_TEMP_KELVIN) == TARGET_KELVIN
        for call in calls
    )


@pytest.mark.parametrize(
    "cancel",
    ["turn_off", "disable_profile", "unload", "remove_member"],
)
async def test_native_group_member_activation_rechecks_after_delay(
    hass,
    monkeypatch,
    cancel,
):
    """A queued repair may not outlive its member or owning profile."""
    setup = await setup_native_group(hass, **{CONF_ADAPT_DELAY: 1})
    delay = DelayBarrier(monkeypatch, setup.switch, "_respond_to_off_to_on_event")
    calls = track_adaptive_light_calls(hass)
    turning_on = hass.async_create_task(turn_on_member(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1
        if cancel == "turn_off":
            await hass.services.async_call(
                "light",
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: RIGHT},
                blocking=True,
            )
        elif cancel == "disable_profile":
            await setup.switch.async_turn_off()
        elif cancel == "unload":
            assert await hass.config_entries.async_unload(setup.entry.entry_id)
        else:
            setup.group.members.remove(setup.right)
            setup.group.async_write_ha_state()
    finally:
        delay.release.set()
        await turning_on
    await hass.async_block_till_done()
    assert calls == []
    assert setup.right.physical_kelvin == 4000
    if cancel == "turn_off":
        assert hass.states.get(RIGHT).state == STATE_OFF
