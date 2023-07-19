"""Tests for Adaptive Lighting switches."""
# pylint: disable=protected-access
import asyncio
from copy import deepcopy
import datetime
import itertools
import logging
from random import randint
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_MAX_COLOR_TEMP_KELVIN,
    ATTR_MIN_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    COLOR_MODE_BRIGHTNESS,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.light import SERVICE_TURN_OFF
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
import homeassistant.config as config_util
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    CONF_LIGHTS,
    CONF_NAME,
    EVENT_CALL_SERVICE,
    EVENT_STATE_CHANGED,
    SERVICE_TOGGLE,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context, Event, HomeAssistant, State
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.setup import async_setup_component
from homeassistant.util.color import color_temperature_mired_to_kelvin
import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_area_registry,
)
import ulid_transform
import voluptuous.error

from custom_components.adaptive_lighting.adaptation_utils import (
    AdaptationData,
    _create_service_call_data_iterator,
)
from custom_components.adaptive_lighting.const import (
    ADAPT_BRIGHTNESS_SWITCH,
    ADAPT_COLOR_SWITCH,
    ATTR_TURN_ON_OFF_LISTENER,
    CONF_AUTORESET_CONTROL,
    CONF_DETECT_NON_HA_CHANGES,
    CONF_INITIAL_TRANSITION,
    CONF_MANUAL_CONTROL,
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_PREFER_RGB_COLOR,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    CONF_TRANSITION,
    CONF_TURN_ON_LIGHTS,
    CONF_USE_DEFAULTS,
    CONST_COLOR,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_NAME,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_COLOR_TEMP,
    DOMAIN,
    SERVICE_APPLY,
    SERVICE_CHANGE_SWITCH_SETTINGS,
    SERVICE_SET_MANUAL_CONTROL,
    SLEEP_MODE_SWITCH,
    UNDO_UPDATE_LISTENER,
)
from custom_components.adaptive_lighting.switch import (
    _SUPPORT_OPTS,
    INTERNAL_CONF_PROACTIVE_SERVICE_CALL_ADAPTATION,
    VALID_COLOR_MODES,
    AdaptiveSwitch,
    _attributes_have_changed,
    _supported_features,
    color_difference_redmean,
    create_context,
    is_our_context,
    is_our_context_id,
)

_LOGGER = logging.getLogger(__name__)

SUNRISE = datetime.datetime(
    year=2020,
    month=10,
    day=17,
    hour=6,
)
SUNSET = datetime.datetime(
    year=2020,
    month=10,
    day=17,
    hour=22,
)

LAT_LONG_TZS = [
    (39, -1, "Europe/Madrid"),
    (60, 50, "GMT"),
    (55, 13, "Europe/Copenhagen"),
    (52.379189, 4.899431, "Europe/Amsterdam"),
    (32.87336, -117.22743, "US/Pacific"),
]

ENTITY_LIGHT = "light.bed_light"
ENTITY_LIGHT3 = "light.kitchen_lights"
_SWITCH_FMT = f"{SWITCH_DOMAIN}.{DOMAIN}"
ENTITY_SWITCH = f"{_SWITCH_FMT}_{DEFAULT_NAME}"
ENTITY_SLEEP_MODE_SWITCH = f"{_SWITCH_FMT}_sleep_mode_{DEFAULT_NAME}"
ENTITY_ADAPT_BRIGHTNESS_SWITCH = f"{_SWITCH_FMT}_adapt_brightness_{DEFAULT_NAME}"
ENTITY_ADAPT_COLOR_SWITCH = f"{_SWITCH_FMT}_adapt_color_{DEFAULT_NAME}"

ORIG_TIMEZONE = dt_util.DEFAULT_TIME_ZONE

GLOBAL_TEST_DEPENDENCIES = [
    "test_adaptive_lighting_switches",
    "test_light_settings",
]


def create_random_context() -> str:
    return Context(id=ulid_transform.ulid_now(), parent_id=None)


@pytest.fixture
def reset_time_zone():
    """Reset time zone."""
    yield
    dt_util.DEFAULT_TIME_ZONE = ORIG_TIMEZONE


