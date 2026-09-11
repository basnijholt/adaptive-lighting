"""Sensor platform for the Adaptive Lighting integration (CDiT fork).

Each config entry exposes three read-only output sensors that publish the
curve's current target values + the actual sun elevation:

- ``sensor.<profile>_output_brightness``    (% — from self._settings["brightness_pct"])
- ``sensor.<profile>_output_color_temp``    (K — from self._settings["color_temp_kelvin"])
- ``sensor.<profile>_sun_elevation``        (° — from sun.sun.attributes["elevation"])

The sensors update via a per-entry dispatcher signal fired by the master
switch after every curve evaluation. They are pure readers — no curve math
runs in the sensor class. See ``add-output-sensors/design.md`` decisions
2, 3, and 8.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_LUX_SENSOR, DOMAIN, OUTPUT_SENSORS, SIGNAL_OUTPUTS_UPDATED

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the output sensors for this config entry."""
    has_lux = bool(
        config_entry.options.get(CONF_LUX_SENSOR)
        or config_entry.data.get(CONF_LUX_SENSOR),
    )
    entities = [
        AdaptiveOutputSensor(
            hass=hass,
            entry=config_entry,
            output_key=row["key"],
            unit=row["unit"],
            icon=row["icon"],
        )
        for row in OUTPUT_SENSORS
        if not row.get("conditional") or has_lux
    ]
    async_add_entities(entities)


# Only ambient_lux maps onto a standard HA device class. The rest are AL curve
# outputs with no equivalent, and claiming one would break their unit handling.
_SENSOR_DEVICE_CLASSES = {"ambient_lux": SensorDeviceClass.ILLUMINANCE}


class AdaptiveOutputSensor(SensorEntity):
    """One read-only output value from an AL profile's curve tick."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        entry: ConfigEntry,
        output_key: str,
        unit: str,
        icon: str,
    ) -> None:
        """Initialise a single output sensor entity."""
        self._hass = hass
        self._entry = entry
        self._output_key = output_key
        # No _attr_name: Entity._name_internal returns it before it ever
        # consults translation_key, which would leave every translation dead.
        self._attr_translation_key = output_key
        self._attr_device_class = _SENSOR_DEVICE_CLASSES.get(output_key)
        self._attr_unique_id = f"{entry.entry_id}_{output_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        # Renders as `unknown` until the first dispatcher signal arrives.
        # Do NOT use RestoreEntity — restored values would be stale (the
        # sun has moved); `unknown` for one tick is honest.
        self._attr_native_value = None

    @property
    def device_info(self) -> DeviceInfo:
        """Group with the profile's switches and number entities."""
        profile_name = self._entry.data.get("name") or self._entry.title
        return DeviceInfo(
            identifiers={(DOMAIN, profile_name)},
            name=profile_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to the per-entry outputs-updated dispatcher signal."""
        await super().async_added_to_hass()
        signal = SIGNAL_OUTPUTS_UPDATED.format(entry_id=self._entry.entry_id)
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass,
                signal,
                self._handle_outputs_updated,
            ),
        )

    @callback
    def _handle_outputs_updated(self) -> None:
        """Read this sensor's value from the cache and write state."""
        outputs = (
            self._hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("outputs")
        )
        if not outputs:
            # Early signal (e.g., setup race) — leave state as unknown.
            return
        self._attr_native_value = outputs.get(self._output_key)
        self.async_write_ha_state()
