"""Native-group traffic behavior at HA and device boundaries."""

# pylint: disable=protected-access
import json
from collections import Counter

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_COLOR_TEMP,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
)
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import ATTR_ENTITY_ID, CONF_LIGHTS, SERVICE_TURN_ON, STATE_ON
from homeassistant.core import Context
from homeassistant.setup import async_setup_component

from .support.adaptive import setup_switch, track_adaptive_light_calls
from .support.native_lights import TARGET_KELVIN, NativeGroup, NativeMember


@pytest.mark.parametrize(
    "group_sizes",
    [(3,), (14,), (3, 14)],
    ids=["one_group_3_bulbs", "one_group_14_bulbs", "living_shape_2_groups_17_bulbs"],
)
async def test_native_whole_area_activation_keeps_colour_corrections_grouped(
    hass,
    record_property,
    group_sizes,
):
    """Correct every lit bulb with one colour adaptation per native group."""
    assert await async_setup_component(hass, "light", {})
    groups, members = [], []
    for group_index, size in enumerate(group_sizes):
        group_members = [
            NativeMember(f"light.area_{group_index}_member_{member_index}")
            for member_index in range(size)
        ]
        for member_index, member in enumerate(group_members):
            member._attr_brightness = 30 + member_index * 7
        group = NativeGroup(group_members)
        group.entity_id = f"light.area_group_{group_index}"
        group._attr_is_on = False
        groups.append(group)
        members.extend(group_members)
    # A separate OFF light proves that the original area target is respected.
    control = NativeMember("light.outside_area_control")
    await hass.data[DATA_COMPONENT].async_add_entities([*members, *groups, control])
    group_ids = [group.entity_id for group in groups]
    member_ids = {member.entity_id for member in members}
    _, switch = await setup_switch(
        hass,
        {
            CONF_LIGHTS: group_ids,
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_COLOR_TEMP: TARGET_KELVIN,
            CONF_MAX_COLOR_TEMP: TARGET_KELVIN,
            CONF_SLEEP_COLOR_TEMP: TARGET_KELVIN,
            CONF_SKIP_REDUNDANT_COMMANDS: True,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    await switch.adapt_brightness_switch.async_turn_off()
    await hass.async_block_till_done()
    original_brightness = {m.entity_id: m.brightness for m in members}
    assert all(
        not member.is_on and member.physical_kelvin == 4000 for member in members
    )
    calls = track_adaptive_light_calls(hass)

    # One area action invokes the real light service on each native group.
    # Group and member reports use the existing native entity model, including
    # independent member contexts and matching optimistic colour caches.
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: group_ids},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    activation_calls = list(calls)
    calls.clear()
    await switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    periodic_calls = list(calls)

    counts = Counter(call[ATTR_ENTITY_ID] for call in activation_calls)
    evidence = {
        "group_sizes": list(group_sizes),
        "bulb_count": len(members),
        "expected_correction_count": len(groups),
        "actual_correction_count": len(activation_calls),
        "group_corrections": sum(counts[group_id] for group_id in group_ids),
        "member_corrections": sum(counts[member_id] for member_id in member_ids),
        "activation_calls": activation_calls,
        "unchanged_periodic_calls": periodic_calls,
        "all_physical_colours_correct": all(
            m.physical_kelvin == TARGET_KELVIN for m in members
        ),
        "brightness_preserved": all(
            m.brightness == original_brightness[m.entity_id] for m in members
        ),
        "outside_control_still_off": not control.is_on,
    }
    record_property("traffic_evidence", json.dumps(evidence, sort_keys=True))

    # Verify useful adaptation and safety before checking the traffic budget:
    # simply suppressing all corrections must not satisfy this regression.
    assert evidence["all_physical_colours_correct"], evidence
    assert evidence["brightness_preserved"], evidence
    assert evidence["outside_control_still_off"], evidence
    assert all(hass.states.get(group_id).state == STATE_ON for group_id in group_ids)
    assert all(ATTR_BRIGHTNESS not in call for call in activation_calls)
    assert all(
        call.get(ATTR_COLOR_TEMP_KELVIN) == TARGET_KELVIN for call in activation_calls
    )
    assert switch.lights == sorted(group_ids)
    assert periodic_calls == [], evidence
    assert counts == Counter(dict.fromkeys(group_ids, 1)), evidence
