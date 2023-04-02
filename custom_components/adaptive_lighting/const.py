"""Constants for the Adaptive Lighting integration."""

from homeassistant.components.light import VALID_TRANSITION
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

ICON_MAIN = "mdi:theme-light-dark"
ICON_BRIGHTNESS = "mdi:brightness-4"
ICON_COLOR_TEMP = "mdi:sun-thermometer"
ICON_SLEEP = "mdi:sleep"

DOMAIN = "adaptive_lighting"
SUN_EVENT_NOON = "solar_noon"
SUN_EVENT_MIDNIGHT = "solar_midnight"

CONF_NAME, DEFAULT_NAME = "name", "default"
CONF_NAME_DOCS = "Display name for this switch. 📝"

CONF_LIGHTS, DEFAULT_LIGHTS = "lights", []
CONF_LIGHTS_DOCS = (
    "List of light entities to be controlled by Adaptive Lighting (may be empty). 🌟"
)

CONF_DETECT_NON_HA_CHANGES, DEFAULT_DETECT_NON_HA_CHANGES = (
    "detect_non_ha_changes",
    False,
)
CONF_DETECT_NON_HA_CHANGES_DOCS = "Detect non-`light.turn_on` state changes and stop adapting lights. Requires `take_over_control`. 🕵️"

CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES = (
    "include_config_in_attributes",
    False,
)
CONF_INCLUDE_CONFIG_IN_ATTRIBUTES_DOCS = "Show all options as attributes on the switch in Home Assistant when set to `true`. 📝"

CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
CONF_INITIAL_TRANSITION_DOCS = (
    "Duration of the first transition when lights turn from `off` to `on`. ⏲️"
)

CONF_SLEEP_TRANSITION, DEFAULT_SLEEP_TRANSITION = "sleep_transition", 1
CONF_SLEEP_TRANSITION_DOCS = "Duration of transition when 'sleep mode' is toggled. 😴"

CONF_INTERVAL, DEFAULT_INTERVAL = "interval", 90
CONF_INTERVAL_DOCS = "Frequency to adapt the lights, in seconds. 🔄"

CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS = "max_brightness", 100
CONF_MAX_BRIGHTNESS_DOCS = "Maximum brightness percentage. 💡"

CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP = "max_color_temp", 5500
CONF_MAX_COLOR_TEMP_DOCS = "Coldest color temperature in Kelvin. ❄️"

CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS = "min_brightness", 1
CONF_MIN_BRIGHTNESS_DOCS = "Minimum brightness percentage. 💡"

CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP = "min_color_temp", 2000
CONF_MIN_COLOR_TEMP_DOCS = "Warmest color temperature in Kelvin. 🔥"

CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE = "only_once", False
CONF_ONLY_ONCE_DOCS = "Adapt lights only when they are turned on (`true`) or keep adapting them (`false`). 🔄"

CONF_PREFER_RGB_COLOR, DEFAULT_PREFER_RGB_COLOR = "prefer_rgb_color", False
CONF_PREFER_RGB_COLOR_DOCS = (
    "Use RGB color adjustment instead of native light color temperature. 🌈"
)

CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS = (
    "separate_turn_on_commands",
    False,
)
CONF_SEPARATE_TURN_ON_COMMANDS_DOCS = "Use separate `light.turn_on` calls for color and brightness, needed for some light types. 🔀"

CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS = "sleep_brightness", 1
CONF_SLEEP_BRIGHTNESS_DOCS = "Brightness of lights in sleep mode. 😴"

CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP = "sleep_color_temp", 1000
CONF_SLEEP_COLOR_TEMP_DOCS = "Color temperature in sleep mode (used when `sleep_rgb_or_color_temp` is `color_temp`). 😴"

CONF_SLEEP_RGB_COLOR, DEFAULT_SLEEP_RGB_COLOR = "sleep_rgb_color", [255, 56, 0]
CONF_SLEEP_RGB_COLOR_DOCS = (
    "RGB color in sleep mode (used when `sleep_rgb_or_color_temp` is `'rgb_color'`). 🌈"
)

CONF_SLEEP_RGB_OR_COLOR_TEMP, DEFAULT_SLEEP_RGB_OR_COLOR_TEMP = (
    "sleep_rgb_or_color_temp",
    "color_temp",
)
CONF_SLEEP_RGB_OR_COLOR_TEMP_DOCS = (
    "Use either `'rgb_color'` or `'color_temp'` in sleep mode. 🌙"
)

CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET = "sunrise_offset", 0
CONF_SUNRISE_OFFSET_DOCS = "Adjust sunrise time with a positive or negative offset. ⏰"

CONF_SUNRISE_TIME = "sunrise_time"
CONF_SUNRISE_TIME_DOCS = "Set a fixed time for sunrise. 🌅"

CONF_MAX_SUNRISE_TIME = "max_sunrise_time"
CONF_MAX_SUNRISE_TIME_DOCS = (
    "Set the latest virtual sunrise time, allowing for earlier real sunrises. 🌅"
)

CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET = "sunset_offset", 0
CONF_SUNSET_OFFSET_DOCS = "Adjust sunset time with a positive or negative offset. ⏰"

CONF_SUNSET_TIME = "sunset_time"
CONF_SUNSET_TIME_DOCS = "Set a fixed time for sunset. 🌇"

CONF_MIN_SUNSET_TIME = "min_sunset_time"
CONF_MIN_SUNSET_TIME_DOCS = (
    "Set the earliest virtual sunset time, allowing for later real sunsets. 🌇"
)

