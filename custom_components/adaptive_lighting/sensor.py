"""Status sensor for the Adaptive Lighting integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

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
from homeassistant.util import slugify

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
    CONF_LIGHTS,
    DOMAIN,
    SIGNAL_STATUS_UPDATED,
    STATUS_INACTIVE,
)


def _expand_light_groups(hass: HomeAssistant, lights: list[str]) -> list[str]:
    expanded: set[str] = set()
    for light in lights:
        state = hass.states.get(light)
        if state is None:
            expanded.add(light)
        elif "entity_id" in state.attributes and not state.attributes.get(
            "is_hue_group",
            False,
        ):
            expanded.update(state.attributes["entity_id"])
        else:
            expanded.add(light)
    return sorted(expanded)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities) -> None:
    """Set up Adaptive Lighting status sensors."""
    manager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    store = hass.data[DOMAIN].setdefault("status_sensors", {})

    data = dict(config_entry.data)
    data.update(config_entry.options)
    lights = _expand_light_groups(hass, data.get(CONF_LIGHTS, []))

    new_entities: list[AdaptiveLightingStatusSensor] = []
    for light in lights:
        if light in store:
            continue
        sensor = AdaptiveLightingStatusSensor(hass, manager, light)
        store[light] = sensor
        new_entities.append(sensor)

    if new_entities:
        async_add_entities(new_entities)


class AdaptiveLightingStatusSensor(SensorEntity):
    """Per-light status sensor for Adaptive Lighting."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, manager, light_entity_id: str) -> None:
        self.hass = hass
        self._manager = manager
        self._light_entity_id = light_entity_id
        self._attr_unique_id = f"{DOMAIN}_status_{slugify(light_entity_id)}"

    @property
    def name(self) -> str:
        state = self.hass.states.get(self._light_entity_id)
        light_name = state.name if state is not None else self._light_entity_id
        return f"Adaptive Lighting Status: {light_name}"

    @property
    def native_value(self) -> str:
        combined = self._manager.get_combined_status(self._light_entity_id)
        return combined.status if combined.status else STATUS_INACTIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        combined = self._manager.get_combined_status(self._light_entity_id)
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

        override_until = None
        if self._manager.get_manual_control_attributes(self._light_entity_id).has_any():
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
            ATTR_STATUS_MANUAL_CONTROL: self._manager.get_manual_control_attributes(
                self._light_entity_id,
            ).has_any(),
            ATTR_STATUS_OVERRIDE_UNTIL: override_until.isoformat()
            if override_until
            else None,
            ATTR_STATUS_LAST_ERROR: combined.last_error,
        }

    @property
    def device_info(self) -> DeviceInfo | None:
        ent_reg = entity_registry.async_get(self.hass)
        entity_entry = ent_reg.async_get(self._light_entity_id)
        if entity_entry and entity_entry.device_id:
            dev_reg = device_registry.async_get(self.hass)
            device_entry = dev_reg.async_get(entity_entry.device_id)
            if device_entry and device_entry.identifiers:
                return DeviceInfo(identifiers=device_entry.identifiers)
        return None

    async def async_added_to_hass(self) -> None:
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
            self.async_write_ha_state()
