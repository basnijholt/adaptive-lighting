"""Switch for the Adaptive Lighting integration."""
from __future__ import annotations

import asyncio
import datetime
import logging
import zoneinfo
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Literal

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import ulid_transform
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODE_RGB,
    COLOR_MODE_RGBW,
    COLOR_MODE_RGBWW,
    COLOR_MODE_XY,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    SUPPORT_TRANSITION,
    is_on,
    preprocess_turn_on_alternatives,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_DOMAIN,
    ATTR_ENTITY_ID,
    ATTR_SERVICE,
    ATTR_SERVICE_DATA,
    ATTR_SUPPORTED_FEATURES,
    CONF_NAME,
    CONF_PARAMS,
    EVENT_CALL_SERVICE,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_STATE_CHANGED,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    HomeAssistant,
    ServiceCall,
    State,
    callback,
)
from homeassistant.helpers import entity_platform, entity_registry
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.sun import get_astral_location
from homeassistant.helpers.template import area_entities
from homeassistant.loader import bind_hass
from homeassistant.util import slugify
from homeassistant.util.color import (
    color_temperature_to_rgb,
    color_xy_to_RGB,
)

from .adaptation_utils import (
    BRIGHTNESS_ATTRS,
    COLOR_ATTRS,
    AdaptationData,
    ServiceData,
    prepare_adaptation_data,
)
from .color_and_brightness import SunLightSettings
from .const import (
    ADAPT_BRIGHTNESS_SWITCH,
    ADAPT_COLOR_SWITCH,
    ATTR_ADAPT_BRIGHTNESS,
    ATTR_ADAPT_COLOR,
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_ADAPT_DELAY,
    CONF_ADAPT_ONLY_ON_BARE_TURN_ON,
    CONF_ADAPT_UNTIL_SLEEP,
    CONF_AUTORESET_CONTROL,
    CONF_BRIGHTNESS_MODE,
    CONF_BRIGHTNESS_MODE_TIME_DARK,
    CONF_BRIGHTNESS_MODE_TIME_LIGHT,
    CONF_DETECT_NON_HA_CHANGES,
    CONF_INCLUDE_CONFIG_IN_ATTRIBUTES,
    CONF_INITIAL_TRANSITION,
    CONF_INTERCEPT,
    CONF_INTERVAL,
    CONF_LIGHTS,
    CONF_MANUAL_CONTROL,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MAX_SUNRISE_TIME,
    CONF_MAX_SUNSET_TIME,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MIN_SUNRISE_TIME,
    CONF_MIN_SUNSET_TIME,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_ONLY_ONCE,
    CONF_PREFER_RGB_COLOR,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_BRIGHTNESS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_SLEEP_RGB_COLOR,
    CONF_SLEEP_RGB_OR_COLOR_TEMP,
    CONF_SLEEP_TRANSITION,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_TIME,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
    CONF_TURN_ON_LIGHTS,
    CONF_USE_DEFAULTS,
    DOMAIN,
    EXTRA_VALIDATION,
    ICON_BRIGHTNESS,
    ICON_COLOR_TEMP,
    ICON_MAIN,
    ICON_SLEEP,
    SERVICE_APPLY,
    SERVICE_CHANGE_SWITCH_SETTINGS,
    SERVICE_SET_MANUAL_CONTROL,
    SET_MANUAL_CONTROL_SCHEMA,
    SLEEP_MODE_SWITCH,
    TURNING_OFF_DELAY,
    VALIDATION_TUPLES,
    apply_service_schema,
    replace_none_str,
)
from .hass_utils import setup_service_call_interceptor
from .helpers import (
    clamp,
    color_difference_redmean,
    int_to_base36,
    remove_vowels,
    short_hash,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_SUPPORT_OPTS = {
    "brightness": SUPPORT_BRIGHTNESS,
    "color_temp": SUPPORT_COLOR_TEMP,
    "color": SUPPORT_COLOR,
    "transition": SUPPORT_TRANSITION,
}


_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)

# Consider it a significant change when attribute changes more than
BRIGHTNESS_CHANGE = 25  # ≈10% of total range
COLOR_TEMP_CHANGE = 100  # ≈3% of total range (2000-6500)
RGB_REDMEAN_CHANGE = 80  # ≈10% of total range


# Keep a short domain version for the context instances (which can only be 36 chars)
_DOMAIN_SHORT = "al"


def create_context(
    name: str,
    which: str,
    index: int,
    parent: Context | None = None,
) -> Context:
    """Create a context that can identify this integration."""
    # Use a hash for the name because otherwise the context might become
    # too long (max len == 26) to fit in the database.
    # Pack index with base85 to maximize the number of contexts we can create
    # before we exceed the 26-character limit and are forced to wrap.
    time_stamp = ulid_transform.ulid_now()[:10]  # time part of a ULID
    name_hash = short_hash(name)
    which_short = remove_vowels(which)
    context_id_start = f"{time_stamp}:{_DOMAIN_SHORT}:{name_hash}:{which_short}:"
    chars_left = 26 - len(context_id_start)
    index_packed = int_to_base36(index).zfill(chars_left)[-chars_left:]
    context_id = context_id_start + index_packed
    parent_id = parent.id if parent else None
    return Context(id=context_id, parent_id=parent_id)


def is_our_context_id(context_id: str | None, which: str | None = None) -> bool:
    """Check whether this integration created 'context_id'."""
    if context_id is None:
        return False

    is_al = f":{_DOMAIN_SHORT}:" in context_id
    if not is_al:
        return False
    if which is None:
        return True
    return f":{remove_vowels(which)}:" in context_id


def is_our_context(context: Context | None, which: str | None = None) -> bool:
    """Check whether this integration created 'context'."""
    if context is None:
        return False
    return is_our_context_id(context.id, which)


@bind_hass
def _switches_with_lights(
    hass: HomeAssistant,
    lights: list[str],
    expand_light_groups: bool = True,
) -> list[AdaptiveSwitch]:
    """Get all switches that control at least one of the lights passed."""
    config_entries = hass.config_entries.async_entries(DOMAIN)
    data = hass.data[DOMAIN]
    switches = []
    all_check_lights = (
        _expand_light_groups(hass, lights) if expand_light_groups else set(lights)
    )
    for config in config_entries:
        entry = data.get(config.entry_id)
        if entry is None:  # entry might be disabled and therefore missing
            continue
        switch = data[config.entry_id][SWITCH_DOMAIN]
        switch._expand_light_groups()
        # Check if any of the lights are in the switch's lights
        if set(switch.lights) & set(all_check_lights):
            switches.append(switch)
    return switches


class NoSwitchFoundError(ValueError):
    """No switches found for lights."""


@bind_hass
def _switch_with_lights(
    hass: HomeAssistant,
    lights: list[str],
    expand_light_groups: bool = True,
) -> AdaptiveSwitch:
    """Find the switch that controls the lights in 'lights'."""
    switches = _switches_with_lights(hass, lights, expand_light_groups)
    if len(switches) == 1:
        return switches[0]
    if len(switches) > 1:
        on_switches = [s for s in switches if s.is_on]
        if len(on_switches) == 1:
            # Of the multiple switches, only one is on
            return on_switches[0]
        msg = (
            f"_switch_with_lights: Light(s) {lights} found in multiple switch configs"
            f" ({[s.entity_id for s in switches]}). You must pass a switch under"
            " 'entity_id'."
        )
        raise NoSwitchFoundError(msg)
    msg = (
        f"_switch_with_lights: Light(s) {lights} not found in any switch's"
        " configuration. You must either include the light(s) that is/are"
        " in the integration config, or pass a switch under 'entity_id'."
    )
    raise NoSwitchFoundError(msg)


# For documentation on this function, see integration_entities() from HomeAssistant Core:
# https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/template.py#L1109
@bind_hass
def _switches_from_service_call(
    hass: HomeAssistant,
    service_call: ServiceCall,
) -> list[AdaptiveSwitch]:
    data = service_call.data
    lights = data[CONF_LIGHTS]
    switch_entity_ids: list[str] | None = data.get("entity_id")

    if not lights and not switch_entity_ids:
        msg = (
            "adaptive-lighting: Neither a switch nor a light was provided in the service call."
            " If you intend to adapt all lights on all switches, please inform the"
            " developers at https://github.com/basnijholt/adaptive-lighting about your"
            " use case. Currently, you must pass either an adaptive-lighting switch or"
            " the lights to an `adaptive_lighting` service call."
        )
        raise ValueError(msg)

    if switch_entity_ids is not None:
        if len(switch_entity_ids) > 1 and lights:
            msg = (
                "adaptive-lighting: Cannot pass multiple switches with lights argument."
                f" Invalid service data received: {service_call.data}"
            )
            raise ValueError(msg)
        switches = []
        ent_reg = entity_registry.async_get(hass)
        for entity_id in switch_entity_ids:
            ent_entry = ent_reg.async_get(entity_id)
            assert ent_entry is not None
            config_id = ent_entry.config_entry_id
            switches.append(hass.data[DOMAIN][config_id][SWITCH_DOMAIN])
        return switches

    if lights:
        switch = _switch_with_lights(hass, lights)
        return [switch]

    msg = (
        "adaptive-lighting: Incorrect data provided in service call."
        f" Entities not found in the integration. Service data: {service_call.data}"
    )
    raise ValueError(msg)


async def handle_change_switch_settings(
    switch: AdaptiveSwitch,
    service_call: ServiceCall,
) -> None:
    """Allows HASS to change config values via a service call."""
    data = service_call.data
    which = data.get(CONF_USE_DEFAULTS, "current")
    if which == "current":  # use whatever we're already using.
        defaults = switch._current_settings  # pylint: disable=protected-access
    elif which == "factory":  # use actual defaults listed in the documentation
        defaults = None
    elif which == "configuration":
        # use whatever's in the config flow or configuration.yaml
        defaults = switch._config_backup
    else:
        defaults = None

    # deep copy the defaults so we don't modify the original dicts
    switch._set_changeable_settings(data=data, defaults=deepcopy(defaults))
    switch._update_time_interval_listener()

    _LOGGER.debug(
        "Called 'adaptive_lighting.change_switch_settings' service with '%s'",
        data,
    )

    switch.manager.reset(*switch.lights, reset_manual_control=False)
    if switch.is_on:
        await switch._update_attrs_and_maybe_adapt_lights(  # pylint: disable=protected-access
            context=switch.create_context("service", parent=service_call.context),
            lights=switch.lights,
            transition=switch.initial_transition,
            force=True,
        )


