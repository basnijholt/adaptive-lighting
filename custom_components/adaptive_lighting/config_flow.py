"""Config flow for Adaptive Lighting (CDiT fork).

Replaces upstream's flat 40-field options dialog with a six-section
layout (Targets / Daytime curve / Sun schedule / Light control / Advanced /
Diagnostics) using HA's `section()` helper and native selectors throughout.
See design.md decisions 1, 5, 6, 9, 14 and specs/options-flow/spec.md R1-R7.
"""

import contextlib
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
)
from homeassistant.config_entries import ConfigFlow as HAConfigFlow

try:
    from homeassistant.config_entries import OptionsFlowWithReload
except ImportError:  # pragma: no cover — HA < 2025.1 fallback for dev env
    from homeassistant.config_entries import OptionsFlow as OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_ADAPT_DELAY,
    CONF_INCLUDE_CONFIG_IN_ATTRIBUTES,
    CONF_INITIAL_TRANSITION,
    CONF_INTERCEPT,
    CONF_INTERVAL,
    CONF_LIGHTS,
    CONF_LUX_SENSOR,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_PREFER_RGB_COLOR,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SUNRISE_ENTITY,
    CONF_SUNSET_ENTITY,
    CONF_TARGET_LUX,
    CONF_TRANSITION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_INITIAL_TRANSITION,
    DEFAULT_INTERCEPT,
    DEFAULT_INTERVAL,
    DEFAULT_LUX_SENSOR,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MAX_COLOR_TEMP,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MIN_COLOR_TEMP,
    DEFAULT_MULTI_LIGHT_INTERCEPT,
    DEFAULT_PREFER_RGB_COLOR,
    DEFAULT_SEND_SPLIT_DELAY,
    DEFAULT_SEPARATE_TURN_ON_COMMANDS,
    DEFAULT_SKIP_REDUNDANT_COMMANDS,
    DEFAULT_SUNRISE_ENTITY,
    DEFAULT_SUNSET_ENTITY,
    DEFAULT_TARGET_LUX,
    DEFAULT_TRANSITION,
    DOMAIN,
    RANGE_ENTITIES,
)

_LOGGER = logging.getLogger(__name__)


# --- Section identifiers (also the translation-key roots in strings.json) ---
SECTION_TARGETS = "targets"
SECTION_DAYTIME = "daytime_curve"
SECTION_SUN = "sun_schedule"
SECTION_AMBIENT_LUX = "ambient_lux"
SECTION_LIGHT_CONTROL = "light_control"
SECTION_ADVANCED = "advanced"
SECTION_DIAGNOSTICS = "diagnostics"


# --- Selector factories (consistent units, ranges, units of measurement) ---


def _brightness_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=1,
            max=100,
            step=1,
            unit_of_measurement="%",
            mode=NumberSelectorMode.SLIDER,
        ),
    )


def _color_temp_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=1000,
            max=10000,
            step=100,
            unit_of_measurement="K",
            mode=NumberSelectorMode.BOX,
        ),
    )


def _duration_seconds_selector(max_value: int = 3600) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=max_value,
            step=1,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        ),
    )


def _duration_milliseconds_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=10000,
            step=10,
            unit_of_measurement="ms",
            mode=NumberSelectorMode.BOX,
        ),
    )


def _lights_selector() -> EntitySelector:
    return EntitySelector(EntitySelectorConfig(domain="light", multiple=True))


def _sun_event_selector() -> EntitySelector:
    return EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="timestamp"),
    )


def _lux_sensor_selector() -> EntitySelector:
    return EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="illuminance"),
    )


def _target_lux_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=1,
            max=10000,
            step=10,
            unit_of_measurement="lx",
            mode=NumberSelectorMode.BOX,
        ),
    )


# --- Schema builder ---