async def setup_switch(hass, extra_data) -> tuple[MockConfigEntry, AdaptiveSwitch]:
    """Create the switch entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: DEFAULT_NAME,
            INTERNAL_CONF_PROACTIVE_SERVICE_CALL_ADAPTATION: False,
            **extra_data,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    switch = hass.data[DOMAIN][entry.entry_id][SWITCH_DOMAIN]
    return entry, switch


async def setup_lights(hass: HomeAssistant):
    """Set up 3 light entities using the 'template' platform."""
    await async_setup_component(
        hass,
        LIGHT_DOMAIN,
        {
            LIGHT_DOMAIN: [
                {
                    "platform": "template",
                    "lights": {
                        "bed_light": {
                            "friendly_name": "Bed Light",
                            "unique_id": "light_1",
                            "turn_on": None,
                            "turn_off": None,
                            "set_level": None,
                            "set_temperature": None,
                            "set_color": None,
                        },
                        "ceiling_lights": {
                            "friendly_name": "Ceiling Lights",
                            "unique_id": "light_2",
                            "turn_on": None,
                            "turn_off": None,
                            "set_level": None,
                            "set_temperature": None,
                            "set_color": None,
                        },
                        "kitchen_lights": {
                            "friendly_name": "Kitchen Lights",
                            "unique_id": "light_3",
                            "turn_on": None,
                            "turn_off": None,
                            "set_level": None,
                            "set_temperature": None,
                            "set_color": None,
                            "supports_transition_template": True,
                        },
                    },
                },
            ]
        },
    )

    await hass.async_block_till_done()
    platform = async_get_platforms(hass, "template")
    lights = list(platform[0].entities.values())

    await lights[0].async_turn_on()
    await lights[1].async_turn_on()

    for light in lights:
        light._attr_brightness = 255
        light._attr_color_temp = 250

    assert all(hass.states.get(light.entity_id) is not None for light in lights)
    return lights


async def setup_lights_and_switch(hass, extra_conf=None, all_lights: bool = False):
    """Create switch and demo lights."""
    # Setup demo lights and turn on
    lights_instances = await setup_lights(hass)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_LIGHT},
        blocking=True,
    )

    # Setup switch
    lights = [
        ENTITY_LIGHT,
        "light.ceiling_lights",
    ]

    if all_lights:
        lights.append(ENTITY_LIGHT3)

    assert all(hass.states.get(light) is not None for light in lights)
    _, switch = await setup_switch(
        hass,
        {
            CONF_LIGHTS: lights,
            CONF_SUNRISE_TIME: datetime.time(SUNRISE.hour),
            CONF_SUNSET_TIME: datetime.time(SUNSET.hour),
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_DETECT_NON_HA_CHANGES: True,
            CONF_PREFER_RGB_COLOR: False,
            CONF_MIN_COLOR_TEMP: 2500,  # to not coincide with sleep_color_temp
            **(extra_conf or {}),
        },
    )
    await hass.async_block_till_done()
    return switch, lights_instances


# see https://github.com/home-assistant/core/blob/dev/homeassistant/scripts/benchmark/__init__.py
# basically just search the repo for EVENT_STATE_CHANGED look for how it's fired.
def create_transition_events(
    light: str,
    state: State,
    last: dict | None = None,
    current: dict | None = None,
    total_events: int = 4,
) -> list[dict]:
    assert light is not None
    all_events = []
    for i in range(1, total_events):
        # Build basic event data.
        attributes = {}

        # The first state change always has the context from our integration.
        # That one will not be in all_events.
        # It's very possible it stores the parent_id though.
        # If it stores the parent_id in all situations, there's a great improvement
        # that could added in future updates.

        # Simulate the events the bulb would send to HASS.
        last_brightness = last.get(ATTR_BRIGHTNESS) or state[ATTR_BRIGHTNESS]
        current_brightness = current.get(ATTR_BRIGHTNESS)
        if (
            last_brightness
            and current_brightness
            and last_brightness != current_brightness
        ):
            diff = (current_brightness - last_brightness) * (i / total_events)
            attributes[ATTR_BRIGHTNESS] = last_brightness + diff
        elif current_brightness:
            attributes[ATTR_BRIGHTNESS] = current_brightness
        current_kelvin = current.get(ATTR_COLOR_TEMP_KELVIN)
        last_kelvin = last.get(ATTR_COLOR_TEMP_KELVIN) or state[ATTR_COLOR_TEMP_KELVIN]
        if last_kelvin and current_kelvin and last_kelvin != current_kelvin:
            diff = (current_kelvin - last_kelvin) * (i / total_events)
            attributes[ATTR_COLOR_TEMP_KELVIN] = last_kelvin + diff
        elif current_kelvin:
            attributes[ATTR_COLOR_TEMP_KELVIN] = current_kelvin

        # Pack event
        event_data = {
            ATTR_ENTITY_ID: light,
            "old_state": State(light, "on", attributes=last),
            "new_state": State(
                light, "on", attributes=attributes, context=create_random_context()
            ),
        }
        all_events.append(event_data)
    return all_events


async def test_adaptive_lighting_switches(hass):
    """Test switches created for adaptive_lighting integration."""
    entry, _ = await setup_switch(hass, {})

    assert len(hass.states.async_entity_ids(SWITCH_DOMAIN)) == 4
    assert set(hass.states.async_entity_ids(SWITCH_DOMAIN)) == {
        ENTITY_SWITCH,
        ENTITY_SLEEP_MODE_SWITCH,
        ENTITY_ADAPT_COLOR_SWITCH,
        ENTITY_ADAPT_BRIGHTNESS_SWITCH,
    }
    assert ATTR_TURN_ON_OFF_LISTENER in hass.data[DOMAIN]
    assert entry.entry_id in hass.data[DOMAIN]
    assert len(hass.data[DOMAIN].keys()) == 2

    data = hass.data[DOMAIN][entry.entry_id]
    assert SLEEP_MODE_SWITCH in data
    assert SWITCH_DOMAIN in data
    assert ADAPT_COLOR_SWITCH in data
    assert ADAPT_BRIGHTNESS_SWITCH in data
    assert UNDO_UPDATE_LISTENER in data
    assert "instance" in data

    assert len(data.keys()) == 6


@pytest.mark.parametrize("lat,long,timezone", LAT_LONG_TZS)
@pytest.mark.dependency("test_adaptive_lighting_switches")
async def test_adaptive_lighting_time_zones_with_default_settings(
    hass, lat, long, timezone, reset_time_zone  # pylint: disable=redefined-outer-name
):
    """Test setting up the Adaptive Lighting switches with different timezones."""
    await config_util.async_process_ha_core_config(
        hass,
        {"latitude": lat, "longitude": long, "time_zone": timezone},
    )
    _, switch = await setup_switch(hass, {})
    # Shouldn't raise an exception ever
    await switch._update_attrs_and_maybe_adapt_lights(
        context=switch.create_context("test")
    )


@pytest.mark.parametrize("lat,long,timezone", LAT_LONG_TZS)
async def test_adaptive_lighting_time_zones_and_sun_settings(
    hass, lat, long, timezone, reset_time_zone  # pylint: disable=redefined-outer-name
):
    """Test setting up the Adaptive Lighting switches with different timezones.

    Also test the (sleep) brightness and color temperature settings.
    """
    await config_util.async_process_ha_core_config(
        hass,
        {"latitude": lat, "longitude": long, "time_zone": timezone},
    )
    _, switch = await setup_switch(
        hass,
        {
            CONF_SUNRISE_TIME: datetime.time(SUNRISE.hour),
            CONF_SUNSET_TIME: datetime.time(SUNSET.hour),
        },
    )

    context = switch.create_context("test")  # needs to be passed to update method
    min_color_temp = switch._sun_light_settings.min_color_temp

    sunset = SUNSET.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
    before_sunset = sunset - datetime.timedelta(hours=1)
    after_sunset = sunset + datetime.timedelta(hours=1)
    sunrise = SUNRISE.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
    before_sunrise = sunrise - datetime.timedelta(hours=1)
    after_sunrise = sunrise + datetime.timedelta(hours=1)

    async def patch_time_and_update(time):
        with patch("homeassistant.util.dt.utcnow", return_value=time):
            await switch._update_attrs_and_maybe_adapt_lights(context=context)
            await hass.async_block_till_done()

    # At sunset the brightness should be max and color_temp at the smallest value
    await patch_time_and_update(sunset)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == min_color_temp

    # One hour before sunset the brightness should be max and color_temp
    # not at the smallest value yet.
    await patch_time_and_update(before_sunset)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] > min_color_temp

    # One hour after sunset the brightness should be down
    await patch_time_and_update(after_sunset)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] < DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == min_color_temp

    # At sunrise the brightness should be max and color_temp at the smallest value
    await patch_time_and_update(sunrise)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == min_color_temp

    # One hour before sunrise the brightness should smaller than max
    # and color_temp at the min value.
    await patch_time_and_update(before_sunrise)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] < DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == min_color_temp

    # One hour after sunrise the brightness should be up
    await patch_time_and_update(after_sunrise)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] > min_color_temp

    # Turn on sleep mode which make the brightness and color_temp
    # deterministic regardless of the time
    await switch.sleep_mode_switch.async_turn_on()
    await switch._update_attrs_and_maybe_adapt_lights(context=context)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_SLEEP_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == DEFAULT_SLEEP_COLOR_TEMP


async def test_light_settings(hass):
    """Test that light settings are correctly applied."""
    switch, _ = await setup_lights_and_switch(hass)
    lights = switch.lights

    # Turn on "sleep mode"
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_SLEEP_MODE_SWITCH},
        blocking=True,
    )
    await hass.async_block_till_done()
    light_states = [hass.states.get(light) for light in lights]
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] == round(
            255 * switch._settings[ATTR_BRIGHTNESS_PCT] / 100
        )
        last_service_data = switch.turn_on_off_listener.last_service_data[
            state.entity_id
        ]
        assert state.attributes[ATTR_BRIGHTNESS] == last_service_data[ATTR_BRIGHTNESS]
        assert (
            state.attributes[ATTR_COLOR_TEMP_KELVIN]
            == last_service_data[ATTR_COLOR_TEMP_KELVIN]
        )

    # Turn off "sleep mode"
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_SLEEP_MODE_SWITCH},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Test with different times
    sunset = SUNSET.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
    before_sunset = sunset - datetime.timedelta(hours=1)
    after_sunset = sunset + datetime.timedelta(hours=1)
    sunrise = SUNRISE.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
    before_sunrise = sunrise - datetime.timedelta(hours=1)
    after_sunrise = sunrise + datetime.timedelta(hours=1)

    context = switch.create_context("test")  # needs to be passed to update method

    async def patch_time_and_get_updated_states(time):
        with patch("homeassistant.util.dt.utcnow", return_value=time):
            await switch._update_attrs_and_maybe_adapt_lights(
                transition=0, context=context, force=True
            )
            await hass.async_block_till_done()
            return [hass.states.get(light) for light in lights]

    def assert_expected_color_temp(state):
        last_service_data = switch.turn_on_off_listener.last_service_data[
            state.entity_id
        ]
        assert (
            state.attributes[ATTR_COLOR_TEMP_KELVIN]
            == last_service_data[ATTR_COLOR_TEMP_KELVIN]
        )

    # At sunset the brightness should be max and color_temp at the smallest value
    light_states = await patch_time_and_get_updated_states(sunset)
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] == 255
        assert_expected_color_temp(state)

    # One hour before sunset the brightness should be max and color_temp
    # not at the smallest value yet.
    light_states = await patch_time_and_get_updated_states(before_sunset)
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] == 255
        assert_expected_color_temp(state)

    # One hour after sunset the brightness should be down
    light_states = await patch_time_and_get_updated_states(after_sunset)
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] < 255
        assert_expected_color_temp(state)

    # At sunrise the brightness should be max and color_temp at the smallest value
    light_states = await patch_time_and_get_updated_states(sunrise)
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] == 255
        assert_expected_color_temp(state)

    # One hour before sunrise the brightness should smaller than max
    # and color_temp at the min value.
    light_states = await patch_time_and_get_updated_states(before_sunrise)
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] < 255
        assert_expected_color_temp(state)

    # One hour after sunrise the brightness should be up
    light_states = await patch_time_and_get_updated_states(after_sunrise)
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] == 255
        assert_expected_color_temp(state)


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_turn_on_off_listener_not_tracking_untracked_lights(hass):
    """Test that lights that are not in a Adaptive Lighting switch aren't tracked."""
    switch, _ = await setup_lights_and_switch(hass)
    light = "light.kitchen_lights"
    assert light not in switch.lights
    for state in [True, False]:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: light},
            blocking=True,
        )
        await switch._update_attrs_and_maybe_adapt_lights(
            context=switch.create_context("test")
        )
        await hass.async_block_till_done()
    assert light not in switch.turn_on_off_listener.lights


