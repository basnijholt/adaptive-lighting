"""Config flow for Adaptive Lighting integration."""

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, MAJOR_VERSION, MINOR_VERSION
from homeassistant.core import callback

from .const import (  # pylint: disable=unused-import
    BASIC_OPTIONS,
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
        self._basic_options: dict[str, Any] = {}
        self._all_lights_with_names: dict[str, str] = {}

    def _prepare_lights_schema(self) -> tuple[dict[str, Any], dict[str, str]]:
        """Get available lights and build the multi-select schema.

        Returns tuple of (to_replace dict for schema, errors dict).
        Also populates self._all_lights_with_names.
        """
        conf = self.config_entry
        data = validate(conf)
        errors: dict[str, str] = {}

        self._all_lights_with_names = {
            light: get_friendly_name(self.hass, light)
            for light in self.hass.states.async_entity_ids("light")
            if _supported_features(self.hass, light)
        }
        all_lights = list(self._all_lights_with_names.keys())

        for configured_light in data[CONF_LIGHTS]:
            if configured_light not in all_lights:
                errors[CONF_LIGHTS] = "entity_missing"
                _LOGGER.error(
                    "%s: light entity %s is configured, but was not found",
                    data[CONF_NAME],
                    configured_light,
                )
                all_lights.append(configured_light)
                self._all_lights_with_names[configured_light] = configured_light

        light_options = {
            entity_id: f"{name} ({entity_id})"
            for entity_id, name in self._all_lights_with_names.items()
        }
        to_replace = {CONF_LIGHTS: cv.multi_select(light_options)}
        return to_replace, errors

    def _build_options_schema(
        self,
        to_replace: dict[str, Any],
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> vol.Schema:
        """Build schema for specified options.

        Args:
            to_replace: Dict of option names to replacement validators.
            include: If provided, only include these option names.
            exclude: If provided, exclude these option names.

        """
        conf = self.config_entry

        options_schema = {}
        for name, default, validation in VALIDATION_TUPLES:
            # Filter based on include/exclude
            if include is not None and name not in include:
                continue
            if exclude is not None and name in exclude:
                continue

            key = vol.Optional(name, default=conf.options.get(name, default))
            value = to_replace.get(name, validation)
            options_schema[key] = value

        return vol.Schema(options_schema)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle options flow - Step 1: Basic options."""
        conf = self.config_entry
        if conf.source == config_entries.SOURCE_IMPORT:
            return self.async_show_form(step_id="init", data_schema=None)

        to_replace, errors = self._prepare_lights_schema()

        if user_input is not None:
            validate_options(user_input, errors)
            if not errors:
                self._basic_options = user_input
                # Show menu to choose between advanced options or finish
                return self.async_show_menu(
                    step_id="init",
                    menu_options=["advanced", "finish"],
                )

        basic_schema = self._build_options_schema(to_replace, include=BASIC_OPTIONS)
        return self.async_show_form(
            step_id="init",
            data_schema=basic_schema,
            errors=errors,
        )

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None):
        """Handle options flow - Step 2: Advanced options (optional)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge basic + advanced options
            combined = {**self._basic_options, **user_input}
            validate_options(combined, errors)
            if not errors:
                return self.async_create_entry(title="", data=combined)

        # Need to_replace for building schema (though advanced step doesn't use lights)
        to_replace, _ = self._prepare_lights_schema()
        advanced_schema = self._build_options_schema(to_replace, exclude=BASIC_OPTIONS)
        return self.async_show_form(
            step_id="advanced",
            data_schema=advanced_schema,
            errors=errors,
        )

    async def async_step_finish(
        self,
        user_input: dict[str, Any] | None = None,  # noqa: ARG002
    ):
        """Finish configuration without advanced options."""
        errors: dict[str, str] = {}
        validate_options(self._basic_options, errors)
        if not errors:
            return self.async_create_entry(title="", data=self._basic_options)
        # If validation fails, go back to init
        return await self.async_step_init()