@callback
def _fire_manual_control_event(
    switch: AdaptiveSwitch,
    light: str,
    context: Context,
):
    """Fire an event that 'light' is marked as manual_control."""
    hass = switch.hass
    _LOGGER.debug(
        "'adaptive_lighting.manual_control' event fired for %s for light %s",
        switch.entity_id,
        light,
    )
    switch.manager.mark_as_manual_control(light)
    hass.bus.async_fire(
        f"{DOMAIN}.manual_control",
        {ATTR_ENTITY_ID: light, SWITCH_DOMAIN: switch.entity_id},
        context=context,
    )


async def async_setup_entry(  # noqa: PLR0915
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the AdaptiveLighting switch."""
    assert hass is not None
    data = hass.data[DOMAIN]
    assert config_entry.entry_id in data
    _LOGGER.debug(
        "Setting up AdaptiveLighting with data: %s and config_entry %s",
        data,
        config_entry,
    )
    if (  # Skip deleted YAML config entries or first time YAML config entries
        config_entry.source == SOURCE_IMPORT
        and config_entry.unique_id not in data.get("__yaml__", set())
    ):
        _LOGGER.warning(
            "Deleting AdaptiveLighting switch '%s' because YAML"
            " defined switch has been removed from YAML configuration",
            config_entry.unique_id,
        )
        await hass.config_entries.async_remove(config_entry.entry_id)
        return

    if (manager := data.get(ATTR_ADAPTIVE_LIGHTING_MANAGER)) is None:
        manager = AdaptiveLightingManager(hass)
        data[ATTR_ADAPTIVE_LIGHTING_MANAGER] = manager

    sleep_mode_switch = SimpleSwitch(
        which="Sleep Mode",
        initial_state=False,
        hass=hass,
        config_entry=config_entry,
        icon=ICON_SLEEP,
    )
    adapt_color_switch = SimpleSwitch(
        which="Adapt Color",
        initial_state=True,
        hass=hass,
        config_entry=config_entry,
        icon=ICON_COLOR_TEMP,
    )
    adapt_brightness_switch = SimpleSwitch(
        which="Adapt Brightness",
        initial_state=True,
        hass=hass,
        config_entry=config_entry,
        icon=ICON_BRIGHTNESS,
    )
    switch = AdaptiveSwitch(
        hass,
        config_entry,
        manager,
        sleep_mode_switch,
        adapt_color_switch,
        adapt_brightness_switch,
    )

    data[config_entry.entry_id][SLEEP_MODE_SWITCH] = sleep_mode_switch
    data[config_entry.entry_id][ADAPT_COLOR_SWITCH] = adapt_color_switch
    data[config_entry.entry_id][ADAPT_BRIGHTNESS_SWITCH] = adapt_brightness_switch
    data[config_entry.entry_id][SWITCH_DOMAIN] = switch

    async_add_entities(
        [sleep_mode_switch, adapt_color_switch, adapt_brightness_switch, switch],
        update_before_add=True,
    )

    @callback
    async def handle_apply(service_call: ServiceCall):
        """Handle the entity service apply."""
        data = service_call.data
        _LOGGER.debug(
            "Called 'adaptive_lighting.apply' service with '%s'",
            data,
        )
        switches = _switches_from_service_call(hass, service_call)
        lights = data[CONF_LIGHTS]
        for switch in switches:
            if not lights:
                all_lights = switch.lights
            else:
                all_lights = _expand_light_groups(hass, lights)
            switch.manager.lights.update(all_lights)
            for light in all_lights:
                if data[CONF_TURN_ON_LIGHTS] or is_on(hass, light):
                    context = switch.create_context(
                        "service",
                        parent=service_call.context,
                    )
                    await switch._adapt_light(  # pylint: disable=protected-access
                        light,
                        context=context,
                        transition=data[CONF_TRANSITION],
                        adapt_brightness=data[ATTR_ADAPT_BRIGHTNESS],
                        adapt_color=data[ATTR_ADAPT_COLOR],
                        prefer_rgb_color=data[CONF_PREFER_RGB_COLOR],
                        force=True,
                    )

    @callback
    async def handle_set_manual_control(service_call: ServiceCall):
        """Set or unset lights as 'manually controlled'."""
        data = service_call.data
        _LOGGER.debug(
            "Called 'adaptive_lighting.set_manual_control' service with '%s'",
            data,
        )
        switches = _switches_from_service_call(hass, service_call)
        lights = data[CONF_LIGHTS]
        for switch in switches:
            if not lights:
                all_lights = switch.lights
            else:
                all_lights = _expand_light_groups(hass, lights)
            if service_call.data[CONF_MANUAL_CONTROL]:
                for light in all_lights:
                    _fire_manual_control_event(switch, light, service_call.context)
            else:
                switch.manager.reset(*all_lights)
                if switch.is_on:
                    context = switch.create_context(
                        "service",
                        parent=service_call.context,
                    )
                    # pylint: disable=protected-access
                    await switch._update_attrs_and_maybe_adapt_lights(
                        context=context,
                        lights=all_lights,
                        transition=switch.initial_transition,
                        force=True,
                    )

    # Register `apply` service
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_APPLY,
        service_func=handle_apply,
        schema=apply_service_schema(switch.initial_transition),
    )

    # Register `set_manual_control` service
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_SET_MANUAL_CONTROL,
        service_func=handle_set_manual_control,
        schema=SET_MANUAL_CONTROL_SCHEMA,
    )

    args = {vol.Optional(CONF_USE_DEFAULTS, default="current"): cv.string}
    # Modifying these after init isn't possible
    skip = (CONF_INTERVAL, CONF_NAME, CONF_LIGHTS)
    for k, _, valid in VALIDATION_TUPLES:
        if k not in skip:
            args[vol.Optional(k)] = valid
    platform = entity_platform.current_platform.get()
    assert platform is not None
    platform.async_register_entity_service(
        SERVICE_CHANGE_SWITCH_SETTINGS,
        args,
        handle_change_switch_settings,
    )


def validate(
    config_entry: ConfigEntry | None,
    service_data: dict[str, Any] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get the options and data from the config_entry and add defaults."""
    if defaults is None:
        data = {key: default for key, default, _ in VALIDATION_TUPLES}
    else:
        data = deepcopy(defaults)

    if config_entry is not None:
        assert service_data is None
        assert defaults is None
        data.update(config_entry.options)  # come from options flow
        data.update(config_entry.data)  # all yaml settings come from data
    else:
        assert service_data is not None
        changed_settings = {
            key: value
            for key, value in service_data.items()
            if key not in (CONF_USE_DEFAULTS, ATTR_ENTITY_ID)
        }
        data.update(changed_settings)
    data = {key: replace_none_str(value) for key, value in data.items()}
    for key, (validate_value, _) in EXTRA_VALIDATION.items():
        value = data.get(key)
        if value is not None:
            data[key] = validate_value(value)  # Fix the types of the inputs
    return data


def _is_state_event(event: Event, from_or_to_state: Iterable[str]):
    """Match state event when either 'from_state' or 'to_state' matches."""
    return (
        (old_state := event.data.get("old_state")) is not None
        and old_state.state in from_or_to_state
    ) or (
        (new_state := event.data.get("new_state")) is not None
        and new_state.state in from_or_to_state
    )


@bind_hass
def _expand_light_groups(
    hass: HomeAssistant,
    lights: list[str],
) -> list[str]:
    all_lights = set()
    manager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    for light in lights:
        state = hass.states.get(light)
        if state is None:
            _LOGGER.debug("State of %s is None", light)
            all_lights.add(light)
        elif _is_light_group(state):
            group = state.attributes["entity_id"]
            manager.lights.discard(light)
            all_lights.update(group)
            _LOGGER.debug("Expanded %s to %s", light, group)
        else:
            all_lights.add(light)
    return sorted(all_lights)


def _is_light_group(state: State) -> bool:
    return "entity_id" in state.attributes


@bind_hass
def _supported_features(hass: HomeAssistant, light: str) -> set[str]:
    state = hass.states.get(light)
    assert state is not None
    supported_features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
    assert isinstance(supported_features, int)
    supported = {
        key for key, value in _SUPPORT_OPTS.items() if supported_features & value
    }

    supported_color_modes = state.attributes.get(ATTR_SUPPORTED_COLOR_MODES, set())
    color_modes = {
        COLOR_MODE_RGB,
        COLOR_MODE_RGBW,
        COLOR_MODE_RGBWW,
        COLOR_MODE_XY,
        COLOR_MODE_HS,
    }

    # Adding brightness when color mode is supported, see
    # comment https://github.com/basnijholt/adaptive-lighting/issues/112#issuecomment-836944011

    for mode in color_modes:
        if mode in supported_color_modes:
            supported.update({"color", "brightness"})
            break

    if COLOR_MODE_COLOR_TEMP in supported_color_modes:
        supported.update({"color_temp", "brightness"})

    if COLOR_MODE_BRIGHTNESS in supported_color_modes:
        supported.add("brightness")

    return supported


# All comparisons should be done with RGB since
# converting anything to color temp is inaccurate.
def _convert_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    if ATTR_RGB_COLOR in attributes:
        return attributes

    rgb = None
    if (color := attributes.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
        rgb = color_temperature_to_rgb(color)
    elif (color := attributes.get(ATTR_XY_COLOR)) is not None:
        rgb = color_xy_to_RGB(*color)

    if rgb is not None:
        attributes[ATTR_RGB_COLOR] = rgb
        _LOGGER.debug(f"Converted {attributes} to rgb {rgb}")
    else:
        _LOGGER.debug("No suitable color conversion found for %s", attributes)

    return attributes


def _add_missing_attributes(
    old_attributes: dict[str, Any],
    new_attributes: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not any(
        attr in old_attributes and attr in new_attributes
        for attr in [ATTR_COLOR_TEMP_KELVIN, ATTR_RGB_COLOR]
    ):
        old_attributes = _convert_attributes(old_attributes)
        new_attributes = _convert_attributes(new_attributes)

    return old_attributes, new_attributes


def _attributes_have_changed(
    light: str,
    old_attributes: dict[str, Any],
    new_attributes: dict[str, Any],
    adapt_brightness: bool,
    adapt_color: bool,
    context: Context,
) -> bool:
    if adapt_color:
        old_attributes, new_attributes = _add_missing_attributes(
            old_attributes,
            new_attributes,
        )

    if (
        adapt_brightness
        and ATTR_BRIGHTNESS in old_attributes
        and ATTR_BRIGHTNESS in new_attributes
    ):
        last_brightness = old_attributes[ATTR_BRIGHTNESS]
        current_brightness = new_attributes[ATTR_BRIGHTNESS]
        if abs(current_brightness - last_brightness) > BRIGHTNESS_CHANGE:
            _LOGGER.debug(
                "Brightness of '%s' significantly changed from %s to %s with"
                " context.id='%s'",
                light,
                last_brightness,
                current_brightness,
                context.id,
            )
            return True

    if (
        adapt_color
        and ATTR_COLOR_TEMP_KELVIN in old_attributes
        and ATTR_COLOR_TEMP_KELVIN in new_attributes
    ):
        last_color_temp = old_attributes[ATTR_COLOR_TEMP_KELVIN]
        current_color_temp = new_attributes[ATTR_COLOR_TEMP_KELVIN]
        if abs(current_color_temp - last_color_temp) > COLOR_TEMP_CHANGE:
            _LOGGER.debug(
                "Color temperature of '%s' significantly changed from %s to %s with"
                " context.id='%s'",
                light,
                last_color_temp,
                current_color_temp,
                context.id,
            )
            return True

    if (
        adapt_color
        and ATTR_RGB_COLOR in old_attributes
        and ATTR_RGB_COLOR in new_attributes
    ):
        last_rgb_color = old_attributes[ATTR_RGB_COLOR]
        current_rgb_color = new_attributes[ATTR_RGB_COLOR]
        redmean_change = color_difference_redmean(last_rgb_color, current_rgb_color)
        if redmean_change > RGB_REDMEAN_CHANGE:
            _LOGGER.debug(
                "color RGB of '%s' significantly changed from %s to %s with"
                " context.id='%s'",
                light,
                last_rgb_color,
                current_rgb_color,
                context.id,
            )
            return True
    return False


class AdaptiveSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Adaptive Lighting switch."""

    def __init__(
        self,
        hass,
        config_entry: ConfigEntry,
        manager: AdaptiveLightingManager,
        sleep_mode_switch: SimpleSwitch,
        adapt_color_switch: SimpleSwitch,
        adapt_brightness_switch: SimpleSwitch,
    ) -> None:
        """Initialize the Adaptive Lighting switch."""
        # Set attributes that can't be modified during runtime
        assert hass is not None
        self.hass = hass
        self.manager = manager
        self.sleep_mode_switch = sleep_mode_switch
        self.adapt_color_switch = adapt_color_switch
        self.adapt_brightness_switch = adapt_brightness_switch

        data = validate(config_entry)

        self._name = data[CONF_NAME]
        self._interval: timedelta = data[CONF_INTERVAL]
        self.lights: list[str] = data[CONF_LIGHTS]

        # backup data for use in change_switch_settings "configuration" CONF_USE_DEFAULTS
        self._config_backup = deepcopy(data)
        self._set_changeable_settings(data=data, defaults=None)

        # Set other attributes
        self._icon = ICON_MAIN
        self._state: bool | None = None

        # To count the number of `Context` instances
        self._context_cnt: int = 0

        # Set in self._update_attrs_and_maybe_adapt_lights
        self._settings: dict[str, Any] = {}

        # Set and unset tracker in async_turn_on and async_turn_off
        self.remove_listeners: list[CALLBACK_TYPE] = []
        self.remove_interval: CALLBACK_TYPE = lambda: None
        _LOGGER.debug(
            "%s: Setting up with '%s',"
            " config_entry.data: '%s',"
            " config_entry.options: '%s', converted to '%s'.",
            self._name,
            self.lights,
            config_entry.data,
            config_entry.options,
            data,
        )

    def _set_changeable_settings(
        self,
        data: dict[str, Any],
        defaults: dict[str, Any] | None = None,
    ):
        # Only pass settings users can change during runtime
        data = validate(
            config_entry=None,
            service_data=data,
            defaults=defaults,
        )

        # backup data for use in change_switch_settings "current" CONF_USE_DEFAULTS
        self._current_settings = data

        self._detect_non_ha_changes = data[CONF_DETECT_NON_HA_CHANGES]
        self._include_config_in_attributes = data[CONF_INCLUDE_CONFIG_IN_ATTRIBUTES]
        self._config: dict[str, Any] = {}
        if self._include_config_in_attributes:
            attrdata = deepcopy(data)
            for k, v in attrdata.items():
                if isinstance(v, datetime.date | datetime.datetime):
                    attrdata[k] = v.isoformat()
                elif isinstance(v, datetime.timedelta):
                    attrdata[k] = v.total_seconds()
            self._config.update(attrdata)

        self.initial_transition = data[CONF_INITIAL_TRANSITION]
        self._sleep_transition = data[CONF_SLEEP_TRANSITION]
        self._only_once = data[CONF_ONLY_ONCE]
        self._prefer_rgb_color = data[CONF_PREFER_RGB_COLOR]
        self._separate_turn_on_commands = data[CONF_SEPARATE_TURN_ON_COMMANDS]
        self._transition = data[CONF_TRANSITION]
        self._adapt_delay = data[CONF_ADAPT_DELAY]
        self._send_split_delay = data[CONF_SEND_SPLIT_DELAY]
        self._take_over_control = data[CONF_TAKE_OVER_CONTROL]
        if not data[CONF_TAKE_OVER_CONTROL] and (
            data[CONF_DETECT_NON_HA_CHANGES] or data[CONF_ADAPT_ONLY_ON_BARE_TURN_ON]
        ):
            _LOGGER.warning(
                "%s: Config mismatch: `detect_non_ha_changes` or `adapt_only_on_bare_turn_on` "
                "set to `true` requires `take_over_control` to be enabled. Adjusting config "
                "and continuing setup with `take_over_control: true`.",
                self._name,
            )
            self._take_over_control = True
        self._detect_non_ha_changes = data[CONF_DETECT_NON_HA_CHANGES]
        self._adapt_only_on_bare_turn_on = data[CONF_ADAPT_ONLY_ON_BARE_TURN_ON]
        self._auto_reset_manual_control_time = data[CONF_AUTORESET_CONTROL]
        self._skip_redundant_commands = data[CONF_SKIP_REDUNDANT_COMMANDS]
        self._intercept = data[CONF_INTERCEPT]
        self._multi_light_intercept = data[CONF_MULTI_LIGHT_INTERCEPT]
        if not data[CONF_INTERCEPT] and data[CONF_MULTI_LIGHT_INTERCEPT]:
            _LOGGER.warning(
                "%s: Config mismatch: `multi_light_intercept` set to `true` requires `intercept`"
                " to be enabled. Adjusting config and continuing setup with"
                " `multi_light_intercept: false`.",
                self._name,
            )
            self._multi_light_intercept = False
        self._expand_light_groups()  # updates manual control timers
        location, _ = get_astral_location(self.hass)

        self._sun_light_settings = SunLightSettings(
            name=self._name,
            astral_location=location,
            adapt_until_sleep=data[CONF_ADAPT_UNTIL_SLEEP],
            max_brightness=data[CONF_MAX_BRIGHTNESS],
            max_color_temp=data[CONF_MAX_COLOR_TEMP],
            min_brightness=data[CONF_MIN_BRIGHTNESS],
            min_color_temp=data[CONF_MIN_COLOR_TEMP],
            sleep_brightness=data[CONF_SLEEP_BRIGHTNESS],
            sleep_color_temp=data[CONF_SLEEP_COLOR_TEMP],
            sleep_rgb_color=data[CONF_SLEEP_RGB_COLOR],
            sleep_rgb_or_color_temp=data[CONF_SLEEP_RGB_OR_COLOR_TEMP],
            sunrise_offset=data[CONF_SUNRISE_OFFSET],
            sunrise_time=data[CONF_SUNRISE_TIME],
            min_sunrise_time=data[CONF_MIN_SUNRISE_TIME],
            max_sunrise_time=data[CONF_MAX_SUNRISE_TIME],
            sunset_offset=data[CONF_SUNSET_OFFSET],
            sunset_time=data[CONF_SUNSET_TIME],
            min_sunset_time=data[CONF_MIN_SUNSET_TIME],
            max_sunset_time=data[CONF_MAX_SUNSET_TIME],
            brightness_mode=data[CONF_BRIGHTNESS_MODE],
            brightness_mode_time_dark=data[CONF_BRIGHTNESS_MODE_TIME_DARK],
            brightness_mode_time_light=data[CONF_BRIGHTNESS_MODE_TIME_LIGHT],
            timezone=zoneinfo.ZoneInfo(self.hass.config.time_zone),
        )
        _LOGGER.debug(
            "%s: Set switch settings for lights '%s'. now using data: '%s'",
            self._name,
            self.lights,
            data,
        )

    @property
    def name(self):
        """Return the name of the device if any."""
        return f"Adaptive Lighting: {self._name}"

    @property
    def unique_id(self):
        """Return the unique ID of entity."""
        return self._name

    @property
    def is_on(self) -> bool | None:
        """Return true if adaptive lighting is on."""
        return self._state

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        if self.hass.is_running:
            await self._setup_listeners()
        else:
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                self._setup_listeners,
            )
        last_state: State | None = await self.async_get_last_state()
        is_new_entry = last_state is None  # newly added to HA
        if is_new_entry or last_state.state == STATE_ON:  # type: ignore[union-attr]
            await self.async_turn_on(adapt_lights=not self._only_once)
        else:
            self._state = False
            assert not self.remove_listeners

    async def async_will_remove_from_hass(self):
        """Remove the listeners upon removing the component."""
        self._remove_listeners()

    def _expand_light_groups(self) -> None:
        all_lights = _expand_light_groups(self.hass, self.lights)
        self.manager.lights.update(all_lights)
        self.manager.set_auto_reset_manual_control_times(
            all_lights,
            self._auto_reset_manual_control_time,
        )
        self.lights = list(all_lights)

    async def _setup_listeners(self, _=None) -> None:
        _LOGGER.debug("%s: Called '_setup_listeners'", self._name)
        if not self.is_on or not self.hass.is_running:
            _LOGGER.debug("%s: Cancelled '_setup_listeners'", self._name)
            return

        while not all(
            sw._state is not None
            for sw in [
                self.sleep_mode_switch,
                self.adapt_brightness_switch,
                self.adapt_color_switch,
            ]
        ):
            # Waits until `async_added_to_hass` is done, which in SimpleSwitch
            # is when `_state` is set to `True` or `False`.
            # Fixes first issue in https://github.com/basnijholt/adaptive-lighting/issues/682
            _LOGGER.debug(
                "%s: Waiting for simple switches to be initialized",
                self._name,
            )
            await asyncio.sleep(0.1)

        assert not self.remove_listeners

        self._update_time_interval_listener()

        remove_sleep = async_track_state_change_event(
            self.hass,
            entity_ids=self.sleep_mode_switch.entity_id,
            action=self._sleep_mode_switch_state_event_action,
        )

        self.remove_listeners.append(remove_sleep)
        self._expand_light_groups()

    def _update_time_interval_listener(self) -> None:
        """Create or recreate the adaptation interval listener.

        Recreation is necessary when the configuration has changed (e.g., `send_split_delay`).
        """
        self._remove_interval_listener()

        # An adaptation takes a little longer than its nominal duration due processing overhead,
        # so we factor this in to avoid overlapping adaptations. Since this is a constant value,
        # it might not cover all cases, but if large enough, it covers most.
        # Ideally, the interval and adaptation are a coupled process where a finished adaptation
        # triggers the next, but that requires a larger architectural change.
        processing_overhead_time = 0.5

        adaptation_interval = (
            self._interval
            + timedelta(milliseconds=self._send_split_delay)
            + timedelta(seconds=processing_overhead_time)
        )

        self.remove_interval = async_track_time_interval(
            self.hass,
            action=self._async_update_at_interval_action,
            interval=adaptation_interval,
        )

    def _call_on_remove_callbacks(self) -> None:
        """Call callbacks registered by async_on_remove."""
        # This is called when the integration is removed from HA
        # and in `Entity.add_to_platform_abort`.
        # For some unknown reason (to me) `async_will_remove_from_hass`
        # is not called in `add_to_platform_abort`.
        # See https://github.com/basnijholt/adaptive-lighting/issues/658
        self._remove_listeners()
        try:
            # HACK: this is a private method in `Entity` which can change
            super()._call_on_remove_callbacks()
        except AttributeError as err:
            _LOGGER.error(
                "%s: Caught AttributeError in `_call_on_remove_callbacks`: %s",
                self._name,
                err,
            )

    def _remove_interval_listener(self) -> None:
        self.remove_interval()
        self.remove_interval = lambda: None

    def _remove_listeners(self) -> None:
        self._remove_interval_listener()

        while self.remove_listeners:
            remove_listener = self.remove_listeners.pop()
            remove_listener()

    @property
    def icon(self) -> str:
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the attributes of the switch."""
        extra_state_attributes: dict[str, Any] = {"configuration": self._config}
        if not self.is_on:
            for key in self._settings:
                extra_state_attributes[key] = None
            return extra_state_attributes
        extra_state_attributes["manual_control"] = [
            light for light in self.lights if self.manager.manual_control.get(light)
        ]
        extra_state_attributes.update(self._settings)
        timers = self.manager.auto_reset_manual_control_timers
        extra_state_attributes["autoreset_time_remaining"] = {
            light: time
            for light in self.lights
            if (timer := timers.get(light)) and (time := timer.remaining_time()) > 0
        }
        return extra_state_attributes

    def create_context(
        self,
        which: str = "default",
        parent: Context | None = None,
    ) -> Context:
        """Create a context that identifies this Adaptive Lighting instance."""
        context = create_context(self._name, which, self._context_cnt, parent=parent)
        self._context_cnt += 1
        return context

    async def async_turn_on(  # type: ignore[override]
        self,
        adapt_lights: bool = True,
    ) -> None:
        """Turn on adaptive lighting."""
        _LOGGER.debug(
            "%s: Called 'async_turn_on', current state is '%s'",
            self._name,
            self._state,
        )
        if self.is_on:
            return
        self._state = True
        self.manager.reset(*self.lights)
        await self._setup_listeners()
        if adapt_lights:
            await self._update_attrs_and_maybe_adapt_lights(
                context=self.create_context("turn_on"),
                transition=self.initial_transition,
                force=True,
            )

    async def async_turn_off(self, **kwargs) -> None:  # noqa: ARG002
        """Turn off adaptive lighting."""
        if not self.is_on:
            return
        self._state = False
        self._remove_listeners()
        self.manager.reset(*self.lights)

    async def _async_update_at_interval_action(self, now=None) -> None:  # noqa: ARG002
        """Update the attributes and maybe adapt the lights."""
        await self._update_attrs_and_maybe_adapt_lights(
            context=self.create_context("interval"),
            transition=self._transition,
            force=False,
        )

    async def prepare_adaptation_data(
        self,
        light: str,
        transition: int | None = None,
        adapt_brightness: bool | None = None,
        adapt_color: bool | None = None,
        prefer_rgb_color: bool | None = None,
        force: bool = False,
        context: Context | None = None,
    ) -> AdaptationData | None:
        """Prepare `AdaptationData` for adapting a light."""
        if transition is None:
            transition = self._transition
        if adapt_brightness is None:
            adapt_brightness = self.adapt_brightness_switch.is_on
        if adapt_color is None:
            adapt_color = self.adapt_color_switch.is_on
        if prefer_rgb_color is None:
            prefer_rgb_color = self._prefer_rgb_color

        if not adapt_color and not adapt_brightness:
            _LOGGER.debug(
                "%s: Skipping adaptation of %s because both adapt_brightness and"
                " adapt_color are False",
                self._name,
                light,
            )
            return None

        # The switch might be off and not have _settings set.
        self._settings = self._sun_light_settings.get_settings(
            self.sleep_mode_switch.is_on,
            transition,
        )

        # Build service data.
        service_data: dict[str, Any] = {ATTR_ENTITY_ID: light}
        features = _supported_features(self.hass, light)

        # Check transition == 0 to fix #378
        use_transition = "transition" in features and transition > 0
        if use_transition:
            service_data[ATTR_TRANSITION] = transition

        if "brightness" in features and adapt_brightness:
            brightness = round(255 * self._settings["brightness_pct"] / 100)
            service_data[ATTR_BRIGHTNESS] = brightness

        sleep_rgb = (
            self.sleep_mode_switch.is_on
            and self._sun_light_settings.sleep_rgb_or_color_temp == "rgb_color"
        )
        if (
            "color_temp" in features
            and adapt_color
            and not (prefer_rgb_color and "color" in features)
            and not (sleep_rgb and "color" in features)
            and not (self._settings["force_rgb_color"] and "color" in features)
        ):
            _LOGGER.debug("%s: Setting color_temp of light %s", self._name, light)
            state = self.hass.states.get(light)
            assert isinstance(state, State)
            attributes = state.attributes
            min_kelvin = attributes["min_color_temp_kelvin"]
            max_kelvin = attributes["max_color_temp_kelvin"]
            color_temp_kelvin = self._settings["color_temp_kelvin"]
            color_temp_kelvin = clamp(color_temp_kelvin, min_kelvin, max_kelvin)
            service_data[ATTR_COLOR_TEMP_KELVIN] = color_temp_kelvin
        elif "color" in features and adapt_color:
            _LOGGER.debug("%s: Setting rgb_color of light %s", self._name, light)
            service_data[ATTR_RGB_COLOR] = self._settings["rgb_color"]

        required_attrs = [ATTR_RGB_COLOR, ATTR_COLOR_TEMP_KELVIN, ATTR_BRIGHTNESS]
        if not any(attr in service_data for attr in required_attrs):
            _LOGGER.debug(
                "%s: Skipping adaptation of %s because no relevant attributes"
                " are set in service_data: %s",
                self._name,
                light,
                service_data,
            )
            return None

        context = context or self.create_context("adapt_lights")

        return prepare_adaptation_data(
            self.hass,
            light,
            context,
            transition if use_transition else 0,
            self._send_split_delay / 1000.0,
            service_data,
            split=self._separate_turn_on_commands,
            filter_by_state=self._skip_redundant_commands,
            force=force,
        )

    async def _adapt_light(
        self,
        light: str,
        context: Context,
        transition: int | None = None,
        adapt_brightness: bool | None = None,
        adapt_color: bool | None = None,
        prefer_rgb_color: bool | None = None,
        force: bool = False,
    ) -> None:
        if (lock := self.manager.turn_off_locks.get(light)) and lock.locked():
            _LOGGER.debug("%s: '%s' is locked", self._name, light)
            return

        data = await self.prepare_adaptation_data(
            light,
            transition,
            adapt_brightness,
            adapt_color,
            prefer_rgb_color,
            force,
            context,
        )
        if data is None:
            return  # nothing to adapt

        await self.execute_cancellable_adaptation_calls(data)

    async def _execute_adaptation_calls(self, data: AdaptationData):
        """Executes a sequence of adaptation service calls for the given service datas."""
        for index in range(data.max_length):
            is_first_call = index == 0

            # Sleep between multiple service calls.
            if not is_first_call or data.initial_sleep:
                await asyncio.sleep(data.sleep_time)

            # Instead of directly iterating the generator in the while-loop, we get
            # the next item here after the sleep to make sure it incorporates state
            # changes which happened during the sleep.
            service_data = await data.next_service_call_data()

            if not service_data:
                # All service datas processed
                break

            if (
                not data.force
                and not is_on(self.hass, data.entity_id)
                # if proactively adapting, we are sure that it came from a `light.turn_on`
                and not self.manager.is_proactively_adapting(data.context.id)
            ):
                # Do a last-minute check if the entity is still on.
                _LOGGER.debug(
                    "%s: Skipping adaptation of %s because it is now off",
                    self._name,
                    data.entity_id,
                )
                return

            _LOGGER.debug(
                "%s: Scheduling 'light.turn_on' with the following 'service_data': %s"
                " with context.id='%s'",
                self._name,
                service_data,
                data.context.id,
            )
            light = service_data[ATTR_ENTITY_ID]
            self.manager.last_service_data[light] = service_data
            await self.hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_ON,
                service_data,
                context=data.context,
            )

    async def execute_cancellable_adaptation_calls(
        self,
        data: AdaptationData,
    ):
        """Executes a cancellable sequence of adaptation service calls for the given service datas.

        Wraps the sequence of service calls in a task that can be cancelled from elsewhere, e.g.,
        to cancel an ongoing adaptation when a light is turned off.
        """
        # Prevent overlap of multiple adaptation sequences
        self.manager.cancel_ongoing_adaptation_calls(data.entity_id, which=data.which)
        _LOGGER.debug(
            "%s: execute_cancellable_adaptation_calls with data: %s",
            self._name,
            data,
        )
        # Execute adaptation calls within a task
        try:
            task = asyncio.ensure_future(self._execute_adaptation_calls(data))
            if data.which in ("both", "brightness"):
                self.manager.adaptation_tasks_brightness[data.entity_id] = task
            if data.which in ("both", "color"):
                self.manager.adaptation_tasks_color[data.entity_id] = task
            await task
        except asyncio.CancelledError:
            _LOGGER.debug(
                "%s: Ongoing adaptation of %s cancelled, with AdaptationData: %s",
                self._name,
                data.entity_id,
                data,
            )

    async def _update_attrs_and_maybe_adapt_lights(  # noqa: PLR0912
        self,
        *,
        context: Context,
        lights: list[str] | None = None,
        transition: int | None = None,
        force: bool = False,
    ) -> None:
        assert context is not None
        _LOGGER.debug(
            "%s: '_update_attrs_and_maybe_adapt_lights' called with context.id='%s'"
            " lights: '%s', transition: '%s', force: '%s'",
            self._name,
            context.id,
            lights,
            transition,
            force,
        )
        assert self.is_on
        self._settings.update(
            self._sun_light_settings.get_settings(
                self.sleep_mode_switch.is_on,
                transition,
            ),
        )
        self.async_write_ha_state()

        if not force and self._only_once:
            return

        if lights is None:
            lights = self.lights

        on_lights = [light for light in lights if is_on(self.hass, light)]

        if force:
            filtered_lights = on_lights
        else:
            filtered_lights = []
            for light in on_lights:
                # Don't adapt lights that haven't finished prior transitions.
                timer = self.manager.transition_timers.get(light)
                if timer is not None and timer.is_running():
                    _LOGGER.debug(
                        "%s: Light '%s' is still transitioning, context.id='%s'",
                        self._name,
                        light,
                        context.id,
                    )
                elif (
                    # This is to prevent lights immediately turning on after
                    # being turned off in 'interval' update, see #726
                    not self._detect_non_ha_changes
                    and is_our_context(context, "interval")
                    and (turn_on := self.manager.turn_on_event.get(light))
                    and (turn_off := self.manager.turn_off_event.get(light))
                    and turn_off.time_fired > turn_on.time_fired
                ):
                    _LOGGER.debug(
                        "%s: Light '%s' was turned just turned off, context.id='%s'",
                        self._name,
                        light,
                        context.id,
                    )
                else:
                    filtered_lights.append(light)

        _LOGGER.debug("%s: filtered_lights: '%s'", self._name, filtered_lights)
        if not filtered_lights:
            return

        adapt_brightness = self.adapt_brightness_switch.is_on
        adapt_color = self.adapt_color_switch.is_on
        assert isinstance(adapt_brightness, bool)
        assert isinstance(adapt_color, bool)
        tasks = []
        for light in filtered_lights:
            manually_controlled = (
                self._take_over_control
                and self.manager.is_manually_controlled(
                    self,
                    light,
                    force,
                    adapt_brightness,
                    adapt_color,
                )
            )
            if manually_controlled:
                _LOGGER.debug(
                    "%s: '%s' is being manually controlled, stop adapting, context.id=%s.",
                    self._name,
                    light,
                    context.id,
                )
                continue

            significant_change = (
                self._take_over_control
                and self._detect_non_ha_changes
                and not force
                # Note: This call updates the state of the light
                # so it might suddenly be off.
                and await self.manager.significant_change(
                    self,
                    light,
                    adapt_brightness,
                    adapt_color,
                    context,
                )
            )
            if significant_change:
                _fire_manual_control_event(self, light, context)
                continue

            _LOGGER.debug(
                "%s: Calling _adapt_light from _update_attrs_and_maybe_adapt_lights:"
                " '%s' with transition %s and context.id=%s",
                self._name,
                light,
                transition,
                context.id,
            )
            coro = self._adapt_light(light, context, transition, force=force)
            task = self.hass.async_create_task(
                coro,
            )
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks)

    async def _respond_to_off_to_on_event(self, entity_id: str, event: Event) -> None:
        assert not self.manager.is_proactively_adapting(event.context.id)
        from_turn_on = self.manager._off_to_on_state_event_is_from_turn_on(
            entity_id,
            event,
        )
        if (
            self._take_over_control
            and not self._detect_non_ha_changes
            and not from_turn_on
        ):
            # There is an edge case where 2 switches control the same light, e.g.,
            # one for brightness and one for color. Now we will mark both switches
            # as manually controlled, which is not 100% correct.
            _LOGGER.debug(
                "%s: Ignoring 'off' → 'on' event for '%s' with context.id='%s'"
                " because 'light.turn_on' was not called by HA and"
                " 'detect_non_ha_changes' is False",
                self._name,
                entity_id,
                event.context.id,
            )
            self.manager.mark_as_manual_control(entity_id)
            return

        if (
            self._take_over_control
            and self._adapt_only_on_bare_turn_on
            and from_turn_on
            # adaptive_lighting.apply can turn on light, so check this is not our context
            and not is_our_context(event.context)
        ):
            service_data = self.manager.turn_on_event[entity_id].data[ATTR_SERVICE_DATA]
            if self.manager._mark_manual_control_if_non_bare_turn_on(
                entity_id,
                service_data,
            ):
                _LOGGER.debug(
                    "Skipping responding to 'off' → 'on' event for '%s' with context.id='%s' because"
                    " we only adapt on bare `light.turn_on` events and not on service_data: '%s'",
                    entity_id,
                    event.context.id,
                    service_data,
                )
                return

        if self._adapt_delay > 0:
            await asyncio.sleep(self._adapt_delay)

        await self._update_attrs_and_maybe_adapt_lights(
            context=self.create_context("light_event", parent=event.context),
            lights=[entity_id],
            transition=self.initial_transition,
            force=True,
        )

    async def _sleep_mode_switch_state_event_action(self, event: Event) -> None:
        if not _is_state_event(event, (STATE_ON, STATE_OFF)):
            _LOGGER.debug("%s: Ignoring sleep event %s", self._name, event)
            return
        _LOGGER.debug(
            "%s: _sleep_mode_switch_state_event_action, event: '%s'",
            self._name,
            event,
        )
        # Reset the manually controlled status when the "sleep mode" changes
        self.manager.reset(*self.lights)
        await self._update_attrs_and_maybe_adapt_lights(
            context=self.create_context("sleep", parent=event.context),
            transition=self._sleep_transition,
            force=True,
        )


class SimpleSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Adaptive Lighting switch."""

    def __init__(
        self,
        which: str,
        initial_state: bool,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        icon: str,
    ) -> None:
        """Initialize the Adaptive Lighting switch."""
        self.hass = hass
        data = validate(config_entry)
        self._icon = icon
        self._state: bool | None = None
        self._which = which
        name = data[CONF_NAME]
        self._unique_id = f"{name}_{slugify(self._which)}"
        self._name = f"Adaptive Lighting {which}: {name}"
        self._initial_state = initial_state

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of entity."""
        return self._unique_id

    @property
    def icon(self) -> str:
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def is_on(self) -> bool | None:
        """Return true if adaptive lighting is on."""
        return self._state

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        last_state = await self.async_get_last_state()
        _LOGGER.debug("%s: last state is %s", self._name, last_state)
        if (last_state is None and self._initial_state) or (
            last_state is not None and last_state.state == STATE_ON
        ):
            await self.async_turn_on()
        else:
            await self.async_turn_off()

    async def async_turn_on(self, **kwargs) -> None:  # noqa: ARG002
        """Turn on adaptive lighting sleep mode."""
        _LOGGER.debug("%s: Turning on", self._name)
        self._state = True

    async def async_turn_off(self, **kwargs) -> None:  # noqa: ARG002
        """Turn off adaptive lighting sleep mode."""
        _LOGGER.debug("%s: Turning off", self._name)
        self._state = False


class AdaptiveLightingManager:
    """Track 'light.turn_off' and 'light.turn_on' service calls."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the AdaptiveLightingManager that is shared among all switches."""
        assert hass is not None
        self.hass = hass
        self.lights: set[str] = set()

        # Tracks 'light.turn_off' service calls
        self.turn_off_event: dict[str, Event] = {}
        # Tracks 'light.turn_on' service calls
        self.turn_on_event: dict[str, Event] = {}
        # Tracks 'light.toggle' service calls
        self.toggle_event: dict[str, Event] = {}
        # Tracks 'on' → 'off' state changes
        self.on_to_off_event: dict[str, Event] = {}
        # Tracks 'off' → 'on' state changes
        self.off_to_on_event: dict[str, Event] = {}
        # Keep 'asyncio.sleep' tasks that can be cancelled by 'light.turn_on' events
        self.sleep_tasks: dict[str, asyncio.Task] = {}
        # Locks that prevent light adjusting when waiting for a light to 'turn_off'
        self.turn_off_locks: dict[str, asyncio.Lock] = {}
        # Tracks which lights are manually controlled
        self.manual_control: dict[str, bool] = {}
        # Track 'state_changed' events of self.lights resulting from this integration
        self.our_last_state_on_change: dict[str, list[State]] = {}
        # Track last 'service_data' to 'light.turn_on' resulting from this integration
        self.last_service_data: dict[str, dict[str, Any]] = {}
        # Track ongoing split adaptations to be able to cancel them
        self.adaptation_tasks_brightness: dict[str, asyncio.Task] = {}
        self.adaptation_tasks_color: dict[str, asyncio.Task] = {}

        # Track auto reset of manual_control
        self.auto_reset_manual_control_timers: dict[str, _AsyncSingleShotTimer] = {}
        self.auto_reset_manual_control_times: dict[str, float] = {}

        # Track light transitions
        self.transition_timers: dict[str, _AsyncSingleShotTimer] = {}

        # Track _execute_cancellable_adaptation_calls tasks
        self.adaptation_tasks = set()

        # Setup listeners and its callbacks to remove them later
        self.listener_removers = [
            self.hass.bus.async_listen(
                EVENT_CALL_SERVICE,
                self.turn_on_off_event_listener,
            ),
            self.hass.bus.async_listen(
                EVENT_STATE_CHANGED,
                self.state_changed_event_listener,
            ),
        ]

        self._proactively_adapting_contexts: dict[str, str] = {}

        try:
            self.listener_removers.append(
                setup_service_call_interceptor(
                    hass,
                    LIGHT_DOMAIN,
                    SERVICE_TURN_ON,
                    self._service_interceptor_turn_on_handler,
                ),
            )

            self.listener_removers.append(
                setup_service_call_interceptor(
                    hass,
                    LIGHT_DOMAIN,
                    SERVICE_TOGGLE,
                    self._service_interceptor_turn_on_handler,
                ),
            )
        except RuntimeError:
            _LOGGER.warning(
                "Failed to set up service call interceptors, "
                "falling back to event-reactive mode",
                exc_info=True,
            )

    def disable(self):
        """Disable the listener by removing all subscribed handlers."""
        for remove in self.listener_removers:
            remove()

    def set_proactively_adapting(self, context_id: str, entity_id: str) -> None:
        """Declare the adaptation with context_id as proactively adapting,
        and associate it to an entity_id.
        """  # noqa: D205
        self._proactively_adapting_contexts[context_id] = entity_id

    def is_proactively_adapting(self, context_id: str) -> bool:
        """Determine whether an adaptation with the given context_id is proactive."""
        is_proactively_adapting_context = (
            context_id in self._proactively_adapting_contexts
        )

        _LOGGER.debug(
            "is_proactively_adapting_context='%s', context_id='%s'",
            is_proactively_adapting_context,
            context_id,
        )

        return is_proactively_adapting_context

    def clear_proactively_adapting(self, entity_id: str) -> None:
        """Clear all context IDs associated with the given entity ID.

        Call this method to clear past context IDs and avoid a memory leak.
        """
        # First get the keys to avoid modifying the dict while iterating it
        keys = [
            k for k, v in self._proactively_adapting_contexts.items() if v == entity_id
        ]
        for key in keys:
            self._proactively_adapting_contexts.pop(key)

    def _separate_entity_ids(
        self,
        entity_ids: list[str],
        data,
    ) -> tuple[list[str], list[str]]:
        # Create a mapping from switch to entity IDs
        # AdaptiveSwitch.name → entity_ids mapping
        switch_to_eids: dict[str, list[str]] = {}
        # AdaptiveSwitch.name → AdaptiveSwitch mapping
        switch_name_mapping: dict[str, AdaptiveSwitch] = {}
        # Note: In HA≥2023.5, AdaptiveSwitch is hashable, so we can
        # use dict[AdaptiveSwitch, list[str]]
        skipped: list[str] = []
        for entity_id in entity_ids:
            try:
                switch = _switch_with_lights(
                    self.hass,
                    [entity_id],
                    # Do not expand light groups, because HA will make a separate light.turn_on
                    # call where the lights are expanded, and that call will be intercepted.
                    expand_light_groups=False,
                )
            except NoSwitchFoundError:
                # Needs to make the original call but without adaptation
                skipped.append(entity_id)
                _LOGGER.debug(
                    "No switch found for entity_id='%s', skipped='%s'",
                    entity_id,
                    skipped,
                )
            else:
                if (
                    not switch.is_on
                    or not switch._intercept
                    # Never adapt on light groups, because HA will make a separate light.turn_on
                    or _is_light_group(self.hass.states.get(entity_id))
                    # Prevent adaptation of TURN_ON calls when light is already on,
                    # and of TOGGLE calls when toggling off.
                    or self.hass.states.is_state(entity_id, STATE_ON)
                    or self.manual_control.get(entity_id, False)
                    or (
                        switch._take_over_control
                        and switch._adapt_only_on_bare_turn_on
                        and self._mark_manual_control_if_non_bare_turn_on(
                            entity_id,
                            data[CONF_PARAMS],
                        )
                    )
                ):
                    _LOGGER.debug(
                        "Switch is off or light is already on for entity_id='%s', skipped='%s'"
                        " (is_on='%s', is_state='%s', manual_control='%s', switch._intercept='%s')",
                        entity_id,
                        skipped,
                        switch.is_on,
                        self.hass.states.is_state(entity_id, STATE_ON),
                        self.manual_control.get(entity_id, False),
                        switch._intercept,
                    )
                    skipped.append(entity_id)
                else:
                    switch_to_eids.setdefault(switch.name, []).append(entity_id)
                    switch_name_mapping[switch.name] = switch
        return switch_to_eids, switch_name_mapping, skipped

    def _correct_for_multi_light_intercept(
        self,
        entity_ids,
        switch_to_eids,
        switch_name_mapping,
        skipped,
    ):
        # Check for `multi_light_intercept: true/false`
        mli = [sw._multi_light_intercept for sw in switch_name_mapping.values()]
        more_than_one_switch = len(switch_to_eids) > 1
        single_switch_with_multiple_lights = (
            len(switch_to_eids) == 1 and len(next(iter(switch_to_eids.values()))) > 1
        )
        switch_without_multi_light_intercept = not all(mli)
        if more_than_one_switch and switch_without_multi_light_intercept:
            _LOGGER.warning(
                "Multiple switches (%s) targeted, but not all have"
                " `multi_light_intercept: true`, so skipping intercept"
                " for all lights.",
                switch_to_eids,
            )
            skipped = entity_ids
            switch_to_eids = {}
        elif (
            single_switch_with_multiple_lights and switch_without_multi_light_intercept
        ):
            _LOGGER.warning(
                "Single switch with multiple lights targeted, but"
                " `multi_light_intercept: true` is not set, so skipping intercept"
                " for all lights.",
                switch_to_eids,
            )
            skipped = entity_ids
            switch_to_eids = {}
        return switch_to_eids, switch_name_mapping, skipped

    async def _service_interceptor_turn_on_handler(
        self,
        call: ServiceCall,
        service_data: ServiceData,
    ) -> None:
        """Intercept `light.turn_on` and `light.toggle` service calls and adapt them.

        It is possible that the calls are made for multiple lights at once,
        which in turn might be in different switches or no switches at all.
        If there are lights that are not all in a single switch, we need to
        make multiple calls to `light.turn_on` with the correct entity IDs.
        One of these calls can be intercepted and adapted, the others need to
        be adapted by calling `_adapt_light` with the correct entity IDs or
        by calling `light.turn_on` directly.

        We create a mapping from switch to entity IDs and keep a list
        of skipped lights which are lights in no switches or in switches that
        are off or lights that are already on.

        If there is only one switch and 0 skipped lights, we just intercept the
        call directly.

        If there are multiple switches and skipped lights, we can adapt the call
        for one of the switches to include only the lights in that switch and
        need to call `_adapt_light` for the other switches with their
        entity_ids. For skipped lights, we call light.turn_on directly with the
        entity_ids and original service data.

        If there are only skipped lights, we can use the intercepted call
        directly.
        """
        is_skipped_hash = is_our_context(call.context, "skipped")
        _LOGGER.debug(
            "(0) _service_interceptor_turn_on_handler: call.context.id='%s', is_skipped_hash='%s'",
            call.context.id,
            is_skipped_hash,
        )
        if is_our_context(call.context) and not is_skipped_hash:
            # Don't adapt our own service calls, but do re-adapt calls that
            # were skipped by us
            return

        if (
            ATTR_EFFECT in service_data[CONF_PARAMS]
            or ATTR_FLASH in service_data[CONF_PARAMS]
        ):
            return

        _LOGGER.debug(
            "(1) _service_interceptor_turn_on_handler: call='%s', service_data='%s'",
            call,
            service_data,
        )

        # Because `_service_interceptor_turn_on_single_light_handler` modifies the
        # original service data, we need to make a copy of it to use in the `skipped` call
        service_data_copy = deepcopy(service_data)

        entity_ids = self._get_entity_list(service_data)
        # Note: we do not expand light groups anywhere in this method, instead
        # we skip them and rely on the followup call that HA will make
        # with the expanded entity IDs.

        switch_to_eids, switch_name_mapping, skipped = self._separate_entity_ids(
            entity_ids,
            service_data,
        )

        (
            switch_to_eids,
            switch_name_mapping,
            skipped,
        ) = self._correct_for_multi_light_intercept(
            entity_ids,
            switch_to_eids,
            switch_name_mapping,
            skipped,
        )
        _LOGGER.debug(
            "(2) _service_interceptor_turn_on_handler: switch_to_eids='%s', skipped='%s'",
            switch_to_eids,
            skipped,
        )

        def modify_service_data(service_data, entity_ids):
            """Modify the service data to contain the entity IDs."""
            service_data.pop(ATTR_ENTITY_ID, None)
            service_data.pop(ATTR_AREA_ID, None)
            service_data[ATTR_ENTITY_ID] = entity_ids
            return service_data

        # Intercept the call for first switch and call _adapt_light for the rest
        has_intercepted = False  # Can only intercept a turn_on call once
        for adaptive_switch_name, _entity_ids in switch_to_eids.items():
            switch = switch_name_mapping[adaptive_switch_name]
            transition = service_data[CONF_PARAMS].get(
                ATTR_TRANSITION,
                switch.initial_transition,
            )
            if not has_intercepted:
                _LOGGER.debug(
                    "(3) _service_interceptor_turn_on_handler: intercepting entity_ids='%s'",
                    _entity_ids,
                )
                await self._service_interceptor_turn_on_single_light_handler(
                    entity_ids=_entity_ids,
                    switch=switch,
                    transition=transition,
                    call=call,
                    data=modify_service_data(service_data, _entity_ids),
                )
                has_intercepted = True
                continue

            for eid in _entity_ids:
                # Must add a new context otherwise _adapt_light will bail out
                context = switch.create_context("intercept")
                self.clear_proactively_adapting(eid)
                self.set_proactively_adapting(context.id, eid)
                _LOGGER.debug(
                    "(4) _service_interceptor_turn_on_handler: calling `_adapt_light` with eid='%s', context='%s', transition='%s'",
                    eid,
                    context,
                    transition,
                )
                await switch._adapt_light(
                    light=eid,
                    context=context,
                    transition=transition,
                )

        # Call light.turn_on service for skipped entities
        if skipped:
            if not has_intercepted:
                assert set(skipped) == set(entity_ids)
                return  # The call will be intercepted with the original data
            # Call light turn_on service for skipped entities
            context = switch.create_context("skipped")
            _LOGGER.debug(
                "(5) _service_interceptor_turn_on_handler: calling `light.turn_on` with skipped='%s', service_data: '%s', context='%s'",
                skipped,
                service_data_copy,  # This is the original service data
                context.id,
            )
            service_data = {ATTR_ENTITY_ID: skipped, **service_data_copy[CONF_PARAMS]}
            if (
                ATTR_COLOR_TEMP in service_data
                and ATTR_COLOR_TEMP_KELVIN in service_data
            ):
                # ATTR_COLOR_TEMP and ATTR_COLOR_TEMP_KELVIN are mutually exclusive
                del service_data[ATTR_COLOR_TEMP]
            await self.hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_ON,
                service_data,
                blocking=True,
                context=context,
            )

    async def _service_interceptor_turn_on_single_light_handler(
        self,
        entity_ids: list[str],
        switch: AdaptiveSwitch,
        transition: int,
        call: ServiceCall,
        data: ServiceData,
    ):
        _LOGGER.debug(
            "Intercepted TURN_ON call with data %s (%s)",
            data,
            call.context.id,
        )

        # Reset because turning on the light, this also happens in
        # `state_changed_event_listener`, however, this function is called
        # before that one.
        self.reset(*entity_ids, reset_manual_control=False)
        for entity_id in entity_ids:
            self.clear_proactively_adapting(entity_id)

        adaptation_data = await switch.prepare_adaptation_data(
            entity_id,
            transition,
        )
        if adaptation_data is None:
            return

        # Take first adaptation item to apply it to this service call
        first_service_data = await adaptation_data.next_service_call_data()

        if not first_service_data:
            return

        # Update/adapt service call data
        first_service_data.pop(ATTR_ENTITY_ID, None)
        # This is called as a preprocessing step by the schema validation of the original
        # service call and needs to be repeated here to also process the added adaptation data.
        # (A more generic alternative would be re-executing the validation, but that is more
        # complicated and unstable because it requires transformation of the data object back
        # into its original service call structure which cannot be reliably done due to the
        # lack of a bijective mapping.)
        preprocess_turn_on_alternatives(self.hass, first_service_data)
        data[CONF_PARAMS].update(first_service_data)

        # Schedule additional service calls for the remaining adaptation data.
        # We cannot know here whether there is another call to follow (since the
        # state can change until the next call), so we just schedule it and let
        # it sort out by itself.
        for entity_id in entity_ids:
            self.set_proactively_adapting(call.context.id, entity_id)
            self.set_proactively_adapting(adaptation_data.context.id, entity_id)
        adaptation_data.initial_sleep = True

        # Don't await to avoid blocking the service call.
        # Assign to a variable only to await in tests.
        self.adaptation_tasks.add(
            asyncio.create_task(
                switch.execute_cancellable_adaptation_calls(adaptation_data),
            ),
        )
        # Remove tasks that are done
        if done_tasks := [t for t in self.adaptation_tasks if t.done()]:
            self.adaptation_tasks.difference_update(done_tasks)

    def _handle_timer(
        self,
        light: str,
        timers_dict: dict[str, _AsyncSingleShotTimer],
        delay: float | None,
        reset_coroutine: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        timer = timers_dict.get(light)
        if timer is not None:
            if delay is None:  # Timer object exists, but should not anymore
                timer.cancel()
                timers_dict.pop(light)
            else:  # Timer object already exists, just update the delay and restart it
                timer.delay = delay
                timer.start()
        elif delay is not None:  # Timer object does not exist, create it
            timer = _AsyncSingleShotTimer(delay, reset_coroutine)
            timers_dict[light] = timer
            timer.start()

    def start_transition_timer(self, light: str) -> None:
        """Mark a light as manually controlled."""
        last_service_data = self.last_service_data.get(light)
        if last_service_data is None:
            _LOGGER.debug(
                "No last service data for light %s, not starting timer.",
                light,
            )
            return

        last_transition = last_service_data.get(ATTR_TRANSITION)
        if not last_transition:
            _LOGGER.debug(
                "No transition in last adapt for light %s, not starting timer.",
                light,
            )
            return

        _LOGGER.debug(
            "Start transition timer of %s seconds for light %s",
            last_transition,
            light,
        )

        async def reset():
            # Called when the timer expires, doesn't need to do anything
            _LOGGER.debug(
                "Transition finished for light %s",
                light,
            )

        self._handle_timer(light, self.transition_timers, last_transition, reset)

    def set_auto_reset_manual_control_times(self, lights: list[str], time: float):
        """Set the time after which the lights are automatically reset."""
        if time == 0:
            return
        for light in lights:
            old_time = self.auto_reset_manual_control_times.get(light)
            if (old_time is not None) and (old_time != time):
                _LOGGER.info(
                    "Setting auto_reset_manual_control for '%s' from %s seconds to %s seconds."
                    " This might happen because the light is in multiple swiches"
                    " or because of a config change.",
                    light,
                    old_time,
                    time,
                )
            self.auto_reset_manual_control_times[light] = time

    def mark_as_manual_control(self, light: str) -> None:
        """Mark a light as manually controlled."""
        _LOGGER.debug("Marking '%s' as manually controlled.", light)
        self.manual_control[light] = True
        delay = self.auto_reset_manual_control_times.get(light)

        async def reset():
            _LOGGER.debug(
                "Auto resetting 'manual_control' status of '%s' because"
                " it was not manually controlled for %s seconds.",
                light,
                delay,
            )
            self.reset(light)
            switches = _switches_with_lights(self.hass, [light])
            for switch in switches:
                if not switch.is_on:
                    continue
                await switch._update_attrs_and_maybe_adapt_lights(
                    context=switch.create_context("autoreset"),
                    lights=[light],
                    transition=switch.initial_transition,
                    force=True,
                )
            assert not self.manual_control[light]

        self._handle_timer(light, self.auto_reset_manual_control_timers, delay, reset)

    def cancel_ongoing_adaptation_calls(
        self,
        light_id: str,
        which: Literal["color", "brightness", "both"] = "both",
    ):
        """Cancel ongoing adaptation service calls for a specific light entity."""
        brightness_task = self.adaptation_tasks_brightness.get(light_id)
        color_task = self.adaptation_tasks_color.get(light_id)
        if (
            which in ("both", "brightness")
            and brightness_task is not None
            and not brightness_task.done()
        ):
            _LOGGER.debug(
                "Cancelled ongoing brightness adaptation calls (%s) for '%s'",
                brightness_task,
                light_id,
            )
            brightness_task.cancel()
        if (
            which in ("both", "color")
            and color_task is not None
            and color_task is not brightness_task
            and not color_task.done()
        ):
            _LOGGER.debug(
                "Cancelled ongoing color adaptation calls (%s) for '%s'",
                color_task,
                light_id,
            )
            # color_task might be the same as brightness_task
            color_task.cancel()

    def reset(self, *lights, reset_manual_control: bool = True) -> None:
        """Reset the 'manual_control' status of the lights."""
        for light in lights:
            if reset_manual_control:
                self.manual_control[light] = False
                if timer := self.auto_reset_manual_control_timers.pop(light, None):
                    timer.cancel()
            self.our_last_state_on_change.pop(light, None)
            self.last_service_data.pop(light, None)
            self.cancel_ongoing_adaptation_calls(light)

    def _get_entity_list(self, service_data: ServiceData) -> list[str]:
        if ATTR_ENTITY_ID in service_data:
            return cv.ensure_list_csv(service_data[ATTR_ENTITY_ID])
        if ATTR_AREA_ID in service_data:
            entity_ids = []
            area_ids = cv.ensure_list_csv(service_data[ATTR_AREA_ID])
            for area_id in area_ids:
                area_entity_ids = area_entities(self.hass, area_id)
                eids = [
                    entity_id
                    for entity_id in area_entity_ids
                    if entity_id.startswith(LIGHT_DOMAIN)
                ]
                entity_ids.extend(eids)
                _LOGGER.debug(
                    "Found entity_ids '%s' for area_id '%s'",
                    entity_ids,
                    area_id,
                )
            return entity_ids
        _LOGGER.debug(
            "No entity_ids or area_ids found in service_data: %s",
            service_data,
        )
        return []

    async def turn_on_off_event_listener(self, event: Event) -> None:
        """Track 'light.turn_off' and 'light.turn_on' service calls."""
        domain = event.data.get(ATTR_DOMAIN)
        if domain != LIGHT_DOMAIN:
            return

        service = event.data[ATTR_SERVICE]
        service_data = event.data[ATTR_SERVICE_DATA]
        entity_ids = self._get_entity_list(service_data)

        if not any(eid in self.lights for eid in entity_ids):
            return

        def off(eid: str, event: Event):
            self.turn_off_event[eid] = event
            self.reset(eid)

        def on(eid: str, event: Event):
            task = self.sleep_tasks.get(eid)
            if task is not None:
                task.cancel()
            self.turn_on_event[eid] = event
            timer = self.auto_reset_manual_control_timers.get(eid)
            if (
                timer is not None
                and timer.is_running()
                and event.time_fired > timer.start_time  # type: ignore[operator]
            ):
                # Restart the auto reset timer
                timer.start()

        if service == SERVICE_TURN_OFF:
            transition = service_data.get(ATTR_TRANSITION)
            _LOGGER.debug(
                "Detected an 'light.turn_off('%s', transition=%s)' event with context.id='%s'",
                entity_ids,
                transition,
                event.context.id,
            )
            for eid in entity_ids:
                off(eid, event)

        elif service == SERVICE_TURN_ON:
            _LOGGER.debug(
                "Detected an 'light.turn_on('%s')' event with context.id='%s'",
                entity_ids,
                event.context.id,
            )
            for eid in entity_ids:
                on(eid, event)

        elif service == SERVICE_TOGGLE:
            _LOGGER.debug(
                "Detected an 'light.toggle('%s')' event with context.id='%s'",
                entity_ids,
                event.context.id,
            )
            for eid in entity_ids:
                state = self.hass.states.get(eid).state
                self.toggle_event[eid] = event
                if state == STATE_ON:  # is turning off
                    off(eid, event)
                elif state == STATE_OFF:  # is turning on
                    on(eid, event)

    async def state_changed_event_listener(self, event: Event) -> None:
        """Track 'state_changed' events."""
        entity_id = event.data.get(ATTR_ENTITY_ID, "")
        if entity_id not in self.lights:
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        new_on = new_state is not None and new_state.state == STATE_ON
        new_off = new_state is not None and new_state.state == STATE_OFF
        old_on = old_state is not None and old_state.state == STATE_ON
        old_off = old_state is not None and old_state.state == STATE_OFF

        if new_on:
            _LOGGER.debug(
                "Detected a '%s' 'state_changed' event: '%s' with context.id='%s'",
                entity_id,
                new_state.attributes,
                new_state.context.id,
            )
            # It is possible to have multiple state change events with the same context.
            # This can happen because a `turn_on.light(brightness_pct=100, transition=30)`
            # event leads to an instant state change of
            # `new_state=dict(brightness=100, ...)`. However, after polling the light
            # could still only be `new_state=dict(brightness=50, ...)`.
            # We save all events because the first event change might indicate at what
            # settings the light will be later *or* the second event might indicate a
            # final state. The latter case happens for example when a light was
            # called with a color_temp outside of its range (and HA reports the
            # incorrect 'min_kelvin' and 'max_kelvin', which happens e.g., for
            # Philips Hue White GU10 Bluetooth lights).
            last_state: list[State] | None = self.our_last_state_on_change.get(
                entity_id,
            )
            if is_our_context(new_state.context):
                if (
                    last_state is not None
                    and last_state[0].context.id == new_state.context.id
                ):
                    _LOGGER.debug(
                        "AdaptiveLightingManager: State change event of '%s' is already"
                        " in 'self.our_last_state_on_change' (%s)"
                        " adding this state also",
                        entity_id,
                        new_state.context.id,
                    )
                    self.our_last_state_on_change[entity_id].append(new_state)
                else:
                    _LOGGER.debug(
                        "AdaptiveLightingManager: New adapt '%s' found for %s",
                        new_state,
                        entity_id,
                    )
                    self.our_last_state_on_change[entity_id] = [new_state]
                    self.start_transition_timer(entity_id)
            elif last_state is not None:
                self.our_last_state_on_change[entity_id].append(new_state)

        if old_on and new_off:
            # Tracks 'on' → 'off' state changes
            self.on_to_off_event[entity_id] = event
            self.reset(entity_id)
            _LOGGER.debug(
                "Detected an 'on' → 'off' event for '%s' with context.id='%s'",
                entity_id,
                event.context.id,
            )
        elif old_off and new_on:
            # Tracks 'off' → 'on' state changes
            self.off_to_on_event[entity_id] = event
            _LOGGER.debug(
                "Detected an 'off' → 'on' event for '%s' with context.id='%s'",
                entity_id,
                event.context.id,
            )

            if self.is_proactively_adapting(event.context.id):
                _LOGGER.debug(
                    "Skipping responding to 'off' → 'on' event for '%s' with context.id='%s' because"
                    " we are already proactively adapting",
                    entity_id,
                    event.context.id,
                )
                # Note: the reset below already happened in `_service_interceptor_turn_on_handler`
                return

            self.reset(entity_id, reset_manual_control=False)
            lock = self.turn_off_locks.setdefault(entity_id, asyncio.Lock())
            async with lock:
                if await self.just_turned_off(entity_id):
                    # Stop if a rapid 'off' → 'on' → 'off' happens.
                    _LOGGER.debug(
                        "Cancelling adjusting lights for %s",
                        entity_id,
                    )
                    return

            switches = _switches_with_lights(self.hass, [entity_id])
            for switch in switches:
                if switch.is_on:
                    await switch._respond_to_off_to_on_event(
                        entity_id,
                        event,
                    )

    def is_manually_controlled(
        self,
        switch: AdaptiveSwitch,
        light: str,
        force: bool,
        adapt_brightness: bool,
        adapt_color: bool,
    ) -> bool:
        """Check if the light has been 'on' and is now manually controlled."""
        manual_control = self.manual_control.setdefault(light, False)
        if manual_control:
            # Manually controlled until light is turned on and off
            return True

        turn_on_event = self.turn_on_event.get(light)
        if (
            turn_on_event is not None
            and not self.is_proactively_adapting(turn_on_event.context.id)
            and not is_our_context(turn_on_event.context)
            and not force
        ):
            keys = turn_on_event.data[ATTR_SERVICE_DATA].keys()
            if (
                (adapt_color and COLOR_ATTRS.intersection(keys))
                or (adapt_brightness and BRIGHTNESS_ATTRS.intersection(keys))
                or (ATTR_FLASH in keys)
                or (ATTR_EFFECT in keys)
            ):
                # Light was already on and 'light.turn_on' was not called by
                # the adaptive_lighting integration.
                manual_control = True
                _fire_manual_control_event(switch, light, turn_on_event.context)
                _LOGGER.debug(
                    "'%s' was already on and 'light.turn_on' was not called by the"
                    " adaptive_lighting integration (context.id='%s'), the Adaptive"
                    " Lighting will stop adapting the light until the switch or the"
                    " light turns off and then on again.",
                    light,
                    turn_on_event.context.id,
                )
        return manual_control

    async def significant_change(
        self,
        switch: AdaptiveSwitch,
        light: str,
        adapt_brightness: bool,
        adapt_color: bool,
        context: Context,  # just for logging
    ) -> bool:
        """Has the light made a significant change since last update.

        This method will detect changes that were made to the light without
        calling 'light.turn_on', so outside of Home Assistant. If a change is
        detected, we mark the light as 'manually controlled' until the light
        or switch is turned 'off' and 'on' again.
        """
        assert switch._detect_non_ha_changes

        last_service_data = self.last_service_data.get(light)
        if last_service_data is None:
            return False
        # Update state and check for a manual change not done in HA.
        # Ensure HASS is correctly updating your light's state with
        # light.turn_on calls if any problems arise. This
        # can happen e.g. using zigbee2mqtt with 'report: false' in device settings.
        await self.hass.helpers.entity_component.async_update_entity(light)
        refreshed_state = self.hass.states.get(light)
        assert refreshed_state is not None

        changed = _attributes_have_changed(
            old_attributes=last_service_data,
            new_attributes=refreshed_state.attributes,
            light=light,
            adapt_brightness=adapt_brightness,
            adapt_color=adapt_color,
            context=context,
        )
        if changed:
            _LOGGER.debug(
                "%s: State attributes of '%s' changed (%s) wrt 'last_service_data' (%s) (context.id=%s)",
                switch._name,
                light,
                refreshed_state.attributes,
                last_service_data,
                context.id,
            )
            return True
        _LOGGER.debug(
            "%s: State attributes of '%s' did not change (%s) wrt 'last_service_data' (%s) (context.id=%s)",
            switch._name,
            light,
            refreshed_state.attributes,
            last_service_data,
            context.id,
        )
        return False

    def _off_to_on_state_event_is_from_turn_on(
        self,
        entity_id: str,
        off_to_on_event: Event,
    ) -> bool:
        # Adaptive Lighting should never turn on lights itself
        if is_our_context(off_to_on_event.context) and not is_our_context(
            off_to_on_event.context,
            "service",  # adaptive_lighting.apply is allowed to turn on lights
        ):
            _LOGGER.warning(
                "Detected an 'off' → 'on' event for '%s' with context.id='%s' and"
                " event='%s', triggered by the adaptive_lighting integration itself,"
                " which *should* not happen. If you see this please submit an issue with"
                " your full logs at https://github.com/basnijholt/adaptive-lighting",
                entity_id,
                off_to_on_event.context.id,
                off_to_on_event,
            )
        turn_on_event: Event | None = self.turn_on_event.get(entity_id)
        id_off_to_on = off_to_on_event.context.id
        return (
            turn_on_event is not None
            and id_off_to_on is not None
            and id_off_to_on == turn_on_event.context.id
        )

    async def just_turned_off(  # noqa: PLR0911, PLR0912
        self,
        entity_id: str,
    ) -> bool:
        """Cancel the adjusting of a light if it has just been turned off.

        Possibly the lights just got a 'turn_off' call, however, the light
        is actually still turning off (e.g., because of a 'transition') and
        HA polls the light before the light is 100% off. This might trigger
        a rapid switch 'off' → 'on' → 'off'. To prevent this component
        from interfering on the 'on' state, we make sure to wait at least
        TURNING_OFF_DELAY (or the 'turn_off' transition time) between a
        'off' → 'on' event and then check whether the light is still 'on' or
        if the brightness is still decreasing. Only if it is the case we
        adjust the lights.
        """
        off_to_on_event = self.off_to_on_event[entity_id]
        on_to_off_event = self.on_to_off_event.get(entity_id)

        if on_to_off_event is None:
            _LOGGER.debug(
                "just_turned_off: No 'on' → 'off' state change has been registered before for '%s'."
                " It's possible that the light was already on when Home Assistant was turned on.",
                entity_id,
            )
            return False

        if off_to_on_event.context.id == on_to_off_event.context.id:
            _LOGGER.debug(
                "just_turned_off: 'on' → 'off' state change has the same context.id as the"
                " 'off' → 'on' state change for '%s'. This is probably a false positive.",
                entity_id,
            )
            return True

        id_on_to_off = on_to_off_event.context.id

        turn_off_event = self.turn_off_event.get(entity_id)
        if turn_off_event is not None:
            transition = turn_off_event.data[ATTR_SERVICE_DATA].get(ATTR_TRANSITION)
        else:
            transition = None

        if self._off_to_on_state_event_is_from_turn_on(entity_id, off_to_on_event):
            is_toggle = off_to_on_event == self.toggle_event.get(entity_id)
            from_service = "light.toggle" if is_toggle else "light.turn_on"
            _LOGGER.debug(
                "just_turned_off: State change 'off' → 'on' triggered by '%s'",
                from_service,
            )
            return False

        if (
            turn_off_event is not None
            and id_on_to_off == turn_off_event.context.id
            and id_on_to_off is not None
            and transition is not None  # 'turn_off' is called with transition=...
        ):
            # State change 'on' → 'off' and 'light.turn_off(..., transition=...)' come
            # from the same event, so wait at least the 'turn_off' transition time.
            delay = max(transition, TURNING_OFF_DELAY)
        else:
            # State change 'off' → 'on' happened because the light state was set.
            # Possibly because of polling.
            delay = TURNING_OFF_DELAY

        delta_time = (dt_util.utcnow() - on_to_off_event.time_fired).total_seconds()
        if delta_time > delay:
            _LOGGER.debug(
                "just_turned_off: delta_time='%s' > delay='%s'",
                delta_time,
                delay,
            )
            return False

        # Here we could just `return True` but because we want to prevent any updates
        # from happening to this light (through async_track_time_interval or
        # sleep_state) for some time, we wait below until the light
        # is 'off' or the time has passed.

        delay -= delta_time  # delta_time has passed since the 'off' → 'on' event
        _LOGGER.debug(
            "just_turned_off: Waiting with adjusting '%s' for %s",
            entity_id,
            delay,
        )
        total_sleep = 0
        for _ in range(3):
            # It can happen that the actual transition time is longer than the
            # specified time in the 'turn_off' service.
            coro = asyncio.sleep(delay)
            total_sleep += delay
            task = self.sleep_tasks[entity_id] = asyncio.ensure_future(coro)
            try:
                await task
            except asyncio.CancelledError:  # 'light.turn_on' has been called
                _LOGGER.debug(
                    "just_turned_off: Sleep task is cancelled due to 'light.turn_on('%s')' call",
                    entity_id,
                )
                return False

            if not is_on(self.hass, entity_id):
                _LOGGER.debug(
                    "just_turned_off: '%s' is off after %s seconds, cancelling adaptation",
                    entity_id,
                    total_sleep,
                )
                return True
            delay = TURNING_OFF_DELAY  # next time only wait this long

        if transition is not None:
            # Always ignore when there's a 'turn_off' transition.
            # Because it seems like HA cannot detect whether a light is
            # transitioning into 'off'. Maybe needs some discussion/input?
            return True

        # Now we assume that the lights are still on and they were intended
        # to be on.
        _LOGGER.debug(
            "just_turned_off: '%s' is still on after %s seconds, assuming it was intended to be on",
            entity_id,
            total_sleep,
        )
        return False

    def _mark_manual_control_if_non_bare_turn_on(
        self,
        entity_id: str,
        service_data: ServiceData,
    ) -> bool:
        _LOGGER.debug(
            "_mark_manual_control_if_non_bare_turn_on: entity_id='%s', service_data='%s'",
            entity_id,
            service_data,
        )
        if any(attr in service_data for attr in COLOR_ATTRS | BRIGHTNESS_ATTRS):
            self.mark_as_manual_control(entity_id)
            return True
        return False


class _AsyncSingleShotTimer:
    def __init__(self, delay, callback) -> None:
        """Initialize the timer."""
        self.delay = delay
        self.callback = callback
        self.task = None
        self.start_time: datetime.datetime | None = None

    async def _run(self):
        """Run the timer. Don't call this directly, use start() instead."""
        self.start_time = dt_util.utcnow()
        await asyncio.sleep(self.delay)
        if self.callback:
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback()
            else:
                self.callback()

    def is_running(self):
        """Return whether the timer is running."""
        return self.task is not None and not self.task.done()

    def start(self):
        """Start the timer."""
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.task = asyncio.create_task(self._run())

    def cancel(self):
        """Cancel the timer."""
        if self.task:
            self.task.cancel()
            self.callback = None

    def remaining_time(self):
        """Return the remaining time before the timer expires."""
        if self.start_time is not None:
            elapsed_time = (dt_util.utcnow() - self.start_time).total_seconds()
            return max(0, self.delay - elapsed_time)
        return 0
