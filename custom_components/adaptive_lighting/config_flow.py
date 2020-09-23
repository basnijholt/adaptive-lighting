"""Config flow for Coronavirus integration."""
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.components.light import VALID_TRANSITION
from homeassistant.core import callback

from .const import (
    CONF_DISABLE_BRIGHTNESS_ADJUST,
    CONF_DISABLE_ENTITY,
    CONF_DISABLE_STATE,
    CONF_INITIAL_TRANSITION,
    CONF_INTERVAL,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_ONLY_ONCE,
    CONF_SLEEP_BRIGHTNESS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_SLEEP_ENTITY,
    CONF_SLEEP_STATE,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_TIME,
    CONF_TRANSITION,
    DEFAULT_DISABLE_BRIGHTNESS_ADJUST,
    DEFAULT_INITIAL_TRANSITION,
    DEFAULT_INTERVAL,
    DEFAULT_LIGHTS,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MAX_COLOR_TEMP,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MIN_COLOR_TEMP,
    DEFAULT_ONLY_ONCE,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_COLOR_TEMP,
    DEFAULT_SUNRISE_OFFSET,
    DEFAULT_SUNSET_OFFSET,
    DEFAULT_TRANSITION,
    DOMAIN,
    EXTRA_VALIDATION,
    FAKE_NONE,
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adaptive Lighting."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input["name"])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input["name"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("name"): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for Adaptive Lighting."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        errors = {}
        if user_input is not None:
            for key, validate in EXTRA_VALIDATION:
                # these are unserializable validators
                try:
                    value = user_input.get(key)
                    if value is not None and value != FAKE_NONE:
                        validate(user_input[key])
                except vol.Invalid:
                    _LOGGER.exception(
                        "Configuration option %s=%s is incorrect", key, value
                    )
                    errors["base"] = "option_error"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        int_between = lambda a, b: vol.All(vol.Coerce(int), vol.Range(min=a, max=b))
        all_lights = cv.multi_select(self.hass.states.async_entity_ids("light"))
        validation_tuples = [
            (CONF_LIGHTS, DEFAULT_LIGHTS, all_lights),
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

        options_schema = vol.Schema(
            {
                vol.Optional(key, default=options.get(key, default)): validation
                for key, default, validation in validation_tuples
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