def test_supported_features(hass):  # noqa: C901
    """Test the supported features of a light."""

    possible_legacy_features = {}
    MAX_COMBINATIONS = 4  # maximum number of elements that can be combined
    for i in range(1, min(MAX_COMBINATIONS, len(_SUPPORT_OPTS)) + 1):
        for combination in itertools.combinations(_SUPPORT_OPTS.keys(), i):
            key = "_".join(combination)
            value = [v for k, v in _SUPPORT_OPTS.items() if k in combination]
            possible_legacy_features[key] = value

    possible_color_modes = {}
    for i in range(1, len(VALID_COLOR_MODES) + 1):
        for combination in itertools.combinations(VALID_COLOR_MODES.keys(), i):
            key = "_".join(combination)
            value = [v for k, v in VALID_COLOR_MODES.items() if k in combination]
            possible_color_modes[key] = value

    # create a mock HomeAssistant object
    hass = MagicMock()

    # iterate over possible legacy features
    for feature_key, feature_values in possible_legacy_features.items():
        # _LOGGER.debug(feature_values)
        # set the attributes of the mock state object to the possible legacy feature values
        state_attrs = {ATTR_SUPPORTED_FEATURES: sum(feature_values)}
        hass.states.get.return_value.attributes = state_attrs

        # iterate over possible color modes
        for mode_key, mode_values in possible_color_modes.items():
            # _LOGGER.debug(mode_values)
            # set the attributes of the mock state object to the possible color mode values
            state_attrs[ATTR_SUPPORTED_COLOR_MODES] = set(mode_values)
            hass.states.get.return_value.attributes = state_attrs

            # Handle both the new and the old _supported_features.
            result = _supported_features(hass, ENTITY_LIGHT)
            supported, supports_colors = (
                result if isinstance(result, tuple) else (result, None)
            )
            expected_supported = {} if supports_colors is not None else set()
            for mode, attr in VALID_COLOR_MODES.items():
                if mode in mode_values:
                    if supports_colors is None:
                        expected_supported.add(mode)
                    else:
                        expected_supported[attr] = True
                        if supports_colors is True:
                            expected_supported[COLOR_MODE_BRIGHTNESS] = True
            for opt, value in _SUPPORT_OPTS.items():
                if value in feature_values:
                    if supports_colors is None:
                        expected_supported.add(opt)
                    else:
                        if supports_colors is True:
                            expected_supported[COLOR_MODE_BRIGHTNESS] = True
                        if opt in VALID_COLOR_MODES:
                            expected_supported[VALID_COLOR_MODES[opt]] = True
                        elif opt != CONST_COLOR:
                            expected_supported[opt] = True
            if ATTR_MIN_COLOR_TEMP_KELVIN in supported:
                supported.pop(ATTR_MIN_COLOR_TEMP_KELVIN)
            if ATTR_MAX_COLOR_TEMP_KELVIN in supported:
                supported.pop(ATTR_MAX_COLOR_TEMP_KELVIN)
            assert supported == expected_supported, (
                f"\nExpected supported: {expected_supported}\n"
                f"Actual supported: {supported}\n"
                f"feature_values: {feature_values}\n"
                f"mode_values: {mode_values}\n"
                f"supports_colors: {supports_colors}\n"
            )


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_manual_control(hass):
    """Test the 'manual control' tracking."""
    switch, (light, *_) = await setup_lights_and_switch(hass)
    context = switch.create_context("test")  # needs to be passed to update method
    manual_control = switch.turn_on_off_listener.manual_control

    async def update():
        await switch._update_attrs_and_maybe_adapt_lights(transition=0, context=context)
        await hass.async_block_till_done()

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()
        await update()
        _LOGGER.debug("Turn light %s, to %s", state, kwargs)

    async def turn_switch(state, entity_id):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()

    async def change_manual_control(set_to, extra_service_data=None):
        if extra_service_data is None:
            extra_service_data = {CONF_LIGHTS: [ENTITY_LIGHT]}
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_MANUAL_CONTROL,
            {
                ATTR_ENTITY_ID: switch.entity_id,
                CONF_MANUAL_CONTROL: set_to,
                **extra_service_data,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        await update()

    def increased_brightness():
        return (light._attr_brightness + 100) % 255

    def increased_color_temp():
        return max(
            (light._attr_color_temp + 100) % light.max_color_temp_kelvin,
            light.min_color_temp_kelvin,
        )

    # Nothing is manually controlled
    await update()
    assert not manual_control[ENTITY_LIGHT]
    # Call light.turn_on for ENTITY_LIGHT
    await turn_light(True, brightness=increased_brightness())
    # Check that ENTITY_LIGHT is manually controlled
    assert manual_control[ENTITY_LIGHT]
    # Test adaptive_lighting.set_manual_control
    await change_manual_control(False)
    # Check that ENTITY_LIGHT is not manually controlled
    assert not manual_control[ENTITY_LIGHT]

    # Check that toggling light off to on resets manual control
    await change_manual_control(True)
    assert manual_control[ENTITY_LIGHT]
    await turn_light(False)
    await turn_light(True, brightness=increased_brightness())
    assert hass.states.get(ENTITY_LIGHT).state == STATE_ON
    assert not manual_control[ENTITY_LIGHT], manual_control

    # Check that toggling (sleep mode) switch resets manual control
    for entity_id in [ENTITY_SWITCH, ENTITY_SLEEP_MODE_SWITCH]:
        await change_manual_control(True)
        assert manual_control[ENTITY_LIGHT]
        await turn_switch(False, entity_id)
        await turn_switch(True, entity_id)
        assert not manual_control[ENTITY_LIGHT]

    # Check that manual control is still enabled if set while bulb is off.
    # Test issue #37
    await turn_light(False)
    await change_manual_control(True)
    await turn_light(True)
    assert manual_control[ENTITY_LIGHT]

    # Check that when 'adapt_brightness' is off, changing the brightness
    # doesn't mark it as manually controlled but changing color_temp
    # does
    await turn_light(False)
    await turn_light(True)  # reset manually controlled status
    assert not manual_control[ENTITY_LIGHT]
    await switch.adapt_brightness_switch.async_turn_off()
    await turn_light(True, brightness=increased_brightness())
    assert not manual_control[ENTITY_LIGHT]
    mired_range = (light.min_color_temp_kelvin, light.max_color_temp_kelvin)
    kelvin_range = (
        color_temperature_mired_to_kelvin(mired_range[1]),
        color_temperature_mired_to_kelvin(mired_range[0]),
    )
    ptp_kelvin = kelvin_range[1] - kelvin_range[0]
    await turn_light(
        True, color_temp_kelvin=(light._attr_color_temp + 100) % ptp_kelvin
    )
    assert manual_control[ENTITY_LIGHT]
    await switch.adapt_brightness_switch.async_turn_on()  # turn on again

    # Check that when 'adapt_color' is off, changing the color
    # doesn't mark it as manually controlled but changing brightness
    # does
    await turn_light(False)  # reset manually controlled status
    await turn_light(True)
    assert not manual_control[ENTITY_LIGHT]
    await switch.adapt_color_switch.async_turn_off()
    await turn_light(True, color_temp=increased_color_temp())
    assert not manual_control[ENTITY_LIGHT]
    await turn_light(True, brightness=increased_brightness())
    assert manual_control[ENTITY_LIGHT]

    # Check that when 'adapt_color' adapt_brightness are both off
    # nothing marks it as manually controlled
    await turn_light(False)  # reset manually controlled status
    await turn_light(True)
    await switch.adapt_color_switch.async_turn_off()
    await switch.adapt_brightness_switch.async_turn_off()
    assert not manual_control[ENTITY_LIGHT]
    await turn_light(True, color_temp=increased_color_temp())
    await turn_light(True, brightness=increased_brightness())
    await turn_light(
        True,
        color_temp=increased_color_temp(),
        brightness=increased_brightness(),
    )
    assert not manual_control[ENTITY_LIGHT]
    # Turn switches on again
    await switch.adapt_color_switch.async_turn_on()
    await switch.adapt_brightness_switch.async_turn_on()

    # Check that when no lights are specified, all are reset
    await change_manual_control(True, {CONF_LIGHTS: switch.lights})
    assert all([manual_control[eid] for eid in switch.lights])
    # do not pass "lights" so reset all
    await change_manual_control(False, {})
    assert all([not manual_control[eid] for eid in switch.lights])


@pytest.mark.dependency(depends=[*GLOBAL_TEST_DEPENDENCIES, "test_manual_control"])
async def test_auto_reset_manual_control(hass):
    switch, (light, *_) = await setup_lights_and_switch(
        hass, {CONF_AUTORESET_CONTROL: 0.1}
    )
    context = switch.create_context("test")  # needs to be passed to update method
    manual_control = switch.turn_on_off_listener.manual_control

    async def update():
        await switch._update_attrs_and_maybe_adapt_lights(transition=0, context=context)
        await hass.async_block_till_done()

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: light.entity_id, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()
        await update()
        _LOGGER.debug(
            "Turn light %s to state %s, to %s", light.entity_id, state, kwargs
        )

    _LOGGER.debug("Start test auto reset manual control")
    await turn_light(True, brightness=1)
    await turn_light(True, brightness=10)
    assert manual_control[light.entity_id]
    assert (
        switch.extra_state_attributes["autoreset_time_remaining"][light.entity_id] > 0
    )
    await update()
    await asyncio.sleep(0.3)  # Should be enough time for auto reset
    assert not manual_control[light.entity_id], (light, manual_control)
    assert (
        light.entity_id not in switch.extra_state_attributes["autoreset_time_remaining"]
    )

    # Do a couple of quick changes and check that light is not reset
    for i in range(3):
        _LOGGER.debug("Quick change %s", i)
        await turn_light(True, brightness=(i + 1) * 20)
        await asyncio.sleep(0.05)  # Less than 0.1
        assert manual_control[light.entity_id]

    await update()
    await asyncio.sleep(0.3)  # Wait the auto reset time
    assert not manual_control[light.entity_id]


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_apply_service(hass):
    """Test adaptive_lighting.apply service."""
    switch, (_, _, light) = await setup_lights_and_switch(hass)
    entity_id = light.entity_id
    assert entity_id not in switch.lights

    def increased_brightness():
        return (light._attr_brightness + 100) % 255

    def increased_color_temp():
        return max(
            (light._attr_color_temp + 100) % light.max_color_temp_kelvin,
            light.min_color_temp_kelvin,
        )

    async def change_light():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_BRIGHTNESS: increased_brightness(),
                ATTR_COLOR_TEMP_KELVIN: increased_color_temp(),
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    async def apply(**kwargs):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_APPLY,
            {
                ATTR_ENTITY_ID: ENTITY_SWITCH,
                CONF_LIGHTS: [entity_id],
                CONF_TURN_ON_LIGHTS: True,
                **kwargs,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    # Test turn on with defaults
    assert hass.states.get(entity_id).state == STATE_OFF
    await apply()
    assert hass.states.get(entity_id).state == STATE_ON
    await change_light()

    # Test only changing color
    old_state = hass.states.get(entity_id).attributes
    await apply(adapt_color=True, adapt_brightness=False)
    new_state = hass.states.get(entity_id).attributes
    assert old_state[ATTR_BRIGHTNESS] == new_state[ATTR_BRIGHTNESS]
    assert old_state[ATTR_COLOR_TEMP_KELVIN] != new_state[ATTR_COLOR_TEMP_KELVIN]

    # Test only changing brightness
    await change_light()
    old_state = hass.states.get(entity_id).attributes
    await apply(adapt_color=False, adapt_brightness=True)
    new_state = hass.states.get(entity_id).attributes
    assert old_state[ATTR_BRIGHTNESS] != new_state[ATTR_BRIGHTNESS]
    assert old_state[ATTR_COLOR_TEMP_KELVIN] == new_state[ATTR_COLOR_TEMP_KELVIN]


@pytest.mark.dependency(
    depends=[*GLOBAL_TEST_DEPENDENCIES, "test_apply_service", "test_manual_control"]
)
async def test_switch_off_on_off(hass):
    """Test switch rapid off_on_off."""

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()

    async def update():
        await switch._update_attrs_and_maybe_adapt_lights(
            transition=0, context=switch.create_context("test")
        )
        await hass.async_block_till_done()

    switch, _ = await setup_lights_and_switch(hass)

    for turn_light_state_at_end in [True, False]:
        # Turn light on
        await turn_light(True)
        # Turn light off with transition
        await turn_light(False, transition=1)

        assert not switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]
        # Set state to on after a second (like happens IRL)
        await asyncio.sleep(1e-3)
        hass.states.async_set(ENTITY_LIGHT, STATE_ON)
        # Set state to off after a second (like happens IRL)
        await asyncio.sleep(1e-3)
        hass.states.async_set(ENTITY_LIGHT, STATE_OFF)

        # Now we test whether the sleep task is there
        assert ENTITY_LIGHT in switch.turn_on_off_listener.sleep_tasks
        sleep_task = switch.turn_on_off_listener.sleep_tasks[ENTITY_LIGHT]
        assert not sleep_task.cancelled()

        # A 'light.turn_on' event should cancel that task
        await turn_light(turn_light_state_at_end)
        await update()
        state = hass.states.get(ENTITY_LIGHT).state
        if turn_light_state_at_end:
            assert sleep_task.cancelled()
            assert state == STATE_ON
        else:
            assert state == STATE_OFF


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
def test_color_difference_redmean():
    """Test color_difference_redmean function."""
    for _ in range(10):
        rgb_1 = (randint(0, 255), randint(0, 255), randint(0, 255))
        rgb_2 = (randint(0, 255), randint(0, 255), randint(0, 255))
        color_difference_redmean(rgb_1, rgb_2)
    color_difference_redmean((0, 0, 0), (255, 255, 255))


def test_attributes_have_changed():
    """Test _attributes_have_changed function."""
    attributes_1 = {
        ATTR_BRIGHTNESS: 1,
        ATTR_RGB_COLOR: (0, 0, 0),
        ATTR_COLOR_TEMP_KELVIN: 100,
    }
    attributes_2 = {
        ATTR_BRIGHTNESS: 100,
        ATTR_RGB_COLOR: (255, 0, 0),
        ATTR_COLOR_TEMP_KELVIN: 300,
    }
    kwargs = dict(
        light="light.test",
        adapt_brightness=True,
        adapt_color=True,
        context=Context(),
    )
    assert not _attributes_have_changed(
        old_attributes=attributes_1, new_attributes=attributes_1, **kwargs
    )
    for key, value in attributes_2.items():
        attrs = dict(attributes_1)
        attrs[key] = value
        assert _attributes_have_changed(
            old_attributes=attributes_1, new_attributes=attrs, **kwargs
        )
    _LOGGER.debug("Test switch from color_temp to rgb_color")
    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_RGB_COLOR: (255, 166, 87)},
        **kwargs,
    )
    _LOGGER.debug("Test switch from rgb_color to color_temp")
    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_RGB_COLOR: (255, 166, 87)},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        **kwargs,
    )
    _LOGGER.debug("Test switch from color_temp to color_xy")
    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_XY_COLOR: (0.526, 0.387)},
        **kwargs,
    )
    _LOGGER.debug("Test switch from color_xy to color_temp")
    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_XY_COLOR: (0.526, 0.387)},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        **kwargs,
    )


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_state_change_handlers(hass):
    """
    Test TurnOnOffListener's EVENT_STATE_CHANGED listener.
    ======================
    Sequence of events:
    1. Transition from sleep mode to normal.
    2. Create simulated transition events for that adapt.
    3. Fire all simulated transition events.
    4. Assert all possible problems that would result.
    Also tests significant changes.
    """
    switch, (light, *_) = await setup_lights_and_switch(hass)
    context = switch.create_context("test")  # needs to be passed to update method

    # [Config options]:
    transition_used = 2
    total_events = 5

    async def set_brightness(val: int):
        # 'Unsafe' set but we know what we're doing.
        hass.states.async_set(
            ENTITY_LIGHT, "on", {ATTR_BRIGHTNESS: val, ATTR_SUPPORTED_FEATURES: 1}
        )
        await hass.async_block_till_done()
        # Call code in TurnOnOffListener
        hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "new_state": {
                    ATTR_ENTITY_ID: ENTITY_LIGHT,
                    "state": "on",
                    ATTR_BRIGHTNESS: val,
                }
            },
        )
        await hass.async_block_till_done()

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()

    async def update(force: bool = False):
        await switch._update_attrs_and_maybe_adapt_lights(
            force=force, transition=0, context=context
        )
        await hass.async_block_till_done()

    # 1. Adapt to sleep without a transition.
    # Should only be one state change.
    _LOGGER.debug('test_state_change_handling: Turn on "sleep mode"')
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_SLEEP_MODE_SWITCH},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert switch.turn_on_off_listener.last_state_change.get(ENTITY_LIGHT)
    assert len(switch.turn_on_off_listener.last_state_change[ENTITY_LIGHT]) == 1
    assert not switch.turn_on_off_listener.transition_timers.get(ENTITY_LIGHT)
    last_service_data = deepcopy(switch.turn_on_off_listener.last_service_data)
    assert last_service_data.get(ENTITY_LIGHT)

    # 2 Adapt from sleep with a 'transition'.
    await switch.sleep_mode_switch.async_turn_off()
    await switch._update_attrs_and_maybe_adapt_lights(
        force=False, transition=0, context=context
    )
    await hass.async_block_till_done()
    current_service_data = switch.turn_on_off_listener.last_service_data
    assert current_service_data != last_service_data

    for light in switch.lights:
        # current_service_data should have changed after the last update.
        assert current_service_data.get(light)
        assert last_service_data.get(light)
        assert current_service_data[light] != last_service_data[light]

        # Test same context id events.
        current_service_data[light][ATTR_TRANSITION] = transition_used
        hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                ATTR_ENTITY_ID: light,
                "old_state": State(light, "on", attributes=last_service_data),
                "new_state": State(
                    light, "on", attributes=current_service_data, context=context
                ),
            },
        )
        assert not switch.turn_on_off_listener.transition_timers.get(light)

        # 2.3 Refire and overwrite the original state_changed event with our 'transition'
        hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                ATTR_ENTITY_ID: light,
                "old_state": State(light, "on", attributes=last_service_data),
                "new_state": State(
                    light,
                    "on",
                    attributes=current_service_data,
                    # We need to overwrite the old context_id
                    context=switch.create_context("test"),
                ),
            },
        )
        await hass.async_block_till_done()
        # Assert our transition timer was created.
        assert switch.turn_on_off_listener.transition_timers.get(light)
        # 2.5 Simulate a transition. There's no other way to do this in the demo.
        events = create_transition_events(
            light=light,
            state=hass.states.get(light),
            last=last_service_data[light],
            current=current_service_data[light],
            total_events=total_events,
        )
        # 3. Fire simulated events for our TurnOnOffListener
        for event in events:
            _LOGGER.debug("Test EVENT_STATE_CHANGED listener")
            hass.bus.async_fire(EVENT_STATE_CHANGED, event)
            await hass.async_block_till_done()
            # On real systems HA fires transition state changes every ~3 seconds.
            # asyncio.sleep(3)
    # 4. Assert the transition timer started and everything was filled.
    listener = switch.turn_on_off_listener
    assert listener.last_state_change.get(ENTITY_LIGHT)
    assert len(listener.last_state_change[ENTITY_LIGHT]) == total_events
    assert listener.transition_timers.get(ENTITY_LIGHT)

    # 5. Execute some checks during a transition
    _LOGGER.debug("Test detect_non_ha_changes:")
    switch._take_over_control = True
    assert switch._take_over_control
    switch._detect_non_ha_changes = True
    assert switch._detect_non_ha_changes
    await asyncio.sleep(transition_used / 3)
    # Ensure the timer still exists
    timer = listener.transition_timers.get(ENTITY_LIGHT)
    assert timer and timer.is_running()
    last_service_data = deepcopy(current_service_data)
    await update()
    assert not switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]
    await update()
    assert not switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]
    timer = listener.transition_timers.get(ENTITY_LIGHT)
    assert timer and timer.is_running()
    # Ensure the light did not adapt during the transition.
    assert last_service_data == current_service_data

    # 6. Assert everything after the transition finishes.
    await asyncio.sleep(transition_used)
    assert listener.last_state_change.get(ENTITY_LIGHT)
    assert len(listener.last_state_change[ENTITY_LIGHT]) == total_events
    # Timer should be done and reset now.
    # This is the assert that I can't fix.
    timer = listener.transition_timers.get(ENTITY_LIGHT)
    assert not timer or not timer.is_running()

    # build last service data
    await update(force=False)

    # force=True should not reset manual control.
    await turn_light(True, brightness=40)
    await turn_light(True, brightness=20)
    await update(force=False)
    assert switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]
    await update(force=True)
    assert switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]

    # turn light off then on should reset manual control.
    await turn_light(False)
    await turn_light(True)
    assert not switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]

    await turn_light(True, brightness=50)
    _LOGGER.debug("Test: Brightness set to %s", 50)

    # On next update ENTITY_LIGHT should be marked as manually controlled
    await update(force=False)
    assert switch.turn_on_off_listener.last_service_data.get(ENTITY_LIGHT) is not None
    assert switch.turn_on_off_listener.last_state_change.get(ENTITY_LIGHT) is not None
    assert switch.turn_on_off_listener.manual_control[ENTITY_LIGHT]


