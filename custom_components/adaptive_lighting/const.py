"""Constants for the Adaptive Lighting integration."""

from homeassistant.components.light import VALID_TRANSITION
from homeassistant.const import CONF_ENTITY_ID
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

DOCS = {CONF_ENTITY_ID: "Entity ID of the switch. 📝"}


CONF_NAME, DEFAULT_NAME = "name", "default"
DOCS[CONF_NAME] = "Display name for this switch. 📝"

CONF_LIGHTS, DEFAULT_LIGHTS = "lights", []
DOCS[CONF_LIGHTS] = "List of light entity_ids to be controlled (may be empty). 🌟"

CONF_DETECT_NON_HA_CHANGES, DEFAULT_DETECT_NON_HA_CHANGES = (
    "detect_non_ha_changes",
    False,
)
DOCS[CONF_DETECT_NON_HA_CHANGES] = (
    "Detect non-`light.turn_on` state changes and stop adapting lights. "
    "Requires `take_over_control`. 🕵️"
)

CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES = (
    "include_config_in_attributes",
    False,
)
DOCS[CONF_INCLUDE_CONFIG_IN_ATTRIBUTES] = (
    "Show all options as attributes on the switch in "
    "Home Assistant when set to `true`. 📝"
)

CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
DOCS[CONF_INITIAL_TRANSITION] = (
    "Duration of the first transition when lights turn "
    "from `off` to `on` in seconds. ⏲️"
)

CONF_SLEEP_TRANSITION, DEFAULT_SLEEP_TRANSITION = "sleep_transition", 1
DOCS[CONF_SLEEP_TRANSITION] = (
    'Duration of transition when "sleep mode" is toggled ' "in seconds. 😴"
)

CONF_INTERVAL, DEFAULT_INTERVAL = "interval", 90
DOCS[CONF_INTERVAL] = "Frequency to adapt the lights, in seconds. 🔄"

CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS = "max_brightness", 100
DOCS[CONF_MAX_BRIGHTNESS] = "Maximum brightness percentage. 💡"

CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP = "max_color_temp", 5500
DOCS[CONF_MAX_COLOR_TEMP] = "Coldest color temperature in Kelvin. ❄️"

CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS = "min_brightness", 1
DOCS[CONF_MIN_BRIGHTNESS] = "Minimum brightness percentage. 💡"

CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP = "min_color_temp", 2000
DOCS[CONF_MIN_COLOR_TEMP] = "Warmest color temperature in Kelvin. 🔥"

CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE = "only_once", False
DOCS[CONF_ONLY_ONCE] = (
    "Adapt lights only when they are turned on (`true`) or keep adapting them "
    "(`false`). 🔄"
)

CONF_PREFER_RGB_COLOR, DEFAULT_PREFER_RGB_COLOR = "prefer_rgb_color", False
DOCS[CONF_PREFER_RGB_COLOR] = (
    "Whether to prefer RGB color adjustment over "
    "light color temperature when possible. 🌈"
)

CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS = (
    "separate_turn_on_commands",
    False,
)
DOCS[CONF_SEPARATE_TURN_ON_COMMANDS] = (
    "Use separate `light.turn_on` calls for color and brightness, needed for "
    "some light types. 🔀"
)

CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS = "sleep_brightness", 1
DOCS[CONF_SLEEP_BRIGHTNESS] = "Brightness percentage of lights in sleep mode. 😴"

CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP = "sleep_color_temp", 1000
DOCS[CONF_SLEEP_COLOR_TEMP] = (
    "Color temperature in sleep mode (used when `sleep_rgb_or_color_temp` is "
    "`color_temp`) in Kelvin. 😴"
)

CONF_SLEEP_RGB_COLOR, DEFAULT_SLEEP_RGB_COLOR = "sleep_rgb_color", [255, 56, 0]
DOCS[CONF_SLEEP_RGB_COLOR] = (
    "RGB color in sleep mode (used when " '`sleep_rgb_or_color_temp` is "rgb_color"). 🌈'
)

