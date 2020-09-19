import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import VALID_TRANSITION

ICON = "mdi:theme-light-dark"

DOMAIN = "adaptive_lighting"
SUN_EVENT_NOON = "solar_noon"
SUN_EVENT_MIDNIGHT = "solar_midnight"

CONF_NAME, DEFAULT_NAME = "name", "default"
CONF_LIGHTS, DEFAULT_LIGHTS = "lights", []
CONF_DISABLE_BRIGHTNESS_ADJUST, DEFAULT_DISABLE_BRIGHTNESS_ADJUST = (
    "disable_brightness_adjust",
    False,
)
CONF_DISABLE_ENTITY = "disable_entity"
CONF_DISABLE_STATE = "disable_state"
CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
CONF_INTERVAL, DEFAULT_INTERVAL = "interval", 90
CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS = "max_brightness", 100
CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP = "max_color_temp", 5500
CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS = "min_brightness", 1
CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP = "min_color_temp", 2500
CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE = "only_once", False
CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS = "sleep_brightness", 1
CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP = "sleep_color_temp", 1000
CONF_SLEEP_ENTITY = "sleep_entity"
CONF_SLEEP_STATE = "sleep_state"
CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET = "sunrise_offset", 0
CONF_SUNRISE_TIME = "sunrise_time"
CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET = "sunset_offset", 0
CONF_SUNSET_TIME = "sunset_time"
CONF_TRANSITION, DEFAULT_TRANSITION = "transition", 60


_COMMON_SCHEMA = {
    vol.Optional(CONF_LIGHTS, default=DEFAULT_LIGHTS): cv.entity_ids,
    vol.Optional(CONF_DISABLE_BRIGHTNESS_ADJUST, default=DEFAULT_DISABLE_BRIGHTNESS_ADJUST): cv.boolean,
    vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
    vol.Optional(CONF_DISABLE_STATE): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION): VALID_TRANSITION,
    vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): cv.time_period,
    vol.Optional(CONF_MAX_BRIGHTNESS, default=DEFAULT_MAX_BRIGHTNESS): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_MAX_COLOR_TEMP, default=DEFAULT_MAX_COLOR_TEMP): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
    vol.Optional(CONF_MIN_BRIGHTNESS, default=DEFAULT_MIN_BRIGHTNESS): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_MIN_COLOR_TEMP, default=DEFAULT_MIN_COLOR_TEMP): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
    vol.Optional(CONF_ONLY_ONCE, default=DEFAULT_ONLY_ONCE): cv.boolean,
    vol.Optional(CONF_SLEEP_BRIGHTNESS, default=DEFAULT_SLEEP_BRIGHTNESS): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_SLEEP_COLOR_TEMP, default=DEFAULT_SLEEP_COLOR_TEMP): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
    vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
    vol.Optional(CONF_SLEEP_STATE): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_SUNRISE_OFFSET, default=DEFAULT_SUNRISE_OFFSET): cv.time_period,
    vol.Optional(CONF_SUNRISE_TIME): cv.time,
    vol.Optional(CONF_SUNSET_OFFSET, default=DEFAULT_SUNSET_OFFSET): cv.time_period,
    vol.Optional(CONF_SUNSET_TIME): cv.time,
    vol.Optional(CONF_TRANSITION, default=DEFAULT_TRANSITION): VALID_TRANSITION,
}


def _convert_to_options_schema(hass, options):
    schema = {}
    for key, value in _COMMON_SCHEMA.items():
        if key.schema == CONF_LIGHTS:
            all_lights = hass.states.async_entity_ids("light")
            to_type = cv.multi_select(all_lights)
        elif value == cv.boolean:
            to_type = bool
        elif (isinstance(value, vol.All) and hasattr(value.validators, "type") and value.validators[0].type == int) or value == VALID_TRANSITION:
            to_type = value
        elif value == cv.time_period:
            to_type = cv.time_period_dict
        else:
            to_type = str

        default = key.default() if not isinstance(key.default, vol.Undefined) else vol.UNDEFINED
        default = options.get(key.schema, default)
        schema[vol.Optional(key.schema, default=default)] = to_type
    return vol.Schema(schema)
