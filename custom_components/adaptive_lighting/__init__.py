"""Adaptive Lighting integration in Home-Assistant."""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_SOURCE
from homeassistant.core import Event, HomeAssistant

from .const import (
    _DOMAIN_SCHEMA,  # pyright: ignore[reportPrivateUsage]
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_ENABLE_DIAGNOSTIC_SENSORS,
    CONF_NAME,
    DEFAULT_ENABLE_DIAGNOSTIC_SENSORS,
    DOMAIN,
    UNDO_UPDATE_LISTENER,
)
from .sensor import ensure_status_sensors_enabled
from .switch import AdaptiveLightingManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "sensor"]


def _all_unique_names(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate that all entities have a unique profile name."""
    hosts = [device[CONF_NAME] for device in value]
    schema = vol.Schema(vol.Unique())
    schema(hosts)
    return value


CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [_DOMAIN_SCHEMA], _all_unique_names)},
    extra=vol.ALLOW_EXTRA,
)


async def reload_configuration_yaml(event: Event) -> None:
    """Reload configuration.yaml."""
    hass: HomeAssistant | None = event.data.get("hass")
    if hass is not None:
        await hass.services.async_call("homeassistant", "check_config", {})
    else:
        _LOGGER.error("HomeAssistant instance not found in event data.")


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Import integration from config."""
    if DOMAIN in config:
        for entry in config[DOMAIN]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={CONF_SOURCE: SOURCE_IMPORT},
                    data=entry,
                ),
            )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the component."""
    data = hass.data.setdefault(DOMAIN, {})
    if ATTR_ADAPTIVE_LIGHTING_MANAGER not in data:
        data[ATTR_ADAPTIVE_LIGHTING_MANAGER] = AdaptiveLightingManager(hass)

    if (
        config_entry.options.get(CONF_ENABLE_DIAGNOSTIC_SENSORS)
        == DEFAULT_ENABLE_DIAGNOSTIC_SENSORS
        and CONF_ENABLE_DIAGNOSTIC_SENSORS in config_entry.data
    ):
        enable_diagnostic_sensors = config_entry.data[CONF_ENABLE_DIAGNOSTIC_SENSORS]
    else:
        enable_diagnostic_sensors = config_entry.options.get(
            CONF_ENABLE_DIAGNOSTIC_SENSORS,
            DEFAULT_ENABLE_DIAGNOSTIC_SENSORS,
        )

    if enable_diagnostic_sensors and config_entry.pref_disable_new_entities:
        hass.config_entries.async_update_entry(
            config_entry,
            pref_disable_new_entities=False,
        )
    if enable_diagnostic_sensors:
        ensure_status_sensors_enabled(hass, config_entry.entry_id)

    # This will reload any changes the user made to any YAML configurations.
    # Called during 'quick reload' or hass.reload_config_entry
    hass.bus.async_listen("hass.config.entry_updated", reload_configuration_yaml)

    undo_listener = config_entry.add_update_listener(async_update_options)
    data[config_entry.entry_id] = {UNDO_UPDATE_LISTENER: undo_listener}
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(
        config_entry,
        "switch",
    )
    unload_ok = unload_ok and await hass.config_entries.async_forward_entry_unload(
        config_entry,
        "sensor",
    )
    data = hass.data[DOMAIN]
    data[config_entry.entry_id][UNDO_UPDATE_LISTENER]()
    if unload_ok:
        data.pop(config_entry.entry_id)

    if len(data) == 1 and ATTR_ADAPTIVE_LIGHTING_MANAGER in data:
        # no more config_entries
        manager = data.pop(ATTR_ADAPTIVE_LIGHTING_MANAGER)
        manager.disable()

    if not data:
        hass.data.pop(DOMAIN)

    return unload_ok