@pytest.mark.dependency(
    depends=[
        *GLOBAL_TEST_DEPENDENCIES,
        "test_manual_control",
        "test_apply_service",
        "test_attributes_have_changed",
        "test_state_change_handling",
    ]
)
@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
def test_is_our_context():
    """Test is_our_context function."""
    context = create_context(DOMAIN, "test", 0)
    assert is_our_context(context)
    assert not is_our_context(None)
    assert not is_our_context(Context())


async def test_unload_switch(hass):
    """Test removing Adaptive Lighting."""
    entry, _ = await setup_switch(hass, {})
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass.data


@pytest.mark.parametrize("state", [STATE_ON, STATE_OFF, None])
async def test_restore_off_state(hass, state):
    """Test that the 'off' and 'on' states are propoperly restored."""
    with patch(
        "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
        return_value=State(ENTITY_SWITCH, state) if state is not None else None,
    ):
        await hass.async_start()
        await hass.async_block_till_done()
        _, switch = await setup_switch(hass, {})
        if state == STATE_ON:
            assert switch.is_on
        elif state == STATE_OFF:
            assert not switch.is_on
        elif state is None:
            assert switch.is_on

        for _switch, initial_state in [
            (switch.sleep_mode_switch, False),
            (switch.adapt_brightness_switch, True),
            (switch.adapt_color_switch, True),
        ]:
            if state == STATE_ON:
                assert _switch.is_on
            elif state == STATE_OFF:
                assert not _switch.is_on
            elif state is None:
                if initial_state:
                    assert _switch.is_on
                else:
                    assert not _switch.is_on