def _build_options_schema(
    current: dict[str, Any],
    *,
    show_send_split_delay: bool,
    show_target_lux: bool,
) -> vol.Schema:
    """Build the sectioned options schema from the entry's current values."""
    targets_section = section(
        vol.Schema(
            {
                vol.Required(
                    CONF_LIGHTS,
                    default=current.get(CONF_LIGHTS, []),
                ): _lights_selector(),
            },
        ),
        {"collapsed": False},
    )

    daytime_section = section(
        vol.Schema(
            {
                vol.Required(
                    CONF_MIN_BRIGHTNESS,
                    default=current.get(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS),
                ): _brightness_selector(),
                vol.Required(
                    CONF_MAX_BRIGHTNESS,
                    default=current.get(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS),
                ): _brightness_selector(),
                vol.Required(
                    CONF_MIN_COLOR_TEMP,
                    default=current.get(CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP),
                ): _color_temp_selector(),
                vol.Required(
                    CONF_MAX_COLOR_TEMP,
                    default=current.get(CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP),
                ): _color_temp_selector(),
                vol.Required(
                    CONF_PREFER_RGB_COLOR,
                    default=current.get(
                        CONF_PREFER_RGB_COLOR,
                        DEFAULT_PREFER_RGB_COLOR,
                    ),
                ): BooleanSelector(),
            },
        ),
        {"collapsed": False},
    )

    sun_section = section(
        vol.Schema(
            {
                vol.Required(
                    CONF_SUNRISE_ENTITY,
                    default=current.get(CONF_SUNRISE_ENTITY, DEFAULT_SUNRISE_ENTITY),
                ): _sun_event_selector(),
                vol.Required(
                    CONF_SUNSET_ENTITY,
                    default=current.get(CONF_SUNSET_ENTITY, DEFAULT_SUNSET_ENTITY),
                ): _sun_event_selector(),
            },
        ),
        {"collapsed": True},
    )

    # An illuminance EntitySelector rejects an empty string, so we must NOT
    # hand it `default=""`. When no sensor is configured, omit the default
    # entirely (vol.UNDEFINED) so the field is simply absent on submit and
    # treated as "unconfigured" — otherwise the form cannot be saved without
    # selecting a lux sensor.
    lux_default = current.get(CONF_LUX_SENSOR) or vol.UNDEFINED
    ambient_lux_schema: dict[Any, Any] = {
        vol.Optional(
            CONF_LUX_SENSOR,
            default=lux_default,
        ): _lux_sensor_selector(),
    }
    if show_target_lux:
        ambient_lux_schema[
            vol.Optional(
                CONF_TARGET_LUX,
                default=current.get(CONF_TARGET_LUX, DEFAULT_TARGET_LUX),
            )
        ] = _target_lux_selector()

    ambient_lux_section = section(
        vol.Schema(ambient_lux_schema),
        {"collapsed": True},
    )

    light_control_section = section(
        vol.Schema(
            {
                vol.Required(
                    CONF_INTERCEPT,
                    default=current.get(CONF_INTERCEPT, DEFAULT_INTERCEPT),
                ): BooleanSelector(),
                vol.Required(
                    CONF_MULTI_LIGHT_INTERCEPT,
                    default=current.get(
                        CONF_MULTI_LIGHT_INTERCEPT,
                        DEFAULT_MULTI_LIGHT_INTERCEPT,
                    ),
                ): BooleanSelector(),
            },
        ),
        {"collapsed": True},
    )

    advanced_schema: dict[Any, Any] = {
        vol.Required(
            CONF_INTERVAL,
            default=current.get(CONF_INTERVAL, DEFAULT_INTERVAL),
        ): _duration_seconds_selector(),
        vol.Required(
            CONF_TRANSITION,
            default=current.get(CONF_TRANSITION, DEFAULT_TRANSITION),
        ): _duration_seconds_selector(max_value=300),
        vol.Required(
            CONF_INITIAL_TRANSITION,
            default=current.get(CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION),
        ): _duration_seconds_selector(max_value=300),
        vol.Required(
            CONF_ADAPT_DELAY,
            default=current.get(CONF_ADAPT_DELAY, 0),
        ): _duration_seconds_selector(max_value=300),
        vol.Required(
            CONF_SEPARATE_TURN_ON_COMMANDS,
            default=current.get(
                CONF_SEPARATE_TURN_ON_COMMANDS,
                DEFAULT_SEPARATE_TURN_ON_COMMANDS,
            ),
        ): BooleanSelector(),
        vol.Required(
            CONF_SKIP_REDUNDANT_COMMANDS,
            default=current.get(
                CONF_SKIP_REDUNDANT_COMMANDS,
                DEFAULT_SKIP_REDUNDANT_COMMANDS,
            ),
        ): BooleanSelector(),
    }
    # Conditional visibility for send_split_delay: only when its driver
    # (separate_turn_on_commands) is true. Spec R2.
    if show_send_split_delay:
        advanced_schema[
            vol.Required(
                CONF_SEND_SPLIT_DELAY,
                default=current.get(CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY),
            )
        ] = _duration_milliseconds_selector()

    advanced_section = section(
        vol.Schema(advanced_schema),
        {"collapsed": True},
    )

    diagnostics_section = section(
        vol.Schema(
            {
                vol.Required(
                    CONF_INCLUDE_CONFIG_IN_ATTRIBUTES,
                    default=current.get(CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, False),
                ): BooleanSelector(),
            },
        ),
        {"collapsed": True},
    )

    return vol.Schema(
        {
            vol.Required(SECTION_TARGETS): targets_section,
            vol.Required(SECTION_DAYTIME): daytime_section,
            vol.Required(SECTION_SUN): sun_section,
            vol.Required(SECTION_AMBIENT_LUX): ambient_lux_section,
            vol.Required(SECTION_LIGHT_CONTROL): light_control_section,
            vol.Required(SECTION_ADVANCED): advanced_section,
            vol.Required(SECTION_DIAGNOSTICS): diagnostics_section,
        },
    )


