"""Config flow for Adaptive Lighting integration."""

import logging
from datetime import time as dt_time
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
    CONF_MAX_SUNRISE_TIME,
    CONF_MAX_SUNSET_TIME,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MIN_SUNRISE_TIME,
    CONF_MIN_SUNSET_TIME,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_ROOM_PRESET,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_TAKE_OVER_CONTROL,
    DOMAIN,
    EXTRA_VALIDATION,
    NONE_STR,
    ROOM_PRESETS,
    STEP_OPTIONS,
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


def _build_step_schema(
    step_keys: list[str],
    conf_options: dict[str, Any],
    preset_defaults: dict[str, Any],
) -> vol.Schema:
    """Build a voluptuous schema for a single options step.

    Uses preset defaults (from room preset) as fallback when a key has no
    stored value in the config entry.
    """
    to_replace: dict[str, Any] = {
        CONF_LIGHTS: EntitySelector(
            EntitySelectorConfig(
                domain="light",
                multiple=True,
            ),
        ),
    }

    schema = {}
    for name, default, validation in VALIDATION_TUPLES:
        if name not in step_keys:
            continue
        effective_default = conf_options.get(
            name,
            preset_defaults.get(name, default),
        )
        key = vol.Optional(name, default=effective_default)
        value = to_replace.get(name, validation)
        schema[key] = value
    return vol.Schema(schema)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for Adaptive Lighting."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._options: dict[str, Any] = {}
        self._preset_defaults: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Step 1: Essentials
    # ------------------------------------------------------------------
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle Essentials options (Step 1 of 5)."""
        conf = self.config_entry
        data = validate(conf)

        if conf.source == config_entries.SOURCE_IMPORT:
            return self.async_show_form(step_id="init", data_schema=None)

        errors: dict[str, str] = {}

        if user_input is not None:
            # Extract and apply room preset (not persisted)
            preset_name = user_input.pop(CONF_ROOM_PRESET, "custom")
            if preset_name in ROOM_PRESETS:
                self._preset_defaults = ROOM_PRESETS[preset_name]

            validate_options(user_input, errors)

            # Validate brightness range
            min_b = user_input.get(CONF_MIN_BRIGHTNESS, 1)
            max_b = user_input.get(CONF_MAX_BRIGHTNESS, 100)
            if min_b > max_b:
                errors[CONF_MIN_BRIGHTNESS] = "brightness_range_invalid"

            # Validate color temp range
            min_ct = user_input.get(CONF_MIN_COLOR_TEMP, 2000)
            max_ct = user_input.get(CONF_MAX_COLOR_TEMP, 5500)
            if min_ct > max_ct:
                errors[CONF_MIN_COLOR_TEMP] = "color_temp_range_invalid"

            if not errors:
                self._options.update(user_input)
                return await self.async_step_sleep()

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

        # Build schema with room preset selector prepended
        step_schema = _build_step_schema(
            STEP_OPTIONS["init"],
            conf.options,
            self._preset_defaults,
        )
        preset_field = {
            vol.Optional(CONF_ROOM_PRESET, default="custom"): SelectSelector(
                SelectSelectorConfig(
                    options=list(ROOM_PRESETS.keys()),
                    multiple=False,
                    mode=SelectSelectorMode.DROPDOWN,
                ),
            ),
        }
        full_schema = vol.Schema({**preset_field, **step_schema.schema})

        return self.async_show_form(
            step_id="init",
            data_schema=full_schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2: Sleep Mode
    # ------------------------------------------------------------------
    async def async_step_sleep(self, user_input: dict[str, Any] | None = None):
        """Handle Sleep Mode options (Step 2 of 5)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            validate_options(user_input, errors)
            if not errors:
                self._options.update(user_input)
                return await self.async_step_sun_timing()

        schema = _build_step_schema(
            STEP_OPTIONS["sleep"],
            self.config_entry.options,
            self._preset_defaults,
        )
        return self.async_show_form(
            step_id="sleep",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3: Sun & Timing
    # ------------------------------------------------------------------
    async def async_step_sun_timing(self, user_input: dict[str, Any] | None = None):
        """Handle Sun & Timing options (Step 3 of 5)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            validate_options(user_input, errors)

            # Validate sunrise range
            min_sr = user_input.get(CONF_MIN_SUNRISE_TIME, NONE_STR)
            max_sr = user_input.get(CONF_MAX_SUNRISE_TIME, NONE_STR)
            if NONE_STR not in (min_sr, max_sr) and dt_time.fromisoformat(
                min_sr
            ) >= dt_time.fromisoformat(max_sr):
                errors[CONF_MIN_SUNRISE_TIME] = "sunrise_range_invalid"

            # Validate sunset range
            min_ss = user_input.get(CONF_MIN_SUNSET_TIME, NONE_STR)
            max_ss = user_input.get(CONF_MAX_SUNSET_TIME, NONE_STR)
            if NONE_STR not in (min_ss, max_ss) and dt_time.fromisoformat(
                min_ss
            ) >= dt_time.fromisoformat(max_ss):
                errors[CONF_MIN_SUNSET_TIME] = "sunset_range_invalid"

            if not errors:
                self._options.update(user_input)
                return await self.async_step_manual_control()

        schema = _build_step_schema(
            STEP_OPTIONS["sun_timing"],
            self.config_entry.options,
            self._preset_defaults,
        )
        return self.async_show_form(
            step_id="sun_timing",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 4: Behavior (manual control & interception)
    # ------------------------------------------------------------------
    async def async_step_manual_control(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle Behavior options (Step 4 of 5)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            validate_options(user_input, errors)

            take_over = user_input.get(CONF_TAKE_OVER_CONTROL, True)
            intercept = user_input.get(CONF_INTERCEPT, True)

            # detect_non_ha_changes requires take_over_control
            if user_input.get(CONF_DETECT_NON_HA_CHANGES) and not take_over:
                errors[CONF_DETECT_NON_HA_CHANGES] = "requires_take_over_control"

            # adapt_only_on_bare_turn_on requires take_over_control
            if user_input.get(CONF_ADAPT_ONLY_ON_BARE_TURN_ON) and not take_over:
                errors[CONF_ADAPT_ONLY_ON_BARE_TURN_ON] = "requires_take_over_control"

            # multi_light_intercept requires intercept
            if user_input.get(CONF_MULTI_LIGHT_INTERCEPT) and not intercept:
                errors[CONF_MULTI_LIGHT_INTERCEPT] = "requires_intercept"

            if not errors:
                self._options.update(user_input)
                return await self.async_step_workarounds()

        schema = _build_step_schema(
            STEP_OPTIONS["manual_control"],
            self.config_entry.options,
            self._preset_defaults,
        )
        return self.async_show_form(
            step_id="manual_control",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 5: Device Workarounds
    # ------------------------------------------------------------------
    async def async_step_workarounds(self, user_input: dict[str, Any] | None = None):
        """Handle Device Workarounds options (Step 5 of 5)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            validate_options(user_input, errors)

            # send_split_delay requires separate_turn_on_commands
            split_delay = user_input.get(CONF_SEND_SPLIT_DELAY, 0)
            separate = user_input.get(CONF_SEPARATE_TURN_ON_COMMANDS, False)
            if split_delay > 0 and not separate:
                errors[CONF_SEND_SPLIT_DELAY] = "requires_separate_turn_on"

            if not errors:
                self._options.update(user_input)
                return self.async_create_entry(title="", data=self._options)

        schema = _build_step_schema(
            STEP_OPTIONS["workarounds"],
            self.config_entry.options,
            self._preset_defaults,
        )
        return self.async_show_form(
            step_id="workarounds",
            data_schema=schema,
            errors=errors,
        )