CONF_SLEEP_RGB_OR_COLOR_TEMP, DEFAULT_SLEEP_RGB_OR_COLOR_TEMP = (
    "sleep_rgb_or_color_temp",
    "color_temp",
)
DOCS[CONF_SLEEP_RGB_OR_COLOR_TEMP] = (
    'Use either `"rgb_color"` or `"color_temp"` ' "in sleep mode. 🌙"
)

CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET = "sunrise_offset", 0
DOCS[CONF_SUNRISE_OFFSET] = (
    "Adjust sunrise time with a positive or negative offset " "in seconds. ⏰"
)

CONF_SUNRISE_TIME = "sunrise_time"
DOCS[CONF_SUNRISE_TIME] = "Set a fixed time (HH:MM:SS) for sunrise. 🌅"

CONF_MAX_SUNRISE_TIME = "max_sunrise_time"
DOCS[CONF_MAX_SUNRISE_TIME] = (
    "Set the latest virtual sunrise time (HH:MM:SS), allowing"
    " for earlier real sunrises. 🌅"
)

CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET = "sunset_offset", 0
DOCS[
    CONF_SUNSET_OFFSET
] = "Adjust sunset time with a positive or negative offset in seconds. ⏰"

CONF_SUNSET_TIME = "sunset_time"
DOCS[CONF_SUNSET_TIME] = "Set a fixed time (HH:MM:SS) for sunset. 🌇"

CONF_MIN_SUNSET_TIME = "min_sunset_time"
DOCS[CONF_MIN_SUNSET_TIME] = (
    "Set the earliest virtual sunset time (HH:MM:SS), allowing"
    " for later real sunsets. 🌇"
)

CONF_TAKE_OVER_CONTROL, DEFAULT_TAKE_OVER_CONTROL = "take_over_control", True
DOCS[CONF_TAKE_OVER_CONTROL] = (
    "Disable Adaptive Lighting if another source calls `light.turn_on` while lights "
    "are on and being adapted. Note that this calls `homeassistant.update_entity` "
    "every `interval`! 🔒"
)

CONF_TRANSITION, DEFAULT_TRANSITION = "transition", 45
DOCS[CONF_TRANSITION] = "Duration of transition when lights change, in seconds. 🕑"

CONF_ADAPT_UNTIL_SLEEP, DEFAULT_ADAPT_UNTIL_SLEEP = (
    "transition_until_sleep",
    False,
)
DOCS[CONF_ADAPT_UNTIL_SLEEP] = (
    "When enabled, Adaptive Lighting will treat sleep settings as the minimum, "
    "transitioning to these values after sunset. 🌙"
)

CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY = "adapt_delay", 0
DOCS[CONF_ADAPT_DELAY] = (
    "Wait time (seconds) between light turn on and Adaptive Lighting applying "
    "changes. Might help to avoid flickering. ⏲️"
)

CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY = "send_split_delay", 0
DOCS[CONF_SEND_SPLIT_DELAY] = (
    "Delay (ms) between `separate_turn_on_commands` for lights that don't support "
    "simultaneous brightness and color setting. ⏲️"
)

CONF_AUTORESET_CONTROL, DEFAULT_AUTORESET_CONTROL = "autoreset_control_seconds", 0
DOCS[CONF_AUTORESET_CONTROL] = (
    "Automatically reset the manual control after a number of seconds. "
    "Set to 0 to disable. ⏲️"
)

CONF_SKIP_REDUNDANT_COMMANDS, DEFAULT_SKIP_REDUNDANT_COMMANDS = (
    "skip_redundant_commands",
    False,
)
DOCS[CONF_SKIP_REDUNDANT_COMMANDS] = (
    "Skip sending adaptation commands whose target state already "
    "equals the light's known state. Minimizes network traffic and improves the "
    "adaptation responsivity in some situations. "
    "Disable if physical light states get out of sync with HA's recorded state."
)

