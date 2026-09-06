"""Tests for Adaptive Lighting diagnostics."""

import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    AdaptationData,
    LightControlAttributes,
    _create_service_call_data_iterator,
)
from homeassistant.components.adaptive_lighting.const import (
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_AUTORESET_CONTROL,
    CONF_INTERCEPT,
    CONF_MANUAL_CONTROL,
    DOMAIN,
    SERVICE_SET_MANUAL_CONTROL,
)
from homeassistant.components.adaptive_lighting.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    SERVICE_TURN_ON,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SERVICE_DATA,
    CONF_LIGHTS,
    CONF_NAME,
    EVENT_CALL_SERVICE,
    EVENT_STATE_CHANGED,
    STATE_OFF,
    STATE_UNAVAILABLE,
)
from homeassistant.core import State

from tests.common import MockConfigEntry
from tests.components.diagnostics import get_diagnostics_for_config_entry

from .test_switch import (
    ENTITY_LIGHT_1,
    ENTITY_LIGHT_2,
    ENTITY_LIGHT_3,
    setup_lights,
)


@pytest.fixture
async def cleanup_diagnostics(hass):
    """Cancel integration tasks created by diagnostics fixtures."""
    yield
    manager = hass.data.get(DOMAIN, {}).get(ATTR_ADAPTIVE_LIGHTING_MANAGER)
    if manager is None:
        return
    for timer in manager.auto_reset_manual_control_timers.values():
        timer.cancel()
    for timer in manager.transition_timers.values():
        timer.cancel()
    for task in manager.adaptation_tasks:
        task.cancel()


