"""Adaptive Lighting integration in Home-Assistant."""

import logging
from functools import partial
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_SOURCE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import service

from .const import (
    _DOMAIN_SCHEMA,  # pyright: ignore[reportPrivateUsage]
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_NAME,
    DOMAIN,
    SERVICE_APPLY,
    SERVICE_CHANGE_SWITCH_SETTINGS,
    SERVICE_SET_MANUAL_CONTROL,
    SET_MANUAL_CONTROL_SCHEMA,
    UNDO_UPDATE_LISTENER,
    apply_service_schema,
    change_switch_settings_schema,
)
from .switch import (
    handle_apply_service,
    handle_change_switch_settings,
    handle_set_manual_control_service,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch"]


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


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Import integration from config."""
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_APPLY,
        service_func=partial(handle_apply_service, hass),
        schema=apply_service_schema(),
    )

    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_SET_MANUAL_CONTROL,
        service_func=partial(handle_set_manual_control_service, hass),
        schema=SET_MANUAL_CONTROL_SCHEMA,
    )

    if register_platform_service := getattr(
        service,
        "async_register_platform_entity_service",
        None,
    ):
        register_platform_service(
            hass,
            DOMAIN,
            SERVICE_CHANGE_SWITCH_SETTINGS,
            entity_domain=Platform.SWITCH,
            func=handle_change_switch_settings,
            schema=change_switch_settings_schema(),
        )

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
    if not unload_ok:
        return False

    data = hass.data[DOMAIN]
    data.pop(config_entry.entry_id)[UNDO_UPDATE_LISTENER]()

    # Keys that are not config entries; "__yaml__" must outlive the entries so
    # a later reload can tell imported YAML switches from deleted ones.
    non_entry_keys = {ATTR_ADAPTIVE_LIGHTING_MANAGER, "__yaml__"}
    if ATTR_ADAPTIVE_LIGHTING_MANAGER in data and not set(data) - non_entry_keys:
        # no more config_entries
        manager = data.pop(ATTR_ADAPTIVE_LIGHTING_MANAGER)
        manager.disable()

    if not data:
        hass.data.pop(DOMAIN)

    return unload_ok