SLEEP_MODE_SWITCH = "sleep_mode_switch"
ADAPT_COLOR_SWITCH = "adapt_color_switch"
ADAPT_BRIGHTNESS_SWITCH = "adapt_brightness_switch"
ATTR_TURN_ON_OFF_LISTENER = "turn_on_off_listener"
UNDO_UPDATE_LISTENER = "undo_update_listener"
NONE_STR = "None"
ATTR_ADAPT_COLOR = "adapt_color"
DOCS[ATTR_ADAPT_COLOR] = "Whether to adapt the color on supporting lights. 🌈"
ATTR_ADAPT_BRIGHTNESS = "adapt_brightness"
DOCS[ATTR_ADAPT_BRIGHTNESS] = "Whether to adapt the brightness of the light. 🌞"

SERVICE_SET_MANUAL_CONTROL = "set_manual_control"
CONF_MANUAL_CONTROL = "manual_control"
DOCS[CONF_MANUAL_CONTROL] = "Whether to manually control the lights. 🔒"
SERVICE_APPLY = "apply"
CONF_TURN_ON_LIGHTS = "turn_on_lights"
DOCS[CONF_TURN_ON_LIGHTS] = "Whether to turn on lights that are currently off. 🔆"
SERVICE_CHANGE_SWITCH_SETTINGS = "change_switch_settings"
CONF_USE_DEFAULTS = "use_defaults"
DOCS[CONF_USE_DEFAULTS] = (
    "Sets the default values not specified in this service call. Options: "
    '"current" (default, retains current values), "factory" (resets to '
    'documented defaults), or "configuration" (reverts to switch config defaults). ⚙️'
)

TURNING_OFF_DELAY = 5

DOCS_MANUAL_CONTROL = {
    CONF_ENTITY_ID: "The `entity_id` of the switch in which to (un)mark the "
    "light as being `manually controlled`. 📝",
    CONF_LIGHTS: "entity_id(s) of lights, if not specified, all lights in the "
    "switch are selected. 💡",
    CONF_MANUAL_CONTROL: 'Whether to add ("true") or remove ("false") the '
    'light from the "manual_control" list. 🔒',
}

DOCS_APPLY = {
    CONF_ENTITY_ID: "The `entity_id` of the switch with the settings to apply. 📝",
    CONF_LIGHTS: "A light (or list of lights) to apply the settings to. 💡",
}


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
    (CONF_ADAPT_UNTIL_SLEEP, DEFAULT_ADAPT_UNTIL_SLEEP, bool),
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
    (
        CONF_AUTORESET_CONTROL,
        DEFAULT_AUTORESET_CONTROL,
        int_between(0, 365 * 24 * 60 * 60),  # 1 year max
    ),
    (
        CONF_SKIP_REDUNDANT_COMMANDS,
        DEFAULT_SKIP_REDUNDANT_COMMANDS,
        bool,
    ),
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


def apply_service_schema(initial_transition: int = 1):
    """Return the schema for the apply service."""
    return vol.Schema(
        {
            vol.Optional(CONF_ENTITY_ID): cv.entity_ids,
            vol.Optional(CONF_LIGHTS, default=[]): cv.entity_ids,
            vol.Optional(
                CONF_TRANSITION,
                default=initial_transition,
            ): VALID_TRANSITION,
            vol.Optional(ATTR_ADAPT_BRIGHTNESS, default=True): cv.boolean,
            vol.Optional(ATTR_ADAPT_COLOR, default=True): cv.boolean,
            vol.Optional(CONF_PREFER_RGB_COLOR, default=False): cv.boolean,
            vol.Optional(CONF_TURN_ON_LIGHTS, default=False): cv.boolean,
        }
    )


SET_MANUAL_CONTROL_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTITY_ID): cv.entity_ids,
        vol.Optional(CONF_LIGHTS, default=[]): cv.entity_ids,
        vol.Optional(CONF_MANUAL_CONTROL, default=True): cv.boolean,
    }
)
