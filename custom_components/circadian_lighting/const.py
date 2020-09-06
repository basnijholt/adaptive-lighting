import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import VALID_TRANSITION

# Switch and profile settings
CONF_PROFILE = "profile"
CONF_PROFILES = "profiles"
CONF_DISABLE_BRIGHTNESS_ADJUST = "disable_brightness_adjust"
CONF_MIN_BRIGHT, DEFAULT_MIN_BRIGHT = "min_brightness", 1
CONF_MAX_BRIGHT, DEFAULT_MAX_BRIGHT = "max_brightness", 100
CONF_SLEEP_ENTITY = "sleep_entity"
CONF_SLEEP_STATE = "sleep_state"
CONF_SLEEP_CT, DEFAULT_SLEEP_CT = "sleep_colortemp", 1000
CONF_SLEEP_BRIGHT, DEFAULT_SLEEP_BRIGHT = "sleep_brightness", 1
CONF_DISABLE_ENTITY = "disable_entity"
CONF_DISABLE_STATE = "disable_state"
CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
CONF_ONLY_ONCE = "only_once"

_PROFILE_SCHEMA = {
    vol.Optional(CONF_DISABLE_BRIGHTNESS_ADJUST, default=False): cv.boolean,
    vol.Optional(CONF_MIN_BRIGHT, default=DEFAULT_MIN_BRIGHT): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=100)
    ),
    vol.Optional(CONF_MAX_BRIGHT, default=DEFAULT_MAX_BRIGHT): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=100)
    ),
    vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
    vol.Optional(CONF_SLEEP_STATE): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_SLEEP_CT, default=DEFAULT_SLEEP_CT): vol.All(
        vol.Coerce(int), vol.Range(min=1000, max=10000)
    ),
    vol.Optional(CONF_SLEEP_BRIGHT, default=DEFAULT_SLEEP_BRIGHT): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=100)
    ),
    vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
    vol.Optional(CONF_DISABLE_STATE): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(
        CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION
    ): VALID_TRANSITION,
    vol.Optional(CONF_ONLY_ONCE, default=False): cv.boolean,
}