CONF_TAKE_OVER_CONTROL, DEFAULT_TAKE_OVER_CONTROL = "take_over_control", True
CONF_TAKE_OVER_CONTROL_DOCS = "Disable Adaptive Lighting if another source calls `light.turn_on` while lights are on and being adapted. Note that this calls `homeassistant.update_entity` every `interval`! 🔒"

CONF_TRANSITION, DEFAULT_TRANSITION = "transition", 45
CONF_TRANSITION_DOCS = "Duration of transition when lights change, in seconds. 🕑"

CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY = "adapt_delay", 0
CONF_ADAPT_DELAY_DOCS = "Wait time (seconds) between light turn on and Adaptive Lighting applying changes. Helps avoid flickering. ⏲️"

CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY = "send_split_delay", 0
CONF_SEND_SPLIT_DELAY_DOCS = "Wait time (milliseconds) between commands when using `separate_turn_on_commands`. Helps ensure correct handling. ⏲️"

SLEEP_MODE_SWITCH = "sleep_mode_switch"
ADAPT_COLOR_SWITCH = "adapt_color_switch"
ADAPT_BRIGHTNESS_SWITCH = "adapt_brightness_switch"
ATTR_TURN_ON_OFF_LISTENER = "turn_on_off_listener"
UNDO_UPDATE_LISTENER = "undo_update_listener"
NONE_STR = "None"
ATTR_ADAPT_COLOR = "adapt_color"
ATTR_ADAPT_BRIGHTNESS = "adapt_brightness"

SERVICE_SET_MANUAL_CONTROL = "set_manual_control"
CONF_MANUAL_CONTROL = "manual_control"
SERVICE_APPLY = "apply"
CONF_TURN_ON_LIGHTS = "turn_on_lights"
SERVICE_CHANGE_SWITCH_SETTINGS = "change_switch_settings"
CONF_USE_DEFAULTS = "use_defaults"


TURNING_OFF_DELAY = 5


def int_between(min_int, max_int):
    """Return an integer between 'min_int' and 'max_int'."""
    return vol.All(vol.Coerce(int), vol.Range(min=min_int, max=max_int))


VALIDATION_TUPLES = [
    (CONF_LIGHTS, DEFAULT_LIGHTS, cv.entity_ids),
    (CONF_PREFER_RGB_COLOR, DEFAULT_PREFER_RGB_COLOR, bool),
    (CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES, bool),
    (CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION, VALID_TRANSITION),
    (CONF_SLEEP_TRANSITION, DEFAULT_SLEEP_TRANSITION, VALID_TRANSITION),
    (CONF_TRANSITION, DEFAULT_TRANSITION, VALID_TRANSITION),
    (CONF_INTERVAL, DEFAULT_INTERVAL, cv.positive_int),
    (CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS, int_between(1, 100)),
    (CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS, int_between(1, 100)),
    (CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP, int_between(1000, 10000)),
    (CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS, int_between(1, 100)),
    (
        CONF_SLEEP_RGB_OR_COLOR_TEMP,
        DEFAULT_SLEEP_RGB_OR_COLOR_TEMP,
        selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["color_temp", "rgb_color"],
                multiple=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
    ),
    (CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP, int_between(1000, 10000)),
    (
        CONF_SLEEP_RGB_COLOR,
        DEFAULT_SLEEP_RGB_COLOR,
        selector.ColorRGBSelector(selector.ColorRGBSelectorConfig()),
    ),
    (CONF_SUNRISE_TIME, NONE_STR, str),
    (CONF_MAX_SUNRISE_TIME, NONE_STR, str),
    (CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET, int),
    (CONF_SUNSET_TIME, NONE_STR, str),
    (CONF_MIN_SUNSET_TIME, NONE_STR, str),
    (CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET, int),
    (CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE, bool),
    (CONF_TAKE_OVER_CONTROL, DEFAULT_TAKE_OVER_CONTROL, bool),
    (CONF_DETECT_NON_HA_CHANGES, DEFAULT_DETECT_NON_HA_CHANGES, bool),
    (CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS, bool),
    (CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY, int_between(0, 10000)),
    (CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY, cv.positive_float),
]


def timedelta_as_int(value):
    """Convert a `datetime.timedelta` object to an integer.

    This integer can be serialized to json but a timedelta cannot.
    """
    return value.total_seconds()


# conf_option: (validator, coerce) tuples
# these validators cannot be serialized but can be serialized when coerced by coerce.
EXTRA_VALIDATION = {
    CONF_INTERVAL: (cv.time_period, timedelta_as_int),
    CONF_SUNRISE_OFFSET: (cv.time_period, timedelta_as_int),
    CONF_SUNRISE_TIME: (cv.time, str),
    CONF_MAX_SUNRISE_TIME: (cv.time, str),
    CONF_SUNSET_OFFSET: (cv.time_period, timedelta_as_int),
    CONF_SUNSET_TIME: (cv.time, str),
    CONF_MIN_SUNSET_TIME: (cv.time, str),
}


def maybe_coerce(key, validation):
    """Coerce the validation into a json serializable type."""
    validation, coerce = EXTRA_VALIDATION.get(key, (validation, None))
    if coerce is not None:
        return vol.All(validation, vol.Coerce(coerce))
    return validation


def replace_none_str(value, replace_with=None):
    """Replace "None" -> replace_with."""
    return value if value != NONE_STR else replace_with


_yaml_validation_tuples = [
    (key, default, maybe_coerce(key, validation))
    for key, default, validation in VALIDATION_TUPLES
] + [(CONF_NAME, DEFAULT_NAME, cv.string)]

_DOMAIN_SCHEMA = vol.Schema(
    {
        vol.Optional(key, default=replace_none_str(default, vol.UNDEFINED)): validation
        for key, default, validation in _yaml_validation_tuples
    }
)
