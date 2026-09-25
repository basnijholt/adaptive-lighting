"""Constants for the Adaptive Lighting integration (CDiT fork)."""

from datetime import timedelta
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import VALID_TRANSITION
from homeassistant.const import CONF_ENTITY_ID

# CDiT icons (task 2.5). Master switch signals "this is an automatic system",
# the two adapt switches name the attribute they govern.
ICON_MAIN = "mdi:weather-sunny-alert"
ICON_BRIGHTNESS = "mdi:brightness-percent"
ICON_COLOR_TEMP = "mdi:invert-colors"

DOMAIN = "adaptive_lighting"

# Half-width of the tanh ramp around each sun event, in seconds.
# 30 minutes is the eye-friendly circadian-transition sweet spot; long enough
# to feel gradual, short enough to stay in-window across solstice-to-equinox
# sunrise drift. Documented in design.md decision 15.
# Since add-runtime-ramp-width this is the FALLBACK: the live value comes
# from the per-profile ramp half-width number entity (default 30 min).
RAMP_HALF_WIDTH_SECONDS = 1800

# Runtime ramp half-width entity (add-runtime-ramp-width R1, R2, D2, D3).
# Deliberately NOT in VALIDATION_TUPLES: there is no options-flow field —
# the number entity is the only surface, with the constant above as the
# unavailable-entity fallback. Unit is minutes; the curve consumes seconds.
CONF_RAMP_HALF_WIDTH = "ramp_half_width"
DEFAULT_RAMP_HALF_WIDTH_MIN = 30  # minutes; == RAMP_HALF_WIDTH_SECONDS / 60

# CDiT config-entry schema version. Bumped from upstream's implicit v1.
# An entry with version < CONFIG_ENTRY_VERSION fails async_setup_entry with
# a "recreate this entry" message — see design.md decision 4.
CONFIG_ENTRY_VERSION = 2

DOCS = {CONF_ENTITY_ID: "Entity ID of the switch. 📝"}


CONF_NAME, DEFAULT_NAME = "name", "default"
DOCS[CONF_NAME] = "Display name for this profile."

CONF_LIGHTS, DEFAULT_LIGHTS = "lights", []
DOCS[CONF_LIGHTS] = "Light entities this profile controls."

CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES = (
    "include_config_in_attributes",
    False,
)
DOCS[CONF_INCLUDE_CONFIG_IN_ATTRIBUTES] = (
    "Expose all configuration options as attributes on the master switch "
    "for debugging."
)

CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
DOCS[CONF_INITIAL_TRANSITION] = "Fade time when a light first turns on, in seconds."

CONF_INTERVAL, DEFAULT_INTERVAL = "interval", 90
DOCS[CONF_INTERVAL] = "How often to recompute and re-apply the curve, in seconds."

# CDiT default: 90 instead of upstream's 100. Leaves headroom so a manual
# "brighter please" bump above the curve is always possible.
CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS = "max_brightness", 90
DOCS[CONF_MAX_BRIGHTNESS] = "Brightness at the peak of the day, in percent."

CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP = "max_color_temp", 5500
DOCS[CONF_MAX_COLOR_TEMP] = "Color temperature at the peak of the day, in Kelvin."

# CDiT default: 10 instead of upstream's 1. 1% reads as off on most bulbs
# (and 5% proved too dim on gloomy days); 10% is the usable floor.
CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS = "min_brightness", 10
DOCS[CONF_MIN_BRIGHTNESS] = "Brightness during the night, in percent."

# CDiT default: 2000 K (matches upstream). Earlier the fork used 2200 K
# ("sodium-vapor orange" worry), but in practice the deeper warm tone won.
CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP = "min_color_temp", 2000
DOCS[CONF_MIN_COLOR_TEMP] = "Color temperature during the night, in Kelvin."

CONF_PREFER_RGB_COLOR, DEFAULT_PREFER_RGB_COLOR = "prefer_rgb_color", False
DOCS[CONF_PREFER_RGB_COLOR] = (
    "Prefer RGB color over color temperature when a light supports both."
)

CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS = (
    "separate_turn_on_commands",
    False,
)
DOCS[CONF_SEPARATE_TURN_ON_COMMANDS] = (
    "Use separate `light.turn_on` calls for color and brightness. Required "
    "by some lights that cannot accept both at once."
)

CONF_SUNRISE_ENTITY, DEFAULT_SUNRISE_ENTITY = (
    "sunrise_entity",
    "sensor.sun_next_rising",
)
DOCS[CONF_SUNRISE_ENTITY] = (
    "Sensor whose state is the next sunrise timestamp. Defaults to the "
    "built-in `sensor.sun_next_rising`; point at a Sun2 sensor for civil, "
    "nautical, or astronomical twilight."
)

CONF_SUNSET_ENTITY, DEFAULT_SUNSET_ENTITY = (
    "sunset_entity",
    "sensor.sun_next_setting",
)
DOCS[CONF_SUNSET_ENTITY] = (
    "Sensor whose state is the next sunset timestamp. Defaults to the "
    "built-in `sensor.sun_next_setting`."
)

CONF_TRANSITION, DEFAULT_TRANSITION = "transition", 45
DOCS[CONF_TRANSITION] = "Fade time for each scheduled curve update, in seconds."

CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY = "adapt_delay", 0
DOCS[CONF_ADAPT_DELAY] = (
    "Wait time after a light turns on before applying the curve, in seconds. "
    "Avoids flickering on lights that report 'on' before they have settled."
)

CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY = "send_split_delay", 0
DOCS[CONF_SEND_SPLIT_DELAY] = (
    "Pause between the two `light.turn_on` calls when "
    "`separate_turn_on_commands` is enabled, in milliseconds."
)

CONF_SKIP_REDUNDANT_COMMANDS, DEFAULT_SKIP_REDUNDANT_COMMANDS = (
    "skip_redundant_commands",
    False,
)
DOCS[CONF_SKIP_REDUNDANT_COMMANDS] = (
    "Don't send a command when the light is already at the target state. "
    "Cuts traffic; disable if HA's recorded state drifts from the physical "
    "light."
)

CONF_INTERCEPT, DEFAULT_INTERCEPT = "intercept", True
DOCS[CONF_INTERCEPT] = (
    "Intercept `light.turn_on` calls to apply the curve instantly, instead "
    "of waiting for the next scheduled update."
)

CONF_LUX_SENSOR, DEFAULT_LUX_SENSOR = "lux_sensor", ""
DOCS[CONF_LUX_SENSOR] = (
    "An illuminance sensor used to dim lights when ambient light exceeds the target. "
    "Leave empty to use the sun curve alone."
)

CONF_TARGET_LUX, DEFAULT_TARGET_LUX = "target_lux", 0
DOCS[CONF_TARGET_LUX] = (
    "Desired illuminance in lux. When the sensor reads above this value, "
    "lights dim proportionally. 0 disables lux-based dimming."
)

CONF_MULTI_LIGHT_INTERCEPT, DEFAULT_MULTI_LIGHT_INTERCEPT = (
    "multi_light_intercept",
    True,
)
DOCS[CONF_MULTI_LIGHT_INTERCEPT] = (
    "Also intercept `light.turn_on` calls that target multiple lights. "
    "Requires `intercept` to be enabled."
)

# Switch identifiers used as suffixes on each AL profile's entities.
# Sleep-mode switch (`SLEEP_MODE_SWITCH`) is intentionally removed in this
# fork — see design.md decision 7.
ADAPT_COLOR_SWITCH = "adapt_color_switch"
ADAPT_BRIGHTNESS_SWITCH = "adapt_brightness_switch"
ATTR_ADAPTIVE_LIGHTING_MANAGER = "manager"
UNDO_UPDATE_LISTENER = "undo_update_listener"

