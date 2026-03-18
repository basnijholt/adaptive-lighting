"""Config flow for Adaptive Lighting integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (  # pylint: disable=unused-import
    CONF_BAD_WEATHER,
    CONF_LIGHTS,
    CONF_LUX_SENSOR,
    CONF_LUX_SMOOTHING_SAMPLES,
    CONF_LUX_SMOOTHING_WINDOW,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    EXTRA_VALIDATION,
    NONE_STR,
    VALIDATION_TUPLES,
)
from .switch import validate

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Adaptive Lighting."""

    VERSION = 1

    source_options: dict[str, Any] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is None and self._async_current_entries():
            return await self.async_step_menu()
        return await self.async_step_wait_for_name(user_input)

    async def async_step_menu(self, user_input: dict[str, Any] | None = None):
        """Handle the menu step."""
        if user_input is not None:
            if user_input["action"] != "new":
                entry_id = user_input["action"]
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry:
                    self.source_options = dict(entry.options)
            return await self.async_step_wait_for_name()

        entries = self._async_current_entries()
        options = {"new": "Create new instance"}
        for entry in entries:
            options[entry.entry_id] = f"Duplicate '{entry.title}'"

        return self.async_show_form(
            step_id="menu",
            data_schema=vol.Schema(
                {vol.Required("action", default="new"): vol.In(options)},
            ),
        )

    async def async_step_wait_for_name(self, user_input: dict[str, Any] | None = None):
        """Handle the name step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()
            options = self.source_options
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
                options=options,
            )

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
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004
    ) -> "OptionsFlowHandler":
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


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

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle options flow."""
        conf = self.config_entry
        data = validate(conf)
        if conf.source == config_entries.SOURCE_IMPORT:
            return self.async_show_form(step_id="init", data_schema=None)
        errors: dict[str, str] = {}
        if user_input is not None:
            if CONF_LUX_SENSOR in user_input:
                lux_value = user_input[CONF_LUX_SENSOR]
                if lux_value is None or lux_value == "":
                    user_input[CONF_LUX_SENSOR] = NONE_STR
            else:
                user_input[CONF_LUX_SENSOR] = NONE_STR

            if CONF_WEATHER_ENTITY in user_input:
                weather_value = user_input[CONF_WEATHER_ENTITY]
                if weather_value is None or weather_value == "":
                    user_input[CONF_WEATHER_ENTITY] = NONE_STR
            else:
                user_input[CONF_WEATHER_ENTITY] = NONE_STR

            if CONF_BAD_WEATHER in user_input:
                bad_weather = user_input[CONF_BAD_WEATHER]
                if isinstance(bad_weather, str):
                    user_input[CONF_BAD_WEATHER] = [bad_weather]
                elif bad_weather is None:
                    user_input[CONF_BAD_WEATHER] = []

            validate_options(user_input, errors)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Validate that all configured lights still exist
        all_lights = set(self.hass.states.async_entity_ids("light"))
        for configured_light in data[CONF_LIGHTS]:
            if configured_light not in all_lights:
                errors = {CONF_LIGHTS: "entity_missing"}
                _LOGGER.error(
                    "%s: light entity %s is configured, but was not found",
                    data[CONF_NAME],
                    configured_light,
                )

        to_replace: dict[str, Any] = {
            CONF_LIGHTS: EntitySelector(
                EntitySelectorConfig(
                    domain="light",
                    multiple=True,
                ),
            ),
            CONF_LUX_SENSOR: EntitySelector(
                EntitySelectorConfig(
                    domain="sensor",
                    device_class="illuminance",
                    multiple=False,
                ),
            ),
            CONF_WEATHER_ENTITY: EntitySelector(
                EntitySelectorConfig(
                    domain="weather",
                    multiple=False,
                ),
            ),
            CONF_LUX_SMOOTHING_SAMPLES: NumberSelector(
                NumberSelectorConfig(min=1, max=100, mode=NumberSelectorMode.BOX),
            ),
            CONF_LUX_SMOOTHING_WINDOW: NumberSelector(
                NumberSelectorConfig(min=1, max=3600, mode=NumberSelectorMode.BOX),
            ),
            CONF_BAD_WEATHER: SelectSelector(
                SelectSelectorConfig(
                    options=[
                        "clear-night",
                        "cloudy",
                        "exceptional",
                        "fog",
                        "hail",
                        "lightning",
                        "lightning-rainy",
                        "partlycloudy",
                        "pouring",
                        "rainy",
                        "snowy",
                        "snowy-rainy",
                        "sunny",
                        "windy",
                        "windy-variant",
                    ],
                    multiple=True,
                    custom_value=True,
                ),
            ),
        }

        options_schema = {}
        for name, default, validation in VALIDATION_TUPLES:
            current_value = conf.options.get(name, default)

            if name in (CONF_LUX_SENSOR, CONF_WEATHER_ENTITY):
                key = vol.Optional(name)
            else:
                if name == CONF_BAD_WEATHER:
                    if isinstance(current_value, str):
                        current_value = [current_value]
                    elif current_value is None:
                        current_value = []

                key = vol.Optional(name, default=current_value)

            if name in to_replace:
                value = to_replace[name]
            else:
                if callable(validation) and hasattr(validation, "__module__"):
                    module_name = getattr(validation, "__module__", "")
                    if "config_validation" in module_name:
                        value = str
                    else:
                        value = validation
                else:
                    value = validation

            options_schema[key] = value

        suggested_values = {}
        for name in (CONF_LUX_SENSOR, CONF_WEATHER_ENTITY):
            current_value = conf.options.get(name)
            if current_value and current_value != NONE_STR:
                suggested_values[name] = current_value

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(options_schema), suggested_values
            ),
            errors=errors,
        )
