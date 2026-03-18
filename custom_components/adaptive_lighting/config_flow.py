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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (  # pylint: disable=unused-import
    CONF_ADAPT_ONLY_ON_BARE_TURN_ON,
    CONF_DETECT_NON_HA_CHANGES,
    CONF_INTERCEPT,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_ROOM_PRESET,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_TAKE_OVER_CONTROL,
    DOMAIN,
    EXTRA_VALIDATION,
    NONE_STR,
    ROOM_PRESETS,
    STEP_INIT_OPTIONS,
    STEP_MANUAL_CONTROL_OPTIONS,
    STEP_SLEEP_OPTIONS,
    STEP_SUN_TIMING_OPTIONS,
    STEP_WORKAROUNDS_OPTIONS,
    VALIDATION_TUPLES_BY_KEY,
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


def validate_options(
    user_input: dict[str, Any],
    errors: dict[str, str],
    step_keys: list[str] | None = None,
) -> None:
    """Validate the options in the OptionsFlow.

    This is an extra validation step because the validators
    in `EXTRA_VALIDATION` cannot be serialized to json.
    """
    step_key_set = set(step_keys) if step_keys is not None else None
    for key, (_validate, _) in EXTRA_VALIDATION.items():
        if step_key_set is not None and key not in step_key_set:
            continue
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

    def __init__(self) -> None:
        """Initialize options flow."""
        self._options: dict[str, Any] = {}

    def _build_step_schema(
        self,
        step_options: list[str],
        extra_fields: dict | None = None,
    ) -> vol.Schema:
        """Build a schema for a specific step's options."""
        conf = self.config_entry
        to_replace: dict[str, Any] = {}
        if CONF_LIGHTS in step_options:
            to_replace[CONF_LIGHTS] = EntitySelector(
                EntitySelectorConfig(domain="light", multiple=True),
            )
        options_schema = {}
        for name in step_options:
            _name, default, validation = VALIDATION_TUPLES_BY_KEY[name]
            key = vol.Optional(
                name,
                default=self._options.get(name, conf.options.get(name, default)),
            )
            value = to_replace.get(name, validation)
            options_schema[key] = value
        if extra_fields:
            options_schema.update(extra_fields)
        return vol.Schema(options_schema)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Step 1: Essentials — lights, brightness, color temp, and room preset."""
        conf = self.config_entry
        validate(conf)
        if conf.source == config_entries.SOURCE_IMPORT:
            return self.async_show_form(step_id="init", data_schema=None)

        errors: dict[str, str] = {}
        if user_input is not None:
            # Apply room preset overrides
            preset = user_input.pop(CONF_ROOM_PRESET, "custom")
            if preset != "custom":
                preset_values = ROOM_PRESETS.get(preset, {})
                for key, value in preset_values.items():
                    if key in user_input:
                        user_input[key] = value
                    else:
                        # Store cross-step values for later steps
                        self._options[key] = value

            # Validate options
            validate_options(user_input, errors, STEP_INIT_OPTIONS)

            # Range validation
            if user_input.get(CONF_MIN_BRIGHTNESS, 1) > user_input.get(
                CONF_MAX_BRIGHTNESS,
                100,
            ):
                errors[CONF_MIN_BRIGHTNESS] = "brightness_range_invalid"
            if user_input.get(CONF_MIN_COLOR_TEMP, 2000) > user_input.get(
                CONF_MAX_COLOR_TEMP,
                5500,
            ):
                errors[CONF_MIN_COLOR_TEMP] = "color_temp_range_invalid"

            # Light entity existence check
            all_lights = set(self.hass.states.async_entity_ids("light"))
            for configured_light in user_input.get(CONF_LIGHTS, []):
                if configured_light not in all_lights:
                    errors[CONF_LIGHTS] = "entity_missing"
                    break

            if not errors:
                self._options.update(user_input)
                return await self.async_step_sleep()

        # Build schema with room preset selector
        preset_selector = {
            vol.Optional(CONF_ROOM_PRESET, default="custom"): SelectSelector(
                SelectSelectorConfig(
                    options=["custom", *ROOM_PRESETS],
                    multiple=False,
                    mode=SelectSelectorMode.DROPDOWN,
                ),
            ),
        }
        schema = self._build_step_schema(
            STEP_INIT_OPTIONS,
            extra_fields=preset_selector,
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_sleep(self, user_input: dict[str, Any] | None = None):
        """Step 2: Sleep mode settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            validate_options(user_input, errors, STEP_SLEEP_OPTIONS)
            if not errors:
                self._options.update(user_input)
                return await self.async_step_sun_timing()

        return self.async_show_form(
            step_id="sleep",
            data_schema=self._build_step_schema(STEP_SLEEP_OPTIONS),
            errors=errors,
        )

    async def async_step_sun_timing(self, user_input: dict[str, Any] | None = None):
        """Step 3: Sun position and timing settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            validate_options(user_input, errors, STEP_SUN_TIMING_OPTIONS)
            if not errors:
                self._options.update(user_input)
                return await self.async_step_manual_control()

        return self.async_show_form(
            step_id="sun_timing",
            data_schema=self._build_step_schema(STEP_SUN_TIMING_OPTIONS),
            errors=errors,
        )

    async def async_step_manual_control(self, user_input: dict[str, Any] | None = None):
        """Step 4: Behavior — manual control and interception settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            validate_options(user_input, errors, STEP_MANUAL_CONTROL_OPTIONS)

            # Dependency validation
            if user_input.get(CONF_DETECT_NON_HA_CHANGES) and not user_input.get(
                CONF_TAKE_OVER_CONTROL,
            ):
                errors[CONF_DETECT_NON_HA_CHANGES] = "requires_take_over_control"
            if user_input.get(CONF_ADAPT_ONLY_ON_BARE_TURN_ON) and not user_input.get(
                CONF_TAKE_OVER_CONTROL,
            ):
                errors[CONF_ADAPT_ONLY_ON_BARE_TURN_ON] = "requires_take_over_control"
            if user_input.get(CONF_MULTI_LIGHT_INTERCEPT) and not user_input.get(
                CONF_INTERCEPT,
            ):
                errors[CONF_MULTI_LIGHT_INTERCEPT] = "requires_intercept"

            if not errors:
                self._options.update(user_input)
                return await self.async_step_workarounds()

        return self.async_show_form(
            step_id="manual_control",
            data_schema=self._build_step_schema(STEP_MANUAL_CONTROL_OPTIONS),
            errors=errors,
        )

    async def async_step_workarounds(self, user_input: dict[str, Any] | None = None):
        """Step 5: Device workarounds."""
        errors: dict[str, str] = {}
        if user_input is not None:
            validate_options(user_input, errors, STEP_WORKAROUNDS_OPTIONS)

            # Dependency validation
            if user_input.get(CONF_SEND_SPLIT_DELAY, 0) > 0 and not user_input.get(
                CONF_SEPARATE_TURN_ON_COMMANDS,
            ):
                errors[CONF_SEND_SPLIT_DELAY] = "requires_separate_turn_on"

            if not errors:
                self._options.update(user_input)
                return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="workarounds",
            data_schema=self._build_step_schema(STEP_WORKAROUNDS_OPTIONS),
            errors=errors,
        )