async def _setup_entry(hass, name, lights, **data):
    """Set up a real Adaptive Lighting config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: name,
            CONF_LIGHTS: lights,
            CONF_INTERCEPT: False,
            **data,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry, hass.data[DOMAIN][entry.entry_id][SWITCH_DOMAIN]


async def test_config_entry_diagnostics_reports_allowlisted_current_facts(
    hass,
    hass_client,
    cleanup_diagnostics,
):
    """Diagnostics report current selected-profile facts without identifiers."""
    await setup_lights(hass)
    entry, switch = await _setup_entry(
        hass,
        "Private Upstairs Profile",
        [ENTITY_LIGHT_1, ENTITY_LIGHT_2],
        **{CONF_AUTORESET_CONTROL: 60},
    )
    other_entry, _ = await _setup_entry(
        hass,
        "Private Basement Profile",
        [ENTITY_LIGHT_3],
    )

    await switch.adapt_color_switch.async_turn_off()
    await switch.sleep_mode_switch.async_turn_on()
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {
            ATTR_ENTITY_ID: switch.entity_id,
            CONF_LIGHTS: [ENTITY_LIGHT_1],
            CONF_MANUAL_CONTROL: "brightness",
        },
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {
            ATTR_ENTITY_ID: switch.entity_id,
            CONF_LIGHTS: [ENTITY_LIGHT_2],
            CONF_MANUAL_CONTROL: "color",
        },
        blocking=True,
    )
    hass.states.async_set(
        ENTITY_LIGHT_2,
        STATE_UNAVAILABLE,
        {"friendly_name": "Private Bedside Lamp", "room": "Private Bedroom"},
    )
    await hass.async_block_till_done()

    manager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    assert manager.get_manual_control_attributes(ENTITY_LIGHT_1) == (
        LightControlAttributes.BRIGHTNESS
    )
    manager.last_service_data[ENTITY_LIGHT_1] = {
        ATTR_ENTITY_ID: ENTITY_LIGHT_1,
        ATTR_BRIGHTNESS: 123,
        ATTR_COLOR_TEMP_KELVIN: 3456,
        ATTR_RGB_COLOR: (12, 34, 56),
        ATTR_TRANSITION: 4.5,
        "context_id": "private-context-id",
        "friendly_name": "Private Bedside Lamp",
    }
    manager.last_service_data.pop(ENTITY_LIGHT_2, None)

    result = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert result["loaded"] is True
    assert result["profile_switches"] == {
        "profile": True,
        "adapt_brightness": True,
        "adapt_color": False,
        "sleep_mode": True,
    }
    assert result["manager_fact_scope"] == "global_shared_across_profiles"
    assert list(result["lights"]) == ["light_1", "light_2"]
    assert result["lights"]["light_1"]["state"] == "on"
    assert result["lights"]["light_1"]["global_manager_manual_control"] == {
        "brightness": True,
        "color": False,
    }
    assert result["lights"]["light_1"][
        "global_manager_autoreset_seconds"
    ] == pytest.approx(60, abs=2)
    assert result["lights"]["light_1"]["global_manager_last_adaptation_values"] == {
        ATTR_BRIGHTNESS: 123,
        ATTR_COLOR_TEMP_KELVIN: 3456,
        ATTR_RGB_COLOR: [12, 34, 56],
        ATTR_TRANSITION: 4.5,
    }
    assert result["lights"]["light_2"] == {
        "state": STATE_UNAVAILABLE,
        "global_manager_manual_control": {
            "brightness": False,
            "color": True,
        },
        "global_manager_autoreset_seconds": pytest.approx(60, abs=2),
        "global_manager_last_adaptation_values": None,
    }

    serialized = json.dumps(result, sort_keys=True)
    for sensitive_value in (
        entry.entry_id,
        other_entry.entry_id,
        ENTITY_LIGHT_1,
        ENTITY_LIGHT_2,
        ENTITY_LIGHT_3,
        "Private Upstairs Profile",
        "Private Basement Profile",
        "Private Bedside Lamp",
        "Private Bedroom",
        "private-context-id",
    ):
        assert sensitive_value not in serialized


async def test_diagnostics_labels_accumulated_partial_adaptation_values(
    hass,
    cleanup_diagnostics,
):
    """Diagnostics do not describe merged per-attribute history as one command."""
    await setup_lights(hass)
    entry, switch = await _setup_entry(
        hass,
        "Private Profile",
        [ENTITY_LIGHT_1],
    )
    commands = [
        {
            ATTR_ENTITY_ID: ENTITY_LIGHT_1,
            ATTR_BRIGHTNESS: 100,
            ATTR_RGB_COLOR: (12, 34, 56),
            ATTR_TRANSITION: 2,
        },
        {ATTR_ENTITY_ID: ENTITY_LIGHT_1, ATTR_BRIGHTNESS: 180},
        {ATTR_ENTITY_ID: ENTITY_LIGHT_1, ATTR_COLOR_TEMP_KELVIN: 3500},
    ]
    call_events = []
    remove_listener = hass.bus.async_listen(EVENT_CALL_SERVICE, call_events.append)

    await switch._execute_adaptation_calls(
        AdaptationData(
            entity_id=ENTITY_LIGHT_1,
            context=switch.create_context("diagnostics_test"),
            sleep_time=0,
            service_call_datas=_create_service_call_data_iterator(
                hass,
                commands,
                filter_by_state=False,
            ),
            force=True,
            max_length=len(commands),
            attributes=LightControlAttributes.ALL,
        ),
    )
    await hass.async_block_till_done()
    remove_listener()

    actual_commands = [
        event.data[ATTR_SERVICE_DATA]
        for event in call_events
        if event.data["domain"] == LIGHT_DOMAIN
        and event.data["service"] == SERVICE_TURN_ON
    ]
    assert actual_commands == commands

    result = await async_get_config_entry_diagnostics(hass, entry)
    light = result["lights"]["light_1"]
    assert "global_manager_last_sent_target" not in light
    assert light["global_manager_last_adaptation_values"] == {
        ATTR_BRIGHTNESS: 180,
        ATTR_COLOR_TEMP_KELVIN: 3500,
        ATTR_RGB_COLOR: [12, 34, 56],
        ATTR_TRANSITION: 2,
    }


async def test_diagnostics_preserves_restored_off_profile_tracked_group(hass):
    """Diagnostics report tracked targets without refreshing late groups."""
    await setup_lights(hass)
    group = "light.private_late_group"
    members = [ENTITY_LIGHT_1, ENTITY_LIGHT_2]
    with patch(
        "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
        return_value=State("switch.restored", STATE_OFF),
    ):
        entry, switch = await _setup_entry(
            hass,
            "Private Restored Profile",
            [group],
        )
    assert not switch.is_on
    assert switch.lights == [group]

    hass.states.async_set(
        group,
        STATE_UNAVAILABLE,
        {ATTR_ENTITY_ID: members, "friendly_name": "Private Late Group"},
    )
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    manager_lights_before = set(manager.lights)
    reset_times_before = dict(manager.auto_reset_manual_control_times)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["lights"] == {
        "light_1": {
            "state": STATE_UNAVAILABLE,
            "global_manager_manual_control": {
                "brightness": False,
                "color": False,
            },
            "global_manager_autoreset_seconds": None,
            "global_manager_last_adaptation_values": None,
        },
    }
    assert switch.lights == [group]
    assert manager.lights == manager_lights_before
    assert manager.auto_reset_manual_control_times == reset_times_before
    assert group not in json.dumps(result)


async def test_diagnostics_handles_missing_states_and_unload_without_side_effects(
    hass,
):
    """Diagnostics normalize states and never change live integration state."""
    await setup_lights(hass)
    entry, switch = await _setup_entry(
        hass,
        "Private Profile",
        [ENTITY_LIGHT_1, ENTITY_LIGHT_2, ENTITY_LIGHT_3, "light.private_missing"],
    )
    hass.states.async_set(ENTITY_LIGHT_2, STATE_OFF)
    hass.states.async_set(ENTITY_LIGHT_3, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    manager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    manual_control_before = dict(manager.manual_control)
    last_service_data_before = deepcopy(manager.last_service_data)
    timers_before = dict(manager.auto_reset_manual_control_timers)
    switch_states_before = (
        switch.is_on,
        switch.adapt_brightness_switch.is_on,
        switch.adapt_color_switch.is_on,
        switch.sleep_mode_switch.is_on,
    )
    service_events = []
    state_events = []
    remove_service_listener = hass.bus.async_listen(
        EVENT_CALL_SERVICE,
        service_events.append,
    )
    remove_state_listener = hass.bus.async_listen(
        EVENT_STATE_CHANGED,
        state_events.append,
    )

    result = await async_get_config_entry_diagnostics(hass, entry)
    await hass.async_block_till_done()
    remove_service_listener()
    remove_state_listener()

    assert [light["state"] for light in result["lights"].values()] == [
        "on",
        STATE_OFF,
        STATE_UNAVAILABLE,
        "missing",
    ]
    assert json.dumps(result)
    assert not service_events
    assert not state_events
    assert manager.manual_control == manual_control_before
    assert manager.last_service_data == last_service_data_before
    assert manager.auto_reset_manual_control_timers == timers_before
    assert (
        switch.is_on,
        switch.adapt_brightness_switch.is_on,
        switch.adapt_color_switch.is_on,
        switch.sleep_mode_switch.is_on,
    ) == switch_states_before

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await async_get_config_entry_diagnostics(hass, entry) == {"loaded": False}
