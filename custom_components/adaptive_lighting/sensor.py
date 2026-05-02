"""Status sensor for the Adaptive Lighting integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
)
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from homeassistant.util import slugify

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    ATTR_STATUS_LAST_ERROR,
    ATTR_STATUS_MANUAL_CONTROL,
    ATTR_STATUS_OVERRIDE_UNTIL,
    ATTR_STATUS_PROFILES,
    ATTR_STATUS_REASON,
    ATTR_STATUS_SINCE,
    ATTR_STATUS_SOURCE,
    ATTR_STATUS_TARGET,
    CONF_ENABLE_DIAGNOSTIC_SENSORS,
    CONF_LIGHTS,
    DEFAULT_ENABLE_DIAGNOSTIC_SENSORS,
    DOMAIN,
    SIGNAL_STATUS_UPDATED,
    LightStatus,
    LightStatusInfo,
)
from .helpers import expand_light_groups, get_friendly_name


def ensure_status_sensors_enabled(hass: HomeAssistant, entry_id: str) -> None:
    """Enable any disabled status sensors for a config entry."""
    ent_reg = entity_registry.async_get(hass)
    for entry in entity_registry.async_entries_for_config_entry(
        ent_reg,
        entry_id,
    ):
        if (
            entry.domain == "sensor"
            and entry.platform == DOMAIN
            and entry.entity_id.startswith("sensor.adaptive_lighting_status_")
            and entry.disabled_by is not None
            and entry.disabled_by != RegistryEntryDisabler.USER
        ):
            ent_reg.async_update_entity(entry.entity_id, disabled_by=None)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adaptive Lighting status sensors."""
    options = config_entry.options
    data = config_entry.data
    if not options.get(
        CONF_ENABLE_DIAGNOSTIC_SENSORS,
        data.get(CONF_ENABLE_DIAGNOSTIC_SENSORS, DEFAULT_ENABLE_DIAGNOSTIC_SENSORS),
    ):
        return
    manager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    store = hass.data[DOMAIN].setdefault("status_sensors", {})
    entry_lights = hass.data[DOMAIN].setdefault("status_sensor_entry_lights", {})

    lights = expand_light_groups(
        hass,
        options.get(CONF_LIGHTS, data.get(CONF_LIGHTS, [])),
    )

    ensure_status_sensors_enabled(hass, config_entry.entry_id)

    entry_lights[config_entry.entry_id] = set(lights)

    new_entities: list[AdaptiveLightingStatusSensor] = []
    for light in lights:
        if light in store:
            continue
        sensor = AdaptiveLightingStatusSensor(hass, manager, light)
        store[light] = sensor
        new_entities.append(sensor)

    if new_entities:
        async_add_entities(new_entities)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Adaptive Lighting status sensors."""
    domain_data = hass.data.get(DOMAIN, {})
    entry_lights: dict[str, set[str]] = domain_data.get(
        "status_sensor_entry_lights",
        {},
    )
    my_lights = entry_lights.pop(config_entry.entry_id, set())

    still_referenced: set[str] = set()
    for other_lights in entry_lights.values():
        still_referenced |= other_lights

    store: dict[str, AdaptiveLightingStatusSensor] = domain_data.get(
        "status_sensors",
        {},
    )
    for light in my_lights - still_referenced:
        store.pop(light, None)

    return True


class AdaptiveLightingStatusSensor(SensorEntity):
    """Per-light status sensor for Adaptive Lighting."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, manager, light_entity_id: str) -> None:
        """Initialize the per-light status sensor."""
        self.hass = hass
        self._manager = manager
        self._light_entity_id = light_entity_id
        self._attr_unique_id = f"{DOMAIN}_status_{slugify(light_entity_id)}"
        self._combined: LightStatusInfo | None = None

    def _get_combined(self) -> LightStatusInfo:
        if self._combined is None:
            self._combined = self._manager.get_combined_status(self._light_entity_id)
        return self._combined

    @property
    def name(self) -> str:
        """Return the sensor name."""
        light_name = get_friendly_name(self.hass, self._light_entity_id)
        return f"Adaptive Lighting Status: {light_name}"

    @property
    def native_value(self) -> str:
        """Return the current combined status."""
        combined = self._get_combined()
        return combined.status if combined.status else LightStatus.INACTIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed status attributes."""
        combined = self._get_combined()
        statuses = self._manager.get_light_statuses(self._light_entity_id)

        profile_statuses: dict[str, Any] = {}
        for source, info in statuses.items():
            profile_statuses[source] = {
                "status": info.status,
                "since": info.since.isoformat() if info.since else None,
                "reason": info.reason,
                "last_error": info.last_error,
            }

        target_attrs = {}
        last_service_data = self._manager.last_service_data.get(self._light_entity_id)
        if last_service_data:
            for attr in (
                ATTR_BRIGHTNESS,
                ATTR_COLOR_TEMP_KELVIN,
                ATTR_RGB_COLOR,
                ATTR_XY_COLOR,
                ATTR_HS_COLOR,
            ):
                if attr in last_service_data:
                    target_attrs[attr] = last_service_data[attr]

        manual_control_attrs = self._manager.get_manual_control_attributes(
            self._light_entity_id,
        )
        is_manually_controlled = manual_control_attrs.has_any()
        override_until = None
        if is_manually_controlled:
            timer = self._manager.auto_reset_manual_control_timers.get(
                self._light_entity_id,
            )
            if timer is not None and (remaining := timer.remaining_time()) > 0:
                override_until = dt_util.utcnow() + timedelta(seconds=remaining)

        return {
            "light_entity_id": self._light_entity_id,
            ATTR_STATUS_SINCE: combined.since.isoformat() if combined.since else None,
            ATTR_STATUS_REASON: combined.reason,
            ATTR_STATUS_SOURCE: combined.source,
            ATTR_STATUS_PROFILES: profile_statuses,
            ATTR_STATUS_TARGET: target_attrs or None,
            ATTR_STATUS_MANUAL_CONTROL: is_manually_controlled,
            ATTR_STATUS_OVERRIDE_UNTIL: (
                override_until.isoformat() if override_until else None
            ),
            ATTR_STATUS_LAST_ERROR: combined.last_error,
        }

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the linked light device info when available."""
        ent_reg = entity_registry.async_get(self.hass)
        entity_entry = ent_reg.async_get(self._light_entity_id)
        if entity_entry and entity_entry.device_id:
            dev_reg = device_registry.async_get(self.hass)
            device_entry = dev_reg.async_get(entity_entry.device_id)
            if device_entry and device_entry.identifiers:
                return DeviceInfo(identifiers=device_entry.identifiers)
        return None

    async def async_added_to_hass(self) -> None:
        """Register status update listeners."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATUS_UPDATED,
                self._handle_status_update,
            ),
        )

    @callback
    def _handle_status_update(self, light_entity_id: str) -> None:
        if light_entity_id == self._light_entity_id:
            self._combined = self._manager.get_combined_status(light_entity_id)
            self.async_write_ha_state()