# Runtime range number-entity declarations. Each tuple drives both the
# number platform's entity creation and the curve-math read path. The
# `field_key` becomes the entity's unique-id suffix; the `conf_key` ties
# the entity back to its initial-seed value in `entry.options`.
# Design decisions 5, 6, 11 — see add-runtime-range-controls/design.md.
# Naming: "lower/upper" (not "min/max") so the device page — which sorts
# entities alphabetically by name — lists min before max for each quantity.
RANGE_ENTITIES: list[dict[str, Any]] = [
    {
        "field_key": "min_brightness",
        "conf_key": CONF_MIN_BRIGHTNESS,
        "default": DEFAULT_MIN_BRIGHTNESS,
        "name": "Brightness lower",
        "native_min": 1,
        "native_max": 100,
        "step": 1,
        "unit": "%",
        "icon": "mdi:brightness-3",
    },
    {
        "field_key": "max_brightness",
        "conf_key": CONF_MAX_BRIGHTNESS,
        "default": DEFAULT_MAX_BRIGHTNESS,
        "name": "Brightness upper",
        "native_min": 1,
        "native_max": 100,
        "step": 1,
        "unit": "%",
        "icon": "mdi:brightness-7",
    },
    {
        "field_key": "min_color_temp",
        "conf_key": CONF_MIN_COLOR_TEMP,
        "default": DEFAULT_MIN_COLOR_TEMP,
        "name": "Color temp lower",
        "native_min": 1000,
        "native_max": 10000,
        "step": 100,
        "unit": "K",
        "icon": "mdi:thermometer-low",
    },
    {
        "field_key": "max_color_temp",
        "conf_key": CONF_MAX_COLOR_TEMP,
        "default": DEFAULT_MAX_COLOR_TEMP,
        "name": "Color temp upper",
        "native_min": 1000,
        "native_max": 10000,
        "step": 100,
        "unit": "K",
        "icon": "mdi:thermometer-high",
    },
]

# Ramp half-width number-entity declaration (add-runtime-ramp-width R1, D2).
# Kept OUT of RANGE_ENTITIES: it has no `entry.options` mirror, so the
# options-seeding code paths that iterate the four range fields must not
# pick it up. One value drives BOTH the sunrise and sunset ramps (D1); the
# total transition is 2x this value. Unit is minutes; curve consumes seconds.
RAMP_WIDTH_ENTITY: dict[str, Any] = {
    "field_key": CONF_RAMP_HALF_WIDTH,
    "default": DEFAULT_RAMP_HALF_WIDTH_MIN,
    "name": "Ramp half-width",
    "native_min": 5,
    "native_max": 120,
    "step": 1,
    "unit": "min",
    "icon": "mdi:transition",
}

# Output sensor declarations (add-output-sensors / R1, D4, D7).
# Each dict drives one read-only `sensor` entity per AL profile. The `key`
# becomes both the sensor's unique-id suffix AND the cache-dict key in
# `hass.data[DOMAIN][entry_id]["outputs"]`, so the sensor reads
# `outputs[self._output_key]` with no intermediate mapping.
OUTPUT_SENSORS: list[dict[str, Any]] = [
    {
        "key": "output_brightness",
        "name": "Output brightness",
        "unit": "%",
        "icon": "mdi:brightness-percent",
    },
    {
        "key": "output_color_temp",
        "name": "Output color temp",
        "unit": "K",
        "icon": "mdi:thermometer",
    },
    {
        "key": "sun_elevation",
        "name": "Sun elevation",
        "unit": "°",
        "icon": "mdi:weather-sunset",
    },
    {
        "key": "ambient_lux",
        "name": "Ambient lux",
        "unit": "lx",
        "icon": "mdi:brightness-5",
        "conditional": True,
    },
    {
        "key": "lux_reduction",
        "name": "Lux reduction",
        "unit": "%",
        "icon": "mdi:chart-line-variant",
        "conditional": True,
    },
]

# Dispatcher signal used by the master switch to wake the output sensors
# after each curve tick. Keyed per config entry so two profiles don't
# cross-update. Format with `.format(entry_id=...)` at call/connect time.
SIGNAL_OUTPUTS_UPDATED = f"{DOMAIN}_{{entry_id}}_outputs_updated"

ATTR_ADAPT_COLOR = "adapt_color"
DOCS[ATTR_ADAPT_COLOR] = "Adjust the color of supporting lights over the day."
ATTR_ADAPT_BRIGHTNESS = "adapt_brightness"
DOCS[ATTR_ADAPT_BRIGHTNESS] = "Adjust the brightness of supporting lights over the day."