def _flatten_sections(sectioned: dict[str, Any]) -> dict[str, Any]:
    """Flatten a sectioned form result back into a flat options dict.

    HA's section() wraps each section's values in a nested dict; we store
    options flat (matching VALIDATION_TUPLES), so unwrap here.
    """
    flat: dict[str, Any] = {}
    for value in sectioned.values():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[CONF_NAME] = value  # unlikely fallback
    return flat


def _has_pending_reveal(flat: dict[str, Any]) -> bool:
    """Return True when a just-toggled driver hides a dependent field.

    HA's section() forms are not reactive, so when a user enables a driver
    in this submission its dependent field was absent from the rendered
    schema (and therefore from ``flat``). The caller re-shows the rebuilt
    form so the dependent field appears in the same session, per the
    options-flow conditional-visibility spec.
    """
    return (bool(flat.get(CONF_LUX_SENSOR)) and CONF_TARGET_LUX not in flat) or (
        bool(flat.get(CONF_SEPARATE_TURN_ON_COMMANDS))
        and CONF_SEND_SPLIT_DELAY not in flat
    )


class AdaptiveLightingConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Handle a config flow for the CDiT Adaptive Lighting fork."""

    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Initial step: ask for a profile name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,  # noqa: ARG004
    ) -> "OptionsFlowHandler":
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


# Legacy alias so external code that does `from .config_flow import ConfigFlow`
# (such as upstream's docs/tests harness) still resolves.
ConfigFlow = AdaptiveLightingConfigFlow


class OptionsFlowHandler(OptionsFlowWithReload):
    """Sectioned options flow with reload-on-save.

    Spec R6: extends OptionsFlowWithReload so saving triggers a clean
    reload of the entry.
    """

    def _overlay_range_values(self, current: dict[str, Any]) -> None:
        """Overlay live runtime-range number entity values onto ``current``.

        Keeps the dialog's brightness/color-temp defaults in sync with what
        the four ``number`` entities are actually running (spec R6, D4).
        """
        registry = er.async_get(self.hass)
        for row in RANGE_ENTITIES:
            unique_id = f"{self.config_entry.entry_id}_{row['field_key']}"
            entity_id = registry.async_get_entity_id("number", DOMAIN, unique_id)
            if entity_id is None:
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (None, "unavailable", "unknown"):
                continue
            try:
                current[row["conf_key"]] = int(float(state.state))
            except (TypeError, ValueError):
                continue

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Render the single-page options form and handle its submission."""
        conf = self.config_entry
        # Merge data and options to compute the effective "current" view.
        current = dict(conf.data)
        current.update(conf.options)

        # Overlay live values from the four runtime range number entities
        # so the dialog matches what the user's lights are actually running
        # (spec R6, design D4). Other ~14 fields keep their `entry.options`
        # values from above.
        self._overlay_range_values(current)

        errors: dict[str, str] = {}
        if user_input is not None:
            flat = _flatten_sections(user_input)
            # Validate at least one light still exists.
            all_lights = set(self.hass.states.async_entity_ids("light"))
            for configured_light in flat.get(CONF_LIGHTS, []):
                if configured_light not in all_lights:
                    errors[CONF_LIGHTS] = "entity_missing"
                    _LOGGER.error(
                        "Adaptive Lighting: light entity %s is configured but not "
                        "currently registered. Aborting save.",
                        configured_light,
                    )
                    break
            if not errors:
                if _has_pending_reveal(flat):
                    # Overlay the just-submitted values so the re-rendered
                    # form keeps the user's edits and recomputes conditional
                    # visibility from the new driver values below, instead of
                    # saving — the dependent field then appears in the same
                    # session (no save-and-reopen round-trip).
                    current.update(flat)
                else:
                    return self.async_create_entry(title="", data=flat)

        lux_sensor_id = current.get(CONF_LUX_SENSOR, DEFAULT_LUX_SENSOR)
        lux_reading = "—"
        if lux_sensor_id:
            lux_state = self.hass.states.get(lux_sensor_id)
            if lux_state and lux_state.state not in ("unavailable", "unknown"):
                with contextlib.suppress(TypeError, ValueError):
                    lux_reading = f"{float(lux_state.state):.0f} lx"

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(
                current,
                show_send_split_delay=bool(
                    current.get(
                        CONF_SEPARATE_TURN_ON_COMMANDS,
                        DEFAULT_SEPARATE_TURN_ON_COMMANDS,
                    ),
                ),
                show_target_lux=bool(lux_sensor_id),
            ),
            description_placeholders={"current_lux": lux_reading},
            errors=errors,
        )
