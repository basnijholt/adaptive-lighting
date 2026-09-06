"""Tests for Adaptive Lighting integration."""

import pytest
import voluptuous.error
from homeassistant.components import adaptive_lighting
from homeassistant.components.adaptive_lighting.const import (
    DEFAULT_NAME,
    SERVICE_APPLY,
    SERVICE_CHANGE_SWITCH_SETTINGS,
    SERVICE_SET_MANUAL_CONTROL,
    UNDO_UPDATE_LISTENER,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry


async def test_setup_with_config(hass):
    """Test that we import the config and setup the integration."""
    config = {
        adaptive_lighting.DOMAIN: {
            adaptive_lighting.CONF_NAME: DEFAULT_NAME,
        },
    }
    assert await async_setup_component(hass, adaptive_lighting.DOMAIN, config)
    assert adaptive_lighting.DOMAIN in hass.data


async def test_successful_config_entry(hass):
    """Test that Adaptive Lighting is configured successfully."""
    entry = MockConfigEntry(
        domain=adaptive_lighting.DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state == ConfigEntryState.LOADED

    assert UNDO_UPDATE_LISTENER in hass.data[adaptive_lighting.DOMAIN][entry.entry_id]


async def test_unload_entry(hass):
    """Test removing Adaptive Lighting."""
    entry = MockConfigEntry(
        domain=adaptive_lighting.DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.NOT_LOADED
    assert adaptive_lighting.DOMAIN not in hass.data


async def test_services_survive_entry_unload_and_reload(hass):
    """Test integration services remain registered across entry lifecycle."""
    assert await async_setup_component(hass, adaptive_lighting.DOMAIN, {})
    service_names = (
        SERVICE_APPLY,
        SERVICE_CHANGE_SWITCH_SETTINGS,
        SERVICE_SET_MANUAL_CONTROL,
    )
    registered = {
        name: hass.services.async_services()[adaptive_lighting.DOMAIN][name]
        for name in service_names
    }

    entry = MockConfigEntry(
        domain=adaptive_lighting.DOMAIN,
        data={CONF_NAME: DEFAULT_NAME},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)

    for name in service_names:
        assert (
            hass.services.async_services()[adaptive_lighting.DOMAIN][name]
            is registered[name]
        )

    assert await hass.config_entries.async_setup(entry.entry_id)
    for name in service_names:
        assert (
            hass.services.async_services()[adaptive_lighting.DOMAIN][name]
            is registered[name]
        )


async def test_change_switch_settings_requires_entity_target(hass):
    """Test change_switch_settings rejects a missing entity target."""
    assert await async_setup_component(hass, adaptive_lighting.DOMAIN, {})

    with pytest.raises(
        voluptuous.error.MultipleInvalid,
        match=r"required key not provided.*entity_id",
    ):
        await hass.services.async_call(
            adaptive_lighting.DOMAIN,
            SERVICE_CHANGE_SWITCH_SETTINGS,
            {},
            blocking=True,
        )