SERVICE_APPLY = "apply"
CONF_TURN_ON_LIGHTS = "turn_on_lights"
DOCS[CONF_TURN_ON_LIGHTS] = "Also turn on any targeted lights that are currently off."
SERVICE_CHANGE_SWITCH_SETTINGS = "change_switch_settings"
CONF_USE_DEFAULTS = "use_defaults"
DOCS[CONF_USE_DEFAULTS] = (
    "Source for any field not supplied in this call: "
    '"current" (keep existing values), "factory" (documented defaults), '
    'or "configuration" (the profile\'s own configured defaults).'
)

TURNING_OFF_DELAY = 5

DOCS_APPLY = {
    CONF_ENTITY_ID: "The master switch whose curve settings to apply.",
    CONF_LIGHTS: "Lights to apply the settings to.",
}


def int_between(min_int: int, max_int: int) -> vol.All:
    """Return an integer between 'min_int' and 'max_int'."""
    return vol.All(vol.Coerce(int), vol.Range(min=min_int, max=max_int))


# Per-field validation tuples: switch.py validates and defaults entry options
# against them. The UI options flow does not consume this list directly;
# config_flow.py hand-shapes its sections via HA selectors. Eighteen entries:
# 16 retained from upstream + 2 new sun-entity fields.
VALIDATION_TUPLES: list[tuple[str, Any, Any]] = [
    (CONF_LIGHTS, DEFAULT_LIGHTS, cv.entity_ids),  # type: ignore[arg-type]
    (CONF_INTERVAL, DEFAULT_INTERVAL, cv.positive_int),
    (CONF_TRANSITION, DEFAULT_TRANSITION, VALID_TRANSITION),
    (CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION, VALID_TRANSITION),
    (CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS, int_between(1, 100)),
    (CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS, int_between(1, 100)),
    (CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_PREFER_RGB_COLOR, DEFAULT_PREFER_RGB_COLOR, bool),
    (CONF_SUNRISE_ENTITY, DEFAULT_SUNRISE_ENTITY, cv.entity_id),
    (CONF_SUNSET_ENTITY, DEFAULT_SUNSET_ENTITY, cv.entity_id),
    (CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS, bool),
    (CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY, int_between(0, 10000)),
    (CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY, cv.positive_float),
    (CONF_SKIP_REDUNDANT_COMMANDS, DEFAULT_SKIP_REDUNDANT_COMMANDS, bool),
    (CONF_INTERCEPT, DEFAULT_INTERCEPT, bool),
    (CONF_MULTI_LIGHT_INTERCEPT, DEFAULT_MULTI_LIGHT_INTERCEPT, bool),
    (CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES, bool),
    (CONF_LUX_SENSOR, DEFAULT_LUX_SENSOR, cv.string),
    (CONF_TARGET_LUX, DEFAULT_TARGET_LUX, int_between(0, 10000)),
]


def timedelta_as_int(value: timedelta) -> float:
    """Convert a `datetime.timedelta` object to an integer."""
    return value.total_seconds()


# Only CONF_INTERVAL still needs coercion (HA accepts strings like "00:01:30"
# and turns them into timedeltas). All other coerced fields (sun times,
# brightness-mode windows) were removed.
EXTRA_VALIDATION: dict[str, tuple[Any, Any]] = {
    CONF_INTERVAL: (cv.time_period, timedelta_as_int),
}


def apply_service_schema(initial_transition: int = 1) -> vol.Schema:
    """Return the schema for the apply service."""
    return vol.Schema(
        {
            vol.Optional(CONF_ENTITY_ID): cv.entity_ids,  # type: ignore[arg-type]
            vol.Optional(CONF_LIGHTS, default=[]): cv.entity_ids,  # type: ignore[arg-type]
            vol.Optional(
                CONF_TRANSITION,
                default=initial_transition,
            ): VALID_TRANSITION,
            vol.Optional(ATTR_ADAPT_BRIGHTNESS, default=True): cv.boolean,
            vol.Optional(ATTR_ADAPT_COLOR, default=True): cv.boolean,
            vol.Optional(CONF_PREFER_RGB_COLOR, default=False): cv.boolean,
            vol.Optional(CONF_TURN_ON_LIGHTS, default=False): cv.boolean,
        },
    )