@pytest.mark.xfail(reason="Offset is larger than half a day")
async def test_offset_too_large(hass):
    """Test that update fails when the offset is too large."""
    _, switch = await setup_switch(hass, {CONF_SUNRISE_OFFSET: 3600 * 12})
    await switch._update_attrs_and_maybe_adapt_lights(
        context=switch.create_context("test")
    )
    await hass.async_block_till_done()


async def test_turn_on_and_off_when_already_at_that_state(hass):
    """Test 'switch.turn_on/off' when switch is on/off."""
    _, switch = await setup_switch(hass, {})

    await switch.async_turn_on()
    await hass.async_block_till_done()
    await switch.async_turn_on()
    await hass.async_block_till_done()

    await switch.async_turn_off()
    await hass.async_block_till_done()
    await switch.async_turn_off()
    await hass.async_block_till_done()


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_async_update_at_interval(hass):
    """Test '_async_update_at_interval' method."""
    _, switch = await setup_switch(hass, {})
    await switch._async_update_at_interval()


@pytest.mark.parametrize("separate_turn_on_commands", (True, False))
@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_separate_turn_on_commands(hass, separate_turn_on_commands):
    """Test 'separate_turn_on_commands' argument."""
    switch, (light, *_) = await setup_lights_and_switch(
        hass, {CONF_SEPARATE_TURN_ON_COMMANDS: separate_turn_on_commands}
    )
    # We just turn sleep mode on and off which should change the
    # brightness and color. We don't test whether the number are exactly
    # what we expect because we do this in other tests already, we merely
    # check whether the brightness and color_temp change.
    context = switch.create_context("test")  # needs to be passed to update method
    brightness = light.brightness
    color_temp = light.color_temp
    await switch.sleep_mode_switch.async_turn_on()
    await switch._update_attrs_and_maybe_adapt_lights(context=context)
    await hass.async_block_till_done()

    # TODO: figure out why `light.brightness` is not updating
    attrs = hass.states.get(light.entity_id).attributes
    sleep_brightness = attrs["brightness"]
    sleep_color_temp = attrs["color_temp"]

    assert sleep_brightness != brightness
    assert sleep_color_temp != color_temp

    await switch.sleep_mode_switch.async_turn_off()
    await switch._update_attrs_and_maybe_adapt_lights(context=context)
    await hass.async_block_till_done()

    attrs = hass.states.get(light.entity_id).attributes
    brightness = attrs["brightness"]
    color_temp = attrs["color_temp"]

    assert sleep_brightness != brightness
    assert sleep_color_temp != color_temp


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_area(hass):
    switch, (light, *_) = await setup_lights_and_switch(hass)

    area_registry = mock_area_registry(hass)
    area_registry.async_create("test_area")

    entity = entity_registry.async_get(hass).async_get_or_create(
        LIGHT_DOMAIN, "template", light.unique_id
    )
    entity = entity_registry.async_get(hass).async_update_entity(
        entity.entity_id, area_id="test_area"
    )
    _LOGGER.debug("test_area entity: %s", entity)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_AREA_ID: entity.area_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert light.entity_id in switch.turn_on_off_listener.last_service_data
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_AREA_ID: entity.area_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    _LOGGER.debug(
        "switch.turn_on_off_listener.last_service_data: %s",
        switch.turn_on_off_listener.last_service_data,
    )
    assert light.entity_id not in switch.turn_on_off_listener.last_service_data


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_change_switch_settings_service(hass):
    """Test adaptive_lighting.change_switch_settings service."""
    switch, (_, _, light) = await setup_lights_and_switch(hass)
    entity_id = light.entity_id
    assert entity_id not in switch.lights

    async def change_switch_settings(**kwargs):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CHANGE_SWITCH_SETTINGS,
            {
                ATTR_ENTITY_ID: ENTITY_SWITCH,
                **kwargs,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    # Test changing sunrise offset
    assert switch._sun_light_settings.sunrise_offset.total_seconds() == 0
    await change_switch_settings(**{CONF_SUNRISE_OFFSET: 10})
    assert switch._sun_light_settings.sunrise_offset.total_seconds() == 10

    # Test changing max brightness
    assert switch._sun_light_settings.max_brightness == 100
    await change_switch_settings(**{CONF_MAX_BRIGHTNESS: 50})
    assert switch._sun_light_settings.max_brightness == 50

    # Test changing to illegal max brightness
    with pytest.raises(
        voluptuous.error.MultipleInvalid,
        match="value must be at most 100 for dictionary",
    ):
        await change_switch_settings(**{CONF_MAX_BRIGHTNESS: 5000})

    # Change CONF_MIN_COLOR_TEMP, the factory default is 2000, but setup_lights_and_switch
    # sets it to 2500
    assert switch._sun_light_settings.min_color_temp == 2500

    # testing with "factory" should change it to 2000
    await change_switch_settings(**{CONF_USE_DEFAULTS: "factory"})
    assert switch._sun_light_settings.min_color_temp == 2000

    # testing with "current" should not change things
    await change_switch_settings(**{CONF_USE_DEFAULTS: "current"})
    assert switch._sun_light_settings.min_color_temp == 2000

    # testing with "configuration" should revert back to 2500
    await change_switch_settings(**{CONF_USE_DEFAULTS: "configuration"})
    assert switch._sun_light_settings.min_color_temp == 2500


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_cancellable_service_calls_task(hass):
    """Test the creation and execution of the task that wraps adaptation service calls."""
    (light, *_) = await setup_lights(hass)
    _, switch = await setup_switch(hass, {CONF_SEPARATE_TURN_ON_COMMANDS: True})
    context = switch.create_context("test")

    assert switch.turn_on_off_listener.adaptation_tasks.get(light.entity_id) is None

    service_data = {
        ATTR_BRIGHTNESS: 10,
        ATTR_COLOR_TEMP_KELVIN: 10,
        ATTR_ENTITY_ID: light.entity_id,
    }
    adaptation_data = AdaptationData(
        light.entity_id,
        context,
        0,
        _create_service_call_data_iterator(hass, [service_data]),
    )
    await switch.execute_cancellable_adaptation_calls(adaptation_data)

    task = switch.turn_on_off_listener.adaptation_tasks.get(light.entity_id)
    assert task is not None
    assert task.done()


@pytest.mark.dependency(depends=GLOBAL_TEST_DEPENDENCIES)
async def test_service_calls_task_cancellation(hass):
    """Tests if the task that wraps ongoing adaptation service calls gets cancelled."""
    _, switch = await setup_switch(hass, {})
    entity_id = "test_id"

    task = asyncio.ensure_future(asyncio.sleep(1))
    switch.turn_on_off_listener.adaptation_tasks[entity_id] = task

    switch.turn_on_off_listener.cancel_ongoing_adaptation_calls(entity_id)

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert task.cancelled()


async def _turn_on_and_track_event_contexts(
    hass: HomeAssistant, context_id: str, entity_id
):
    context = Context(id=context_id)
    event_context_ids = []

    async def turn_on_off_event_listener(event: Event) -> None:
        event_context_ids.append(event.context.id)

    hass.bus.async_listen(EVENT_CALL_SERVICE, turn_on_off_event_listener)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
        context=context,
    )
    await hass.async_block_till_done()

    return event_context_ids


