"""A per-switch intensity dial for Adaptive Lighting.

Adds one number entity per configuration, sitting alongside the Sleep Mode /
Adapt Brightness / Adapt Color switches on the same device:

    number.adaptive_lighting_intensity_<name>

100% is the normal adaptive behaviour. 0% is the switch's floor, set by the
``intensity_floor`` option: its sleep settings (``sleep_brightness`` and
``sleep_color_temp``) by default, or its ``min_brightness``/``min_color_temp``.
Anything in between blends the two, recomputed continuously so the sun still
moves the light through a smaller range. At 0%, the target stays at the endpoint.

The value survives restarts via RestoreEntity, and is re-applied to the switch
whenever it changes so the lights follow immediately instead of waiting for the
next adaptation interval.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import (
    CONF_NAME,
    DEFAULT_INTENSITY,
    DOMAIN,
    ICON_INTENSITY,
    INTENSITY_NUMBER,
    PENDING_INTENSITY,
)
from .switch import validate

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
    """Set up the intensity number for one Adaptive Lighting configuration."""
    data = hass.data[DOMAIN]
    number = AdaptiveIntensityNumber(hass, config_entry)
    data[config_entry.entry_id][INTENSITY_NUMBER] = number
    async_add_entities([number], update_before_add=True)


class AdaptiveIntensityNumber(NumberEntity, RestoreEntity):
    """A 0-100% dial between the adaptive settings and the switch's floor."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False
    # Matches the sibling switches: the device supplies "Adaptive Lighting:
    # <name>" and this entity contributes only "Intensity".
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the intensity number."""
        self.hass = hass
        self._config_entry = config_entry
        config = validate(config_entry)
        self._config_name = config[CONF_NAME]
        self._which = "Intensity"
        self._attr_unique_id = f"{self._config_name}_{slugify(self._which)}"
        self._attr_name = self._which
        self._attr_icon = ICON_INTENSITY
        self._value: float = DEFAULT_INTENSITY

    @property
    def native_value(self) -> float:
        """Return the current intensity."""
        return self._value

    @property
    def device_info(self) -> DeviceInfo:
        """Group with the other entities for this configuration."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_name)},
            name=f"Adaptive Lighting: {self._config_name}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _switch(self) -> Any | None:
        """The AdaptiveSwitch this dial belongs to, if it is set up yet."""
        entry = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id, {})
        return entry.get(SWITCH_DOMAIN)

    async def async_added_to_hass(self) -> None:
        """Restore the last value and push it to the switch."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                self._value = float(last_state.state)
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "%s: could not restore intensity from %s, using %s",
                    self._attr_name,
                    last_state.state,
                    DEFAULT_INTENSITY,
                )
        # The switch starts after this platform and owns startup adaptation,
        # including the decision to skip it for only_once configurations.
        await self._push(adapt=False)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new intensity and re-adapt the lights straight away."""
        self._value = float(value)
        self.async_write_ha_state()
        await self._push(adapt=True)

    async def _push(self, *, adapt: bool) -> None:
        switch = self._switch
        if switch is None or switch.hass is None or switch.is_on is None:
            # The parent may not have started yet, or may be disabled in the
            # entity registry. It adopts this value when added to Home Assistant.
            entry_data = self.hass.data[DOMAIN][self._config_entry.entry_id]
            entry_data[PENDING_INTENSITY] = self._value
            _LOGGER.debug(
                "%s: switch not set up yet, handing intensity %s over to it",
                self._attr_name,
                self._value,
            )
            return
        await switch.async_set_intensity(self._value, adapt=adapt)
