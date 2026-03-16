"""Constants for the Adaptive Lighting integration."""

from datetime import timedelta
from enum import Enum
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import VALID_TRANSITION
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.helpers import selector

ICON_MAIN = "mdi:theme-light-dark"
ICON_BRIGHTNESS = "mdi:brightness-4"
ICON_COLOR_TEMP = "mdi:sun-thermometer"
ICON_SLEEP = "mdi:sleep"

DOMAIN = "adaptive_lighting"


class TakeOverControlMode(Enum):
    """Modes for pausing adaptation when control of a light is taken over externally."""

    PAUSE_ALL = "pause_all"
    PAUSE_CHANGED = "pause_changed"


DOCS = {CONF_ENTITY_ID: "Entity ID of this Adaptive Lighting switch."}


CONF_NAME, DEFAULT_NAME = "name", "default"
DOCS[CONF_NAME] = "Display name for this Adaptive Lighting instance."

CONF_LIGHTS, DEFAULT_LIGHTS = "lights", []
DOCS[CONF_LIGHTS] = (
    "Light entities controlled by this switch. "
    "Leave empty to add lights later."
)

CONF_DETECT_NON_HA_CHANGES, DEFAULT_DETECT_NON_HA_CHANGES = (
    "detect_non_ha_changes",
    False,
)
DOCS[CONF_DETECT_NON_HA_CHANGES] = (
    "Detects changes made outside Home Assistant (physical switches, third-party apps) "
    "by polling lights each interval, and pauses adaptation until manually reset. "
    "Requires `take_over_control`. "
    "⚠️ Some lights falsely report an 'on' state, which can cause them to turn on "
    "unexpectedly. Disable if you observe unintended behavior."
)

CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES = (
    "include_config_in_attributes",
    False,
)
DOCS[CONF_INCLUDE_CONFIG_IN_ATTRIBUTES] = (
    "Exposes all configuration values as attributes on the switch entity, "
    "visible in Home Assistant developer tools."
)

CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
DOCS[CONF_INITIAL_TRANSITION] = (
    "Fade duration (seconds) when a light first turns on from an off state."
)

CONF_SLEEP_TRANSITION, DEFAULT_SLEEP_TRANSITION = "sleep_transition", 1
DOCS[CONF_SLEEP_TRANSITION] = (
    "Fade duration (seconds) when entering or exiting sleep mode."
)

CONF_INTERVAL, DEFAULT_INTERVAL = "interval", 90
DOCS[CONF_INTERVAL] = (
    "Update frequency (seconds) for recalculating and applying light settings."
)

CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS = "max_brightness", 100
DOCS[CONF_MAX_BRIGHTNESS] = "Highest brightness (%) applied during the day."

CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP = "max_color_temp", 5500
DOCS[CONF_MAX_COLOR_TEMP] = "Coldest color temperature (Kelvin) applied around midday."

CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS = "min_brightness", 1
DOCS[CONF_MIN_BRIGHTNESS] = "Lowest brightness (%) applied at night."

CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP = "min_color_temp", 2000
DOCS[CONF_MIN_COLOR_TEMP] = "Warmest color temperature (Kelvin) applied at night."

CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE = "only_once", False
DOCS[CONF_ONLY_ONCE] = (
    "Applies adaptive settings only at the moment a light turns on, "
    "without continuing to update while the light stays on."
)

CONF_ADAPT_ONLY_ON_BARE_TURN_ON, DEFAULT_ADAPT_ONLY_ON_BARE_TURN_ON = (
    "adapt_only_on_bare_turn_on",
    False,
)
DOCS[CONF_ADAPT_ONLY_ON_BARE_TURN_ON] = (
    "Skips adaptation when a light is turned on with explicit color or brightness "
    "values (e.g., a scene). The light is then treated as manually controlled. "
    "Requires `take_over_control`."
)

CONF_PREFER_RGB_COLOR, DEFAULT_PREFER_RGB_COLOR = "prefer_rgb_color", False
DOCS[CONF_PREFER_RGB_COLOR] = (
    "Sends RGB color commands instead of color temperature commands to lights "
    "that support both. Useful for lights with inaccurate built-in color "
    "temperature control."
)

CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS = (
    "separate_turn_on_commands",
    False,
)
DOCS[CONF_SEPARATE_TURN_ON_COMMANDS] = (
    "Sends brightness and color as two separate commands instead of one. "
    "Required for light types that cannot handle both attributes in a single call."
)

CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS = "sleep_brightness", 1
DOCS[CONF_SLEEP_BRIGHTNESS] = "Brightness (%) applied while sleep mode is active."

CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP = "sleep_color_temp", 1000
DOCS[CONF_SLEEP_COLOR_TEMP] = (
    "Color temperature (Kelvin) applied while sleep mode is active. "
    "Requires `sleep_rgb_or_color_temp` set to `color_temp`."
)

CONF_SLEEP_RGB_COLOR, DEFAULT_SLEEP_RGB_COLOR = "sleep_rgb_color", [255, 56, 0]
DOCS[CONF_SLEEP_RGB_COLOR] = (
    "RGB color applied while sleep mode is active. "
    'Requires `sleep_rgb_or_color_temp` set to `rgb_color`.'
)

CONF_SLEEP_RGB_OR_COLOR_TEMP, DEFAULT_SLEEP_RGB_OR_COLOR_TEMP = (
    "sleep_rgb_or_color_temp",
    "color_temp",
)
DOCS[CONF_SLEEP_RGB_OR_COLOR_TEMP] = (
    "Selects whether sleep mode applies a color temperature "
    "(`color_temp`) or an RGB color (`rgb_color`)."
)

CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET = "sunrise_offset", 0
DOCS[CONF_SUNRISE_OFFSET] = (
    "Shifts the sunrise time (seconds). "
    "Positive values delay sunrise; negative values advance it."
)

CONF_SUNRISE_TIME = "sunrise_time"
DOCS[CONF_SUNRISE_TIME] = (
    "Overrides the calculated sunrise with a fixed time (HH:MM:SS). "
    "Leave unset to use the actual local sunrise."
)

CONF_MIN_SUNRISE_TIME = "min_sunrise_time"
DOCS[CONF_MIN_SUNRISE_TIME] = (
    "Earliest allowed sunrise time (HH:MM:SS). "
    "The effective sunrise never occurs before this time."
)

CONF_MAX_SUNRISE_TIME = "max_sunrise_time"
DOCS[CONF_MAX_SUNRISE_TIME] = (
    "Latest allowed sunrise time (HH:MM:SS). "
    "The effective sunrise never occurs after this time."
)

CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET = "sunset_offset", 0
DOCS[CONF_SUNSET_OFFSET] = (
    "Shifts the sunset time (seconds). "
    "Positive values delay sunset; negative values advance it."
)

CONF_SUNSET_TIME = "sunset_time"
DOCS[CONF_SUNSET_TIME] = (
    "Overrides the calculated sunset with a fixed time (HH:MM:SS). "
    "Leave unset to use the actual local sunset."
)

CONF_MIN_SUNSET_TIME = "min_sunset_time"
DOCS[CONF_MIN_SUNSET_TIME] = (
    "Earliest allowed sunset time (HH:MM:SS). "
    "The effective sunset never occurs before this time."
)

CONF_MAX_SUNSET_TIME = "max_sunset_time"
DOCS[CONF_MAX_SUNSET_TIME] = (
    "Latest allowed sunset time (HH:MM:SS). "
    "The effective sunset never occurs after this time."
)

CONF_BRIGHTNESS_MODE, DEFAULT_BRIGHTNESS_MODE = "brightness_mode", "default"
DOCS[CONF_BRIGHTNESS_MODE] = (
    "Brightness calculation algorithm. "
    "`default` follows a smooth solar curve. "
    "`linear` ramps evenly between min and max. "
    "`tanh` applies a gradual S-curve shaped by "
    "`brightness_mode_time_dark` and `brightness_mode_time_light`."
)
CONF_BRIGHTNESS_MODE_TIME_DARK, DEFAULT_BRIGHTNESS_MODE_TIME_DARK = (
    "brightness_mode_time_dark",
    900,
)
DOCS[CONF_BRIGHTNESS_MODE_TIME_DARK] = (
    "Dark-side transition window (seconds): how long before sunrise brightness "
    "begins rising and how long after sunset it finishes falling. "
    "Requires `brightness_mode` set to `linear` or `tanh`."
)
CONF_BRIGHTNESS_MODE_TIME_LIGHT, DEFAULT_BRIGHTNESS_MODE_TIME_LIGHT = (
    "brightness_mode_time_light",
    3600,
)
DOCS[CONF_BRIGHTNESS_MODE_TIME_LIGHT] = (
    "Light-side transition window (seconds): how long after sunrise brightness "
    "finishes rising and how long before sunset it begins falling. "
    "Requires `brightness_mode` set to `linear` or `tanh`."
)

