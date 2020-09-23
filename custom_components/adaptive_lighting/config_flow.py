"""Config flow for Coronavirus integration."""
import logging
from copy import copy

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    EXTRA_VALIDATION,
    FAKE_NONE,
    VALIDATION_TUPLES,
    get_domain_schema,
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

    async def async_step_import(self, user_input=None):
        """Handle configuration by yaml file."""
        _DOMAIN_SCHEMA = get_domain_schema(with_fake_none=False)
        schema = {k: v for k, v in _DOMAIN_SCHEMA.items() if k in user_input}
        vol.Schema(schema)(user_input)
        _LOGGER.error(str(user_input) + str(schema))
        return self.async_create_entry(title=user_input["name"], data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


def validate_options(user_input, errors):
    for key, validate in EXTRA_VALIDATION.items():
        # these are unserializable validators
        try:
            value = user_input.get(key)
            if value is not None and value != FAKE_NONE:
                validate(value)
        except vol.Invalid:
            _LOGGER.exception("Configuration option %s=%s is incorrect", key, value)
            errors["base"] = "option_error"


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for Adaptive Lighting."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        errors = {}
        if user_input is not None:
            validate_options(user_input, errors)
            if not errors:
                return self.async_create_entry(
                    title=user_input["name"], data=user_input
                )

        all_lights = cv.multi_select(self.hass.states.async_entity_ids("light"))
        validation_tuples = copy(VALIDATION_TUPLES)
        lights_tuple = (*validation_tuples[0][:-1], all_lights)
        validation_tuples[0] = lights_tuple

        options = self.config_entry.options
        options_schema = vol.Schema(
            {
                vol.Optional(key, default=options.get(key, default)): validation
                for key, default, validation in validation_tuples
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
