"""Adaptive Lighting integration in Home Assistant (CDiT fork)."""

import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_LUX_SENSOR,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "number", "sensor"]

# unique_id suffix(es) that this fork no longer creates. Any entity in the
# registry whose unique_id ends with one of these strings AND that is owned
# by an Adaptive Lighting config entry is a leftover from upstream and is
# removed on first setup (spec R9, design D12).
_REMOVED_UNIQUE_ID_SUFFIXES = ("_sleep_mode",)


# UI-only: an `adaptive_lighting:` block in configuration.yaml is not imported.
# HA logs that the integration is set up from the UI instead.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _remove_orphan_sleep_entities(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """Remove sleep-mode switch entities left behind by upstream AL.

    Idempotent: subsequent runs find nothing and emit no log lines. Only
    removes entities whose config_entry_id matches the current entry, so
    foreign entities matching the name pattern are not touched.
    Spec R9, design D12.
    """
    registry = er.async_get(hass)
    entries_to_remove = [
        entry.entity_id
        for entry in registry.entities.values()
        if entry.config_entry_id == config_entry.entry_id
        and any(
            entry.unique_id.endswith(suffix) for suffix in _REMOVED_UNIQUE_ID_SUFFIXES
        )
    ]
    for entity_id in entries_to_remove:
        _LOGGER.info(
            "Removing orphan entity %s left behind by upstream Adaptive Lighting "
            "(sleep mode is not supported in the CDiT fork).",
            entity_id,
        )
        registry.async_remove(entity_id)


_LUX_CONDITIONAL_SUFFIXES = ("_ambient_lux", "_lux_reduction")


def _remove_orphan_lux_sensors(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """Remove lux output sensors when lux_sensor is no longer configured."""
    has_lux = bool(
        config_entry.options.get(CONF_LUX_SENSOR)
        or config_entry.data.get(CONF_LUX_SENSOR),
    )
    if has_lux:
        return
    registry = er.async_get(hass)
    for entry in list(registry.entities.values()):
        if entry.config_entry_id == config_entry.entry_id and any(
            entry.unique_id.endswith(s) for s in _LUX_CONDITIONAL_SUFFIXES
        ):
            _LOGGER.info(
                "Removing orphan lux sensor %s (lux_sensor no longer configured).",
                entry.entity_id,
            )
            registry.async_remove(entry.entity_id)


async def async_migrate_entry(
    hass: HomeAssistant,  # noqa: ARG001 — signature required by HA
    config_entry: ConfigEntry,
) -> bool:
    """Reject older config-entry versions with a friendly recreate message.

    Spec R8 + design D4: this fork deliberately does not migrate upstream
    entries. Define a migration handler so HA routes version mismatches
    here (instead of logging the generic "Migration handler not found")
    and surface a `ConfigEntryError` whose message tells the user what to
    do.
    """
    msg = (
        f"Adaptive Lighting v{CONFIG_ENTRY_VERSION} (CDiT fork) is incompatible "
        f"with the existing config entry (version {config_entry.version}). "
        "Delete the entry and recreate it from Settings → Devices & Services."
    )
    raise ConfigEntryError(msg)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the component.

    Note: `OptionsFlowWithReload` (in config_flow.py) handles reload-on-save
    automatically — HA rejects `config_entry.add_update_listener` when used
    with `OptionsFlowWithReload`, so we deliberately do NOT register one.
    """
    _remove_orphan_sleep_entities(hass, config_entry)
    _remove_orphan_lux_sensors(hass, config_entry)

    data = hass.data.setdefault(DOMAIN, {})

    data[config_entry.entry_id] = {
        # Cache slot the master switch publishes to after each curve tick
        # (add-output-sensors / D2). Initialized to None so any sensor that
        # reads before the first tick sees a sentinel rather than a KeyError.
        "outputs": None,
    }
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry,
        PLATFORMS,
    )
    data = hass.data[DOMAIN]
    if unload_ok:
        data.pop(config_entry.entry_id, None)

    if len(data) == 1 and ATTR_ADAPTIVE_LIGHTING_MANAGER in data:
        # no more config_entries
        manager = data.pop(ATTR_ADAPTIVE_LIGHTING_MANAGER)
        manager.disable()

    if not data:
        hass.data.pop(DOMAIN)

    return unload_ok