CONF_TAKE_OVER_CONTROL, DEFAULT_TAKE_OVER_CONTROL = "take_over_control", True
DOCS[CONF_TAKE_OVER_CONTROL] = (
    "Pauses adaptation when another source (automation, scene, or voice assistant) "
    "changes a light. The light stays paused until turned off and on again or "
    "reset via the `set_manual_control` service."
)

CONF_TAKE_OVER_CONTROL_MODE, DEFAULT_TAKE_OVER_CONTROL_MODE = (
    "take_over_control_mode",
    TakeOverControlMode.PAUSE_ALL.value,
)
DOCS[CONF_TAKE_OVER_CONTROL_MODE] = (
    "Controls which attributes pause when another source changes a light. "
    "`pause_all` stops both brightness and color adaptation. "
    "`pause_changed` stops only the attribute that was changed and "
    "continues adapting the other."
)

CONF_TRANSITION, DEFAULT_TRANSITION = "transition", 45
DOCS[CONF_TRANSITION] = (
    "Fade duration (seconds) when applying each adaptive update to a light."
)

CONF_ADAPT_UNTIL_SLEEP, DEFAULT_ADAPT_UNTIL_SLEEP = (
    "transition_until_sleep",
    False,
)
DOCS[CONF_ADAPT_UNTIL_SLEEP] = (
    "Treats sleep mode values as the nighttime floor. After sunset, brightness "
    "and color temperature gradually approach the sleep settings instead of "
    "stopping at the configured minimums."
)

CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY = "adapt_delay", 0
DOCS[CONF_ADAPT_DELAY] = (
    "Wait time (seconds) after a light turns on before applying adaptive settings. "
    "Increase if lights flicker or reset on turn-on."
)

CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY = "send_split_delay", 0
DOCS[CONF_SEND_SPLIT_DELAY] = (
    "Delay (milliseconds) between the brightness and color commands. "
    "Requires `separate_turn_on_commands`."
)

CONF_AUTORESET_CONTROL, DEFAULT_AUTORESET_CONTROL = "autoreset_control_seconds", 0
DOCS[CONF_AUTORESET_CONTROL] = (
    "Resumes adaptive control automatically after a light has been manually "
    "controlled for this duration (seconds). Set to 0 to disable auto-reset."
)

CONF_SKIP_REDUNDANT_COMMANDS, DEFAULT_SKIP_REDUNDANT_COMMANDS = (
    "skip_redundant_commands",
    False,
)
DOCS[CONF_SKIP_REDUNDANT_COMMANDS] = (
    "Skips commands when the target state matches the light's last known state, "
    "reducing network traffic. "
    "Disable if light states drift out of sync."
)

CONF_INTERCEPT, DEFAULT_INTERCEPT = "intercept", True
DOCS[CONF_INTERCEPT] = (
    "Prevents lights from flashing at incorrect settings on turn-on by "
    "intercepting the command and immediately applying adaptive brightness "
    "and color. Disable for lights that do not accept color or brightness "
    "on turn-on."
)

CONF_MULTI_LIGHT_INTERCEPT, DEFAULT_MULTI_LIGHT_INTERCEPT = (
    "multi_light_intercept",
    True,
)
DOCS[CONF_MULTI_LIGHT_INTERCEPT] = (
    "Extends interception to commands targeting multiple lights at once. "
    "⚠️ May split a single command into per-light calls, which can behave "
    "differently for lights managed by separate switches. "
    "Requires `intercept`."
)

