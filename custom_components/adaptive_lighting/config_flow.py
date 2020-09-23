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
            for key, validate in [
                (CONF_SUNRISE_TIME, cv.time),
                (CONF_SUNSET_TIME, cv.time),
                (CONF_SUNRISE_OFFSET, cv.time_period),
                (CONF_SUNSET_OFFSET, cv.time_period),
                (CONF_INTERVAL, cv.time_period),
                (CONF_DISABLE_ENTITY, cv.entity_id),
                (CONF_SLEEP_ENTITY, cv.entity_id),
                (CONF_DISABLE_STATE, vol.All(cv.ensure_list_csv, [cv.string])),
                (CONF_SLEEP_STATE, vol.All(cv.ensure_list_csv, [cv.string])),
            ]:
                try:
                    value = user_input.get(key)
                    if value == FAKE_NONE:
                        value = None
                    if value is not None:
                        validate(user_input[key])
                except vol.Invalid:
                    _LOGGER.exception("Configuration option %s=%s is incorrect", key, value)
                    errors["base"] = "option_error"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        lights = options.get(CONF_LIGHTS, DEFAULT_LIGHTS)
        disable_brightness_adjust = options.get(
            CONF_DISABLE_BRIGHTNESS_ADJUST, DEFAULT_DISABLE_BRIGHTNESS_ADJUST
        )
        disable_entity = options.get(CONF_DISABLE_ENTITY, FAKE_NONE)
        disable_state = options.get(CONF_DISABLE_STATE, FAKE_NONE)
        initial_transition = options.get(
            CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION
        )
        interval = options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        max_brightness = options.get(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS)
        max_color_temp = options.get(CONF_MAX_COLOR_TEMP, DEFAULT_MAX_COLOR_TEMP)
        min_brightness = options.get(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS)
        min_color_temp = options.get(CONF_MIN_COLOR_TEMP, DEFAULT_MIN_COLOR_TEMP)
        only_once = options.get(CONF_ONLY_ONCE, DEFAULT_ONLY_ONCE)
        sleep_brightness = options.get(CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS)
        sleep_color_temp = options.get(CONF_SLEEP_COLOR_TEMP, DEFAULT_SLEEP_COLOR_TEMP)
        sleep_entity = options.get(CONF_SLEEP_ENTITY, FAKE_NONE)
        sleep_state = options.get(CONF_SLEEP_STATE, FAKE_NONE)
        sunrise_offset = options.get(CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET)
        sunrise_time = options.get(CONF_SUNRISE_TIME, FAKE_NONE)
        sunset_offset = options.get(CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET)
        sunset_time = options.get(CONF_SUNSET_TIME, FAKE_NONE)
        transition = options.get(CONF_TRANSITION, DEFAULT_TRANSITION)

        all_lights = self.hass.states.async_entity_ids("light")
        all_lights = cv.multi_select(all_lights)

        options_schema = vol.Schema(
            {
                vol.Optional(CONF_LIGHTS, default=lights): all_lights,
                vol.Optional(
                    CONF_DISABLE_BRIGHTNESS_ADJUST, default=disable_brightness_adjust
                ): bool,
                vol.Optional(CONF_DISABLE_ENTITY, default=disable_entity): str,
                vol.Optional(CONF_DISABLE_STATE, default=disable_state): str,
                vol.Optional(
                    CONF_INITIAL_TRANSITION, default=initial_transition
                ): VALID_TRANSITION,
                vol.Optional(CONF_INTERVAL, default=interval): cv.positive_int,
                vol.Optional(CONF_MAX_BRIGHTNESS, default=max_brightness): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Optional(CONF_MAX_COLOR_TEMP, default=max_color_temp): vol.All(
                    vol.Coerce(int), vol.Range(min=1000, max=10000)
                ),
                vol.Optional(CONF_MIN_BRIGHTNESS, default=min_brightness): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Optional(CONF_MIN_COLOR_TEMP, default=min_color_temp): vol.All(
                    vol.Coerce(int), vol.Range(min=1000, max=10000)
                ),
                vol.Optional(CONF_ONLY_ONCE, default=only_once): bool,
                vol.Optional(CONF_SLEEP_BRIGHTNESS, default=sleep_brightness): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Optional(CONF_SLEEP_COLOR_TEMP, default=sleep_color_temp): vol.All(
                    vol.Coerce(int), vol.Range(min=1000, max=10000)
                ),
                vol.Optional(CONF_SLEEP_ENTITY, default=sleep_entity): str,
                vol.Optional(CONF_SLEEP_STATE, default=sleep_state): str,
                vol.Optional(CONF_SUNRISE_OFFSET, default=sunrise_offset): int,
                vol.Optional(CONF_SUNRISE_TIME, default=sunrise_time): str,
                vol.Optional(CONF_SUNSET_OFFSET, default=sunset_offset): int,
                vol.Optional(CONF_SUNSET_TIME, default=sunset_time): str,
                vol.Optional(CONF_TRANSITION, default=transition): VALID_TRANSITION,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