def _mock_sun_light_settings(switch: AdaptiveSwitch, settings: dict[str, Any]):
    sun_light_settings_mock = Mock()
    sun_light_settings_mock.get_settings = Mock(return_value=settings)
    switch._sun_light_settings = sun_light_settings_mock


async def test_proactive_adaptation(hass):
    """Validate that a proactive adaptation updates the original service call."""
    switch, _ = await setup_lights_and_switch(
        hass, {INTERNAL_CONF_PROACTIVE_SERVICE_CALL_ADAPTATION: True}, True
    )

    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
        },
    )

    event_context_ids = await _turn_on_and_track_event_contexts(
        hass, "test_context", ENTITY_LIGHT3
    )

    # Expect a single service call
    assert len(event_context_ids) == 1
    assert event_context_ids == ["test_context"]

    # Expect adapted light state
    state = hass.states.get(ENTITY_LIGHT3)
    # Sun light settings use %, state only contains absolute
    assert state.attributes[ATTR_BRIGHTNESS] == 171  # == 67%
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 3448


async def test_proactive_adaptation_with_separate_commands(hass):
    """Validate that a split proactive adaptation yields one additional service call."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {
            INTERNAL_CONF_PROACTIVE_SERVICE_CALL_ADAPTATION: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
        },
        True,
    )

    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
        },
    )

    event_context_ids = await _turn_on_and_track_event_contexts(
        hass, "test_context", ENTITY_LIGHT3
    )

    # Expect two service calls
    assert len(event_context_ids) == 2
    assert event_context_ids[0] == "test_context"
    assert is_our_context_id(event_context_ids[1])

    # Expect adapted light state
    state = hass.states.get(ENTITY_LIGHT3)
    assert state.attributes[ATTR_BRIGHTNESS] == 171
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 3448


async def test_proactive_adaptation_toggle(hass):
    """Validate that a proactive adaptation updates service calls which toggle a light on,
    but not those which toggle off.

    This test is based on the fact that contexts of proactive adaptations are recorded.
    """
    switch, _ = await setup_lights_and_switch(
        hass, {INTERNAL_CONF_PROACTIVE_SERVICE_CALL_ADAPTATION: True}, True
    )

    # Toggle ON
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TOGGLE,
        {ATTR_ENTITY_ID: ENTITY_LIGHT3},
        blocking=True,
        context=Context(id="test1"),
    )

    assert switch.turn_on_off_listener.is_proactively_adapting("test1")

    # Toggle OFF
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TOGGLE,
        {ATTR_ENTITY_ID: ENTITY_LIGHT3},
        blocking=True,
        context=Context(id="test2"),
    )

    assert not switch.turn_on_off_listener.is_proactively_adapting("test2")


async def test_proactive_adaptation_transition_override(hass):
    """Validate that transitions in service calls are preferred over the default transition."""
    switch, (_, _, light3) = await setup_lights_and_switch(
        hass,
        {
            INTERNAL_CONF_PROACTIVE_SERVICE_CALL_ADAPTATION: True,
            CONF_INITIAL_TRANSITION: 123,
        },
        True,
    )

    with patch.object(
        light3, "async_turn_on", wraps=light3.async_turn_on
    ) as patched_async_turn_on:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: ENTITY_LIGHT3},
            blocking=True,
        )

        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: ENTITY_LIGHT3, ATTR_TRANSITION: 456},
            blocking=True,
        )

    # Assert that default is used when no transition is specified in service call
    kwargs = patched_async_turn_on.call_args_list[0].kwargs
    assert set({ATTR_TRANSITION: 123}.items()).issubset(kwargs.items())

    # Assert that specified service call transition takes precedence over default
    kwargs = patched_async_turn_on.call_args_list[1].kwargs
    assert set({ATTR_TRANSITION: 456}.items()).issubset(kwargs.items())

    # Cleanup
    switch.turn_on_off_listener.cancel_ongoing_adaptation_calls(ENTITY_LIGHT3)