SLEEP_MODE_SWITCH = "sleep_mode_switch"
ADAPT_COLOR_SWITCH = "adapt_color_switch"
ADAPT_BRIGHTNESS_SWITCH = "adapt_brightness_switch"
ATTR_ADAPTIVE_LIGHTING_MANAGER = "manager"
UNDO_UPDATE_LISTENER = "undo_update_listener"
NONE_STR = "None"
ATTR_ADAPT_COLOR = "adapt_color"
DOCS[ATTR_ADAPT_COLOR] = "Adapts the color temperature or RGB color of the light."
ATTR_ADAPT_BRIGHTNESS = "adapt_brightness"
DOCS[ATTR_ADAPT_BRIGHTNESS] = "Adapts the brightness of the light."

SERVICE_SET_MANUAL_CONTROL = "set_manual_control"
CONF_MANUAL_CONTROL = "manual_control"
DOCS[CONF_MANUAL_CONTROL] = (
    "Marks or unmarks a light as manually controlled. "
    "Pass `true` to pause adaptation, `false` to resume, "
    "or an attribute name (`brightness` or `color`) for selective control."
)
SERVICE_APPLY = "apply"
CONF_TURN_ON_LIGHTS = "turn_on_lights"
DOCS[CONF_TURN_ON_LIGHTS] = "Also turns on lights that are currently off."
SERVICE_CHANGE_SWITCH_SETTINGS = "change_switch_settings"
CONF_USE_DEFAULTS = "use_defaults"
DOCS[CONF_USE_DEFAULTS] = (
    "Determines how unspecified fields are filled. "
    "`current` keeps the switch's live values (default). "
    "`factory` resets unspecified fields to built-in defaults. "
    "`configuration` resets unspecified fields to the switch's saved configuration."
)

TURNING_OFF_DELAY = 5

DOCS_MANUAL_CONTROL = {
    CONF_ENTITY_ID: "The Adaptive Lighting switch whose lights will be updated.",
    CONF_LIGHTS: (
        "Specific lights to mark or unmark. "
        "If omitted, all lights in the switch are affected."
    ),
    CONF_MANUAL_CONTROL: (
        "Pass `true` to pause adaptation, `false` to resume, "
        "or an attribute name (`brightness` or `color`) for selective control."
    ),
}

DOCS_APPLY = {
    CONF_ENTITY_ID: "The Adaptive Lighting switch whose settings will be applied.",
    CONF_LIGHTS: (
        "Specific lights to apply the settings to. "
        "If omitted, all lights in the switch are used."
    ),
}


