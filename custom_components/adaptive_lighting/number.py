"""Number platform for the Adaptive Lighting integration (CDiT fork).

Each config entry exposes five live-tunable sliders that own the runtime
values the curve math reads on every tick:

- ``number.<profile>_min_brightness``
- ``number.<profile>_max_brightness``
- ``number.<profile>_min_color_temp``
- ``number.<profile>_max_color_temp``
- ``number.<profile>_ramp_half_width``

The entities extend ``RestoreNumber`` so values survive HA restarts without
a separate ``Store`` helper. Slider changes do NOT write back to
``entry.options`` (no integration reload). Options-flow saves reload the
integration, and the resulting fresh range entities prefer the just-saved
``entry.options`` value over the restored state. See design.md decisions
1-3 of the ``add-runtime-range-controls`` change.

The ramp half-width entity (``add-runtime-ramp-width``) has NO
``entry.options`` mirror — it is the only surface for the curve's
transition width, so its restore precedence is simply restored-value →
default (30 min). Total transition duration is twice the half-width.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, RAMP_WIDTH_ENTITY, RANGE_ENTITIES

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the four range entities plus the ramp-width entity."""
    entities: list[RestoreNumber] = [
        AdaptiveRangeNumber(
            entry=config_entry,
            field_key=row["field_key"],
            conf_key=row["conf_key"],
            default=row["default"],
            native_min=row["native_min"],
            native_max=row["native_max"],
            step=row["step"],
            unit=row["unit"],
            icon=row["icon"],
        )
        for row in RANGE_ENTITIES
    ]
    entities.append(AdaptiveRampWidthNumber(entry=config_entry))
    async_add_entities(entities)


class AdaptiveRangeNumber(RestoreNumber):
    """Live-tunable slider for one of the four curve range values."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False
    # Behaviour knobs, not state — keep them off the primary device page.
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        field_key: str,
        conf_key: str,
        default: float,
        native_min: float,
        native_max: float,
        step: float,
        unit: str,
        icon: str,
    ) -> None:
        """Initialise a single range number entity."""
        self._entry = entry
        self._field_key = field_key
        self._conf_key = conf_key
        self._default = default
        # No _attr_name — see the note in sensor.py.
        self._attr_translation_key = field_key
        self._attr_unique_id = f"{entry.entry_id}_{field_key}"
        self._attr_native_min_value = native_min
        self._attr_native_max_value = native_max
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        # Initial value falls back to the options snapshot until
        # async_added_to_hass overrides with a restored or just-saved value.
        self._attr_native_value = self._options_value()

    @property
    def suggested_object_id(self) -> str | None:
        """Pin entity_id slugs to the field key (e.g. ``_min_brightness``).

        The display names use "lower/upper" wording (device-page sort order),
        but entity_ids stay on the min/max field keys so new profiles slug
        identically to ones created before the rename.
        """
        return self._field_key

    @property
    def device_info(self) -> DeviceInfo:
        """Group with the profile's switches under one device."""
        profile_name = self._entry.data.get("name") or self._entry.title
        return DeviceInfo(
            identifiers={(DOMAIN, profile_name)},
            name=profile_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _options_value(self) -> float:
        """Read the seed value from entry.options (typed cast).

        On a freshly-created profile neither ``entry.options`` nor
        ``entry.data`` carries the range keys (setup only stores the name),
        so fall back to the field's sensible ``DEFAULT_*`` rather than the
        slider's ``native_min`` — otherwise a new group would come up at
        max_brightness=1% and a 1000-1000K color-temp range.
        """
        raw = self._entry.options.get(self._conf_key)
        if raw is None:
            raw = self._entry.data.get(self._conf_key, self._default)
        return float(raw)

    async def async_added_to_hass(self) -> None:
        """Seed the entity value with three-tier precedence.

        (a) First-creation: no restored state → use ``entry.options[conf_key]``.
        (b) Restored state exists AND was persisted AFTER the entry was last
            modified → the user moved the slider since the last options-flow
            save; use the restored value (slider survives restart).
        (c) Restored state exists BUT the entry was modified AFTER the
            restored state was persisted → an options-flow save changed the
            value; use ``entry.options[conf_key]`` (just-saved wins).
        """
        await super().async_added_to_hass()
        options_value = self._options_value()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in (None, "unknown", "unavailable"):
            self._attr_native_value = options_value
            return
        try:
            restored_value = float(last_state.state)
        except (TypeError, ValueError):
            self._attr_native_value = options_value
            return
        entry_modified = getattr(self._entry, "modified_at", None)
        if entry_modified is not None and entry_modified > last_state.last_updated:
            # Entry was edited (via options-flow save) after the entity's
            # last persist → the just-saved options value supersedes.
            self._attr_native_value = options_value
        else:
            self._attr_native_value = restored_value

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new slider value to entity state only.

        Does NOT write to ``entry.options`` — that would trigger an
        ``OptionsFlowWithReload`` reload on every slider tick. The
        RestoreNumber base class persists the value across restarts.
        """
        self._attr_native_value = value
        self.async_write_ha_state()


class AdaptiveRampWidthNumber(RestoreNumber):
    """Live-tunable ramp half-width for the curve's two sun-event ramps.

    Unlike the four range entities there is NO ``entry.options`` mirror —
    this entity is the only surface for the width (add-runtime-ramp-width
    D2), intended to be driven seasonally from Node-RED. Restore precedence
    is therefore two-tier: restored value → default. It must NOT inherit
    ``AdaptiveRangeNumber``'s three-tier logic, which prefers the options
    value after every options-flow save and would silently reset the width
    to 30 on each unrelated save.
    """

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False
    # Behaviour knobs, not state — keep them off the primary device page.
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, *, entry: ConfigEntry) -> None:
        """Initialise the ramp half-width entity from its const declaration."""
        self._entry = entry
        self._field_key: str = RAMP_WIDTH_ENTITY["field_key"]
        self._default: float = float(RAMP_WIDTH_ENTITY["default"])
        self._attr_translation_key = self._field_key
        self._attr_unique_id = f"{entry.entry_id}_{self._field_key}"
        self._attr_native_min_value = RAMP_WIDTH_ENTITY["native_min"]
        self._attr_native_max_value = RAMP_WIDTH_ENTITY["native_max"]
        self._attr_native_step = RAMP_WIDTH_ENTITY["step"]
        self._attr_native_unit_of_measurement = RAMP_WIDTH_ENTITY["unit"]
        self._attr_icon = RAMP_WIDTH_ENTITY["icon"]
        self._attr_native_value = self._default

    @property
    def suggested_object_id(self) -> str | None:
        """Pin the entity_id slug to the field key (``_ramp_half_width``)."""
        return self._field_key

    @property
    def device_info(self) -> DeviceInfo:
        """Group with the profile's switches under one device."""
        profile_name = self._entry.data.get("name") or self._entry.title
        return DeviceInfo(
            identifiers={(DOMAIN, profile_name)},
            name=profile_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Seed with two-tier precedence: restored value, else default 30."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in (None, "unknown", "unavailable"):
            self._attr_native_value = self._default
            return
        try:
            self._attr_native_value = float(last_state.state)
        except (TypeError, ValueError):
            self._attr_native_value = self._default

    async def async_set_native_value(self, value: float) -> None:
        """Persist to entity state only — never to ``entry.options``."""
        self._attr_native_value = value
        self.async_write_ha_state()
