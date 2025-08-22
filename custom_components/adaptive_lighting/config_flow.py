"""Config flow for Adaptive Lighting integration."""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, MAJOR_VERSION, MINOR_VERSION
from homeassistant.core import callback

from .const import (  # pylint: disable=unused-import
    CONF_LIGHTS,
    DOMAIN,
    EXTRA_VALIDATION,
    NONE_STR,
    VALIDATION_TUPLES,
)
from .helpers import get_friendly_name
from .switch import _supported_features, validate

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adaptive Lighting."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME): str}),
            errors=errors,
        )

    async def async_step_import(self, user_input: dict[str, Any] | None = None):
        """Handle configuration by YAML file."""
        if user_input is None:
            return self.async_abort(reason="no_data")

        await self.async_set_unique_id(user_input[CONF_NAME])
        # Keep a list of switches that are configured via YAML
        data = self.hass.data.setdefault(DOMAIN, {})
        data.setdefault("__yaml__", set()).add(self.unique_id)

        for entry in self._async_current_entries():
            if entry.unique_id == self.unique_id:
                self.hass.config_entries.async_update_entry(entry, data=user_input)
                self._abort_if_unique_id_configured()

        return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Get the options flow for this handler."""
        if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 12):
            # https://github.com/home-assistant/core/pull/129651
            return OptionsFlowHandler()
        return OptionsFlowHandler(config_entry)


def validate_options(user_input: dict[str, Any], errors: dict[str, str]) -> None:
    """Validate the options in the OptionsFlow.

    This is an extra validation step because the validators
    in `EXTRA_VALIDATION` cannot be serialized to json.
    """
    for key, (_validate, _) in EXTRA_VALIDATION.items():
        # these are unserializable validators
        value = user_input.get(key)
        try:
            if value is not None and value != NONE_STR:
                _validate(value)
        except vol.Invalid:
            _LOGGER.exception("Configuration option %s=%s is incorrect", key, value)
            errors["base"] = "option_error"


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for Adaptive Lighting."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize options flow."""
        if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 12):
            super().__init__(*args, **kwargs)
            # https://github.com/home-assistant/core/pull/129651
        else:
            self.config_entry = args[0]

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle options flow."""
        conf = self.config_entry
        data = validate(conf)
        if conf.source == config_entries.SOURCE_IMPORT:
            return self.async_show_form(step_id="init", data_schema=None)
        errors = {}
        if user_input is not None:
            validate_options(user_input, errors)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        all_lights_with_names = {
            light: get_friendly_name(self.hass, light)
            for light in self.hass.states.async_entity_ids("light")
            if _supported_features(self.hass, light)
        }
        all_lights = list(all_lights_with_names.keys())
        for configured_light in data[CONF_LIGHTS]:
            if configured_light not in all_lights:
                errors = {CONF_LIGHTS: "entity_missing"}
                _LOGGER.error(
                    "%s: light entity %s is configured, but was not found",
                    data[CONF_NAME],
                    configured_light,
                )
                all_lights.append(configured_light)
                all_lights_with_names[configured_light] = configured_light

        light_options = {
            entity_id: f"{name} ({entity_id})"
            for entity_id, name in all_lights_with_names.items()
        }
        to_replace = {CONF_LIGHTS: cv.multi_select(light_options)}

        options_schema = {}
        for name, default, validation in VALIDATION_TUPLES:
            key = vol.Optional(name, default=conf.options.get(name, default))
            value = to_replace.get(name, validation)
            options_schema[key] = value

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options_schema),
            errors=errors,
        )
