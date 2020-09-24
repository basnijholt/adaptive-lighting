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

UNDO_UPDATE_LISTENER = "undo_update_listener"
FAKE_NONE = "None"  # TODO: use `from homeassistant.const import ENTITY_MATCH_NONE`?


def int_between(a, b):
    return vol.All(vol.Coerce(int), vol.Range(min=a, max=b))


VALIDATION_TUPLES = [
    (CONF_LIGHTS, DEFAULT_LIGHTS, cv.entity_ids),
    (CONF_DISABLE_BRIGHTNESS_ADJUST, DEFAULT_DISABLE_BRIGHTNESS_ADJUST, bool),
    (CONF_DISABLE_ENTITY, FAKE_NONE, str),
    (CONF_DISABLE_STATE, FAKE_NONE, str),
    (CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION, VALID_TRANSITION),
    (CONF_INTERVAL, DEFAULT_INTERVAL, cv.positive_int),
    (CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS, int_between(1, 100)),
    (CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS, int_between(1, 100)),
    (CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE, bool),
    (CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS, int_between(1, 100)),
    (CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_SLEEP_ENTITY, FAKE_NONE, str),
    (CONF_SLEEP_STATE, FAKE_NONE, str),
    (CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET, int),
    (CONF_SUNRISE_TIME, FAKE_NONE, str),
    (CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET, int),
    (CONF_SUNSET_TIME, FAKE_NONE, str),
    (CONF_TRANSITION, DEFAULT_TRANSITION, VALID_TRANSITION),
]


def timedelta_as_int(value):
    return value.total_seconds()


def join_strings(lst):
    return ",".join(lst)


# these validators cannot be serialized
EXTRA_VALIDATION = {
    CONF_DISABLE_ENTITY: (cv.entity_id, str),
    CONF_DISABLE_STATE: (vol.All(cv.ensure_list_csv, [cv.string]), join_strings),
    CONF_INTERVAL: (cv.time_period, timedelta_as_int),
    CONF_SLEEP_ENTITY: (cv.entity_id, str),
    CONF_SLEEP_STATE: (vol.All(cv.ensure_list_csv, [cv.string]), join_strings),
    CONF_SUNRISE_OFFSET: (cv.time_period, timedelta_as_int),
    CONF_SUNRISE_TIME: (cv.time, str),
    CONF_SUNSET_OFFSET: (cv.time_period, timedelta_as_int),
    CONF_SUNSET_TIME: (cv.time, str),
}


def get_domain_schema(with_fake_none=False, yaml=False):
    def get_validation(key, validation):
        validation, coerce = EXTRA_VALIDATION.get(key, (validation, None))
        return (
            vol.All(validation, vol.Coerce(coerce))
            if yaml and coerce is not None
            else validation
        )

    validation_tuples = [
        (key, default, get_validation(key, validation))
        for key, default, validation in VALIDATION_TUPLES
    ]
    validation_tuples.append((CONF_NAME, DEFAULT_NAME, cv.string))

    def replace_none(x):
        if not with_fake_none and x == FAKE_NONE:
            return vol.UNDEFINED
        return x

    return {
        vol.Optional(key, default=replace_none(default)): validation
        for key, default, validation in validation_tuples
    }