def int_between(min_int: int, max_int: int) -> vol.All:
    """Return an integer between 'min_int' and 'max_int'."""
    return vol.All(vol.Coerce(int), vol.Range(min=min_int, max=max_int))


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
    (CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS, int_between(1, 100)),
    (
        CONF_SLEEP_RGB_OR_COLOR_TEMP,
        DEFAULT_SLEEP_RGB_OR_COLOR_TEMP,
        selector.SelectSelector(  # type: ignore[arg-type]
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
        selector.ColorRGBSelector(selector.ColorRGBSelectorConfig()),  # type: ignore[arg-type]
    ),
    (CONF_SLEEP_TRANSITION, DEFAULT_SLEEP_TRANSITION, VALID_TRANSITION),
    (CONF_ADAPT_UNTIL_SLEEP, DEFAULT_ADAPT_UNTIL_SLEEP, bool),
    (CONF_SUNRISE_TIME, NONE_STR, str),
    (CONF_MIN_SUNRISE_TIME, NONE_STR, str),
    (CONF_MAX_SUNRISE_TIME, NONE_STR, str),
    (CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET, int),
    (CONF_SUNSET_TIME, NONE_STR, str),
    (CONF_MIN_SUNSET_TIME, NONE_STR, str),
    (CONF_MAX_SUNSET_TIME, NONE_STR, str),
    (CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET, int),
    (
        CONF_BRIGHTNESS_MODE,
        DEFAULT_BRIGHTNESS_MODE,
        selector.SelectSelector(  # type: ignore[arg-type]
            selector.SelectSelectorConfig(
                options=["default", "linear", "tanh"],
                multiple=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
    ),
    (CONF_BRIGHTNESS_MODE_TIME_DARK, DEFAULT_BRIGHTNESS_MODE_TIME_DARK, int),
    (CONF_BRIGHTNESS_MODE_TIME_LIGHT, DEFAULT_BRIGHTNESS_MODE_TIME_LIGHT, int),
    (CONF_TAKE_OVER_CONTROL, DEFAULT_TAKE_OVER_CONTROL, bool),
    (
        CONF_TAKE_OVER_CONTROL_MODE,
        DEFAULT_TAKE_OVER_CONTROL_MODE,
        selector.SelectSelector(  # type: ignore[arg-type]
            selector.SelectSelectorConfig(
                options=[
                    TakeOverControlMode.PAUSE_ALL.value,
                    TakeOverControlMode.PAUSE_CHANGED.value,
                ],
                multiple=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
    ),
    (CONF_DETECT_NON_HA_CHANGES, DEFAULT_DETECT_NON_HA_CHANGES, bool),
    (
        CONF_AUTORESET_CONTROL,
        DEFAULT_AUTORESET_CONTROL,
        int_between(0, 365 * 24 * 60 * 60),  # 1 year max
    ),
    (CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE, bool),
    (CONF_ADAPT_ONLY_ON_BARE_TURN_ON, DEFAULT_ADAPT_ONLY_ON_BARE_TURN_ON, bool),
    (CONF_SEPARATE_TURN_ON_COMMANDS, DEFAULT_SEPARATE_TURN_ON_COMMANDS, bool),
    (CONF_SEND_SPLIT_DELAY, DEFAULT_SEND_SPLIT_DELAY, int_between(0, 10000)),
    (CONF_ADAPT_DELAY, DEFAULT_ADAPT_DELAY, cv.positive_float),
    (
        CONF_SKIP_REDUNDANT_COMMANDS,
        DEFAULT_SKIP_REDUNDANT_COMMANDS,
        bool,
    ),
    (CONF_INTERCEPT, DEFAULT_INTERCEPT, bool),
    (CONF_MULTI_LIGHT_INTERCEPT, DEFAULT_MULTI_LIGHT_INTERCEPT, bool),
    (CONF_INCLUDE_CONFIG_IN_ATTRIBUTES, DEFAULT_INCLUDE_CONFIG_IN_ATTRIBUTES, bool),
]


def timedelta_as_int(value: timedelta) -> float:
    """Convert a `datetime.timedelta` object to an integer.

    This integer can be serialized to json but a timedelta cannot.
    """
    return value.total_seconds()


# conf_option: (validator, coerce) tuples
# these validators cannot be serialized but can be serialized when coerced by coerce.
EXTRA_VALIDATION: dict[str, tuple[Any, Any]] = {
    CONF_INTERVAL: (cv.time_period, timedelta_as_int),
    CONF_SUNRISE_OFFSET: (cv.time_period, timedelta_as_int),
    CONF_SUNRISE_TIME: (cv.time, str),
    CONF_MIN_SUNRISE_TIME: (cv.time, str),
    CONF_MAX_SUNRISE_TIME: (cv.time, str),
    CONF_SUNSET_OFFSET: (cv.time_period, timedelta_as_int),
    CONF_SUNSET_TIME: (cv.time, str),
    CONF_MIN_SUNSET_TIME: (cv.time, str),
    CONF_MAX_SUNSET_TIME: (cv.time, str),
    CONF_BRIGHTNESS_MODE_TIME_LIGHT: (cv.time_period, timedelta_as_int),
    CONF_BRIGHTNESS_MODE_TIME_DARK: (cv.time_period, timedelta_as_int),
}


def maybe_coerce(key: str, validation: Any) -> vol.All | Any:
    """Coerce the validation into a json serializable type."""
    validation, coerce = EXTRA_VALIDATION.get(key, (validation, None))
    if coerce is not None:
        return vol.All(validation, vol.Coerce(coerce))
    return validation


def replace_none_str(value: Any, replace_with: Any | None = None) -> Any:
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
    },
)


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


SET_MANUAL_CONTROL_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTITY_ID): cv.entity_ids,  # type: ignore[arg-type]
        vol.Optional(CONF_LIGHTS, default=[]): cv.entity_ids,  # type: ignore[arg-type]
        vol.Optional(CONF_MANUAL_CONTROL, default=True): vol.Any(
            cv.boolean,
            vol.In(["brightness", "color"]),
        ),
    },
)
