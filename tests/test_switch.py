"""Tests for Adaptive Lighting switches."""

# pylint: disable=protected-access
import asyncio
import contextlib
import datetime
import logging
from copy import deepcopy
from random import randint
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import homeassistant.util.dt as dt_util
import pytest
import ulid_transform
import voluptuous.error
from flaky import flaky
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    AdaptationData,
    LightControlAttributes,
    _create_service_call_data_iterator,
)
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    lerp_color_hsv,
)
from homeassistant.components.adaptive_lighting.const import (
    ADAPT_BRIGHTNESS_SWITCH,
    ADAPT_COLOR_SWITCH,
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    CONF_ADAPT_ONLY_ON_BARE_TURN_ON,
    CONF_ADAPT_UNTIL_SLEEP,
    CONF_AUTORESET_CONTROL,
    CONF_BRIGHTNESS_MODE,
    CONF_BRIGHTNESS_MODE_TIME_DARK,
    CONF_BRIGHTNESS_MODE_TIME_LIGHT,
    CONF_DETECT_NON_HA_CHANGES,
    CONF_INITIAL_TRANSITION,
    CONF_MANUAL_CONTROL,
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_PREFER_RGB_COLOR,
    CONF_RESET_MANUAL_CONTROL_ON_SLEEP_MODE_CHANGE,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_RGB_OR_COLOR_TEMP,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    CONF_TAKE_OVER_CONTROL,
    CONF_TAKE_OVER_CONTROL_MODE,
    CONF_TRANSITION,
    CONF_TURN_ON_LIGHTS,
    CONF_USE_DEFAULTS,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_NAME,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_COLOR_TEMP,
    DEFAULT_SLEEP_RGB_COLOR,
    DOMAIN,
    SERVICE_APPLY,
    SERVICE_CHANGE_SWITCH_SETTINGS,
    SERVICE_SET_MANUAL_CONTROL,
    SLEEP_MODE_SWITCH,
    UNDO_UPDATE_LISTENER,
    TakeOverControlMode,
)
from homeassistant.components.adaptive_lighting.switch import (
    CONF_INTERCEPT,
    AdaptiveLightingManager,
    AdaptiveSwitch,
    SimpleSwitch,
    _attributes_have_changed,
    _expand_light_groups,
    color_difference_redmean,
    create_context,
    is_our_context,
    is_our_context_id,
    short_hash,
    validate,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    SERVICE_TURN_OFF,
    ColorMode,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.template import light as template_light
from homeassistant.components.template.light import StateLightEntity as LightTemplate
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER, ConfigEntryState
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_DEVICE_ID,
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
    EntityCategory,
)
from homeassistant.core import Context, Event, HomeAssistant, State
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.setup import async_setup_component
from homeassistant.util.color import color_temperature_mired_to_kelvin

from tests.common import MockConfigEntry
from tests.common import mock_area_registry as mock_ha_area_registry

# HA 2026.6 removed the legacy `light: platform: template` YAML format
# (home-assistant/core#169615); use the modern `template:` format there.
LEGACY_TEMPLATE_LIGHTS = hasattr(template_light, "PLATFORM_SCHEMA")

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

ENTITY_LIGHT_1 = "light.light_1"
ENTITY_LIGHT_2 = "light.light_2"
ENTITY_LIGHT_3 = "light.light_3"
_SWITCH_FMT = f"{SWITCH_DOMAIN}.{DOMAIN}"
ENTITY_SWITCH = f"{_SWITCH_FMT}_{DEFAULT_NAME}"
ENTITY_SLEEP_MODE_SWITCH = f"{_SWITCH_FMT}_{DEFAULT_NAME}_sleep_mode"
ENTITY_ADAPT_BRIGHTNESS_SWITCH = f"{_SWITCH_FMT}_{DEFAULT_NAME}_adapt_brightness"
ENTITY_ADAPT_COLOR_SWITCH = f"{_SWITCH_FMT}_{DEFAULT_NAME}_adapt_color"

ORIG_TIMEZONE = dt_util.DEFAULT_TIME_ZONE


def create_random_context() -> str:
    return Context(id=ulid_transform.ulid_now(), parent_id=None)


@pytest.fixture
def reset_time_zone():
    """Reset time zone."""
    yield
    dt_util.DEFAULT_TIME_ZONE = ORIG_TIMEZONE


@pytest.fixture
async def cleanup(hass):
    yield
    manager: AdaptiveLightingManager = hass.data[DOMAIN][ATTR_ADAPTIVE_LIGHTING_MANAGER]
    for timer in manager.auto_reset_manual_control_timers.values():
        timer.cancel()
    for timer in manager.transition_timers.values():
        timer.cancel()
    for task in manager.adaptation_tasks:
        task.cancel()


async def setup_switch(hass, extra_data) -> tuple[MockConfigEntry, AdaptiveSwitch]:
    """Create the switch entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_INTERCEPT: False,
            **extra_data,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    switch = hass.data[DOMAIN][entry.entry_id][SWITCH_DOMAIN]
    return entry, switch


async def setup_lights(hass: HomeAssistant, with_group: bool = False):
    """Set up 3 light entities using the 'template' platform."""
    n = 3 if not with_group else 5  # last 2 will be put in a group

    group_platform = {
        "platform": "group",
        "entities": ["light.light_4", "light.light_5"],
        "name": "Light Group",
        "unique_id": "light_group",
        "all": "false",
    }

    if LEGACY_TEMPLATE_LIGHTS:
        template_lights = {
            f"light_{i}": {
                "unique_id": f"light_{i}",
                "friendly_name": f"light_{i}",
                "turn_on": None,
                "turn_off": None,
                "set_level": None,
                "set_temperature": None,
                "set_color": None,
            }
            for i in range(1, n + 1)
        }
        template_lights["light_3"]["supports_transition_template"] = True
        platforms = [{"platform": "template", "lights": template_lights}]
        if with_group:
            platforms.append(group_platform)
        await async_setup_component(
            hass,
            LIGHT_DOMAIN,
            {LIGHT_DOMAIN: platforms},
        )
    else:
        if with_group:
            # Setting up `template` below also sets up the `light` domain,
            # after which `async_setup_component(hass, LIGHT_DOMAIN, ...)`
            # would be a no-op, so the group platform must be set up first.
            await async_setup_component(
                hass,
                LIGHT_DOMAIN,
                {LIGHT_DOMAIN: [group_platform]},
            )
        modern_lights = [
            {
                "name": f"light_{i}",
                "unique_id": f"light_{i}",
                "turn_on": None,
                "turn_off": None,
                "set_level": None,
                "set_temperature": None,
                "set_hs": None,
            }
            for i in range(1, n + 1)
        ]
        modern_lights[2]["supports_transition"] = "{{ true }}"
        await async_setup_component(
            hass,
            "template",
            {"template": {"light": modern_lights}},
        )
    await hass.async_block_till_done()

    if with_group:
        state = hass.states.get("light.light_group")
        assert state.attributes["entity_id"] == ["light.light_4", "light.light_5"]

    platform = async_get_platforms(hass, "template")
    lights = list(platform[0].entities.values())

    await lights[0].async_turn_on()
    await lights[1].async_turn_on()
    for light in lights[2:]:
        await light.async_turn_off()

    for light in lights:
        set_light_brightness(light, 255)
        light._attr_color_temp = 250
        light.async_write_ha_state()

    assert all(hass.states.get(light.entity_id) is not None for light in lights)
    return lights


def set_light_brightness(light: LightTemplate, brightness: int) -> None:
    """Set brightness across Home Assistant template light internals."""
    if hasattr(light, "_brightness"):
        light._brightness = brightness
    light._attr_brightness = brightness


async def setup_lights_and_switch(
    hass,
    extra_conf=None,
    all_lights: bool = False,
) -> tuple[AdaptiveSwitch, list[LightTemplate]]:
    """Create switch and demo lights."""
    # Setup demo lights and turn on
    lights_instances = await setup_lights(hass)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_1},
        blocking=True,
    )

    # Setup switch
    lights = [
        ENTITY_LIGHT_1,
        ENTITY_LIGHT_2,
    ]

    if all_lights:
        lights.append(ENTITY_LIGHT_3)

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
                light,
                "on",
                attributes=attributes,
                context=create_random_context(),
            ),
        }
        all_events.append(event_data)
    return all_events


async def test_adaptive_lighting_switches(hass):
    """Test switches created for adaptive_lighting integration."""
    entry, switch = await setup_switch(hass, {})

    assert len(hass.states.async_entity_ids(SWITCH_DOMAIN)) == 4
    assert set(hass.states.async_entity_ids(SWITCH_DOMAIN)) == {
        switch.entity_id,
        switch.sleep_mode_switch.entity_id,
        switch.adapt_color_switch.entity_id,
        switch.adapt_brightness_switch.entity_id,
    }
    assert ATTR_ADAPTIVE_LIGHTING_MANAGER in hass.data[DOMAIN]
    assert entry.entry_id in hass.data[DOMAIN]
    assert len(hass.data[DOMAIN].keys()) == 2

    data = hass.data[DOMAIN][entry.entry_id]
    assert SLEEP_MODE_SWITCH in data
    assert SWITCH_DOMAIN in data
    assert ADAPT_COLOR_SWITCH in data
    assert ADAPT_BRIGHTNESS_SWITCH in data
    assert UNDO_UPDATE_LISTENER in data

    assert len(data.keys()) == 5


def async_process_ha_core_config(hass, config):
    """Set up the Home Assistant configuration."""
    try:
        # ha >= "2023.11.0"
        from homeassistant.core_config import async_process_ha_core_config

        return async_process_ha_core_config(hass, config)
    except ModuleNotFoundError:
        import homeassistant.config as config_util

        return config_util.async_process_ha_core_config(hass, config)


@pytest.mark.parametrize(("lat", "long", "timezone"), LAT_LONG_TZS)
async def test_adaptive_lighting_time_zones_with_default_settings(
    hass,
    lat,
    long,
    timezone,
    reset_time_zone,  # pylint: disable=redefined-outer-name
):
    """Test setting up the Adaptive Lighting switches with different timezones."""
    await async_process_ha_core_config(
        hass,
        {"latitude": lat, "longitude": long, "time_zone": timezone, "country": "US"},
    )
    _, switch = await setup_switch(hass, {})
    # Shouldn't raise an exception ever
    await switch._update_attrs_and_maybe_adapt_lights(
        context=switch.create_context("test"),
    )


@pytest.mark.parametrize(("lat", "long", "timezone"), LAT_LONG_TZS)
async def test_adaptive_lighting_time_zones_and_sun_settings(
    hass,
    lat,
    long,
    timezone,
    reset_time_zone,  # pylint: disable=redefined-outer-name
):
    """Test setting up the Adaptive Lighting switches with different timezones.

    Also test the (sleep) brightness and color temperature settings.
    """
    await async_process_ha_core_config(
        hass,
        {"latitude": lat, "longitude": long, "time_zone": timezone, "country": "US"},
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
        with patch(
            "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
            return_value=time,
        ):
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
        {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    light_states = [hass.states.get(light) for light in lights]
    for state in light_states:
        assert state.attributes[ATTR_BRIGHTNESS] == round(
            255 * switch._settings[ATTR_BRIGHTNESS_PCT] / 100,
        )
        last_service_data = switch.manager.last_service_data[state.entity_id]
        assert state.attributes[ATTR_BRIGHTNESS] == last_service_data[ATTR_BRIGHTNESS]
        assert (
            state.attributes[ATTR_COLOR_TEMP_KELVIN]
            == last_service_data[ATTR_COLOR_TEMP_KELVIN]
        )

    # Turn off "sleep mode"
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
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
        with patch(
            "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
            return_value=time,
        ):
            await switch._update_attrs_and_maybe_adapt_lights(
                context=context,
                transition=0,
                force=True,
            )
            await hass.async_block_till_done()
            return [hass.states.get(light) for light in lights]

    def assert_expected_color_temp(state):
        last_service_data = switch.manager.last_service_data[state.entity_id]
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


async def test_manager_not_tracking_untracked_lights(hass):
    """Test that lights that are not in a Adaptive Lighting switch aren't tracked."""
    switch, _ = await setup_lights_and_switch(hass)
    light = ENTITY_LIGHT_3
    assert light not in switch.lights
    for state in [True, False]:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: light},
            blocking=True,
        )
        await switch._update_attrs_and_maybe_adapt_lights(
            context=switch.create_context("test"),
        )
        await hass.async_block_till_done()
    assert light not in switch.manager.lights


@pytest.mark.parametrize("adapt_only_on_bare_turn_on", [True, False])
@pytest.mark.parametrize("proactive_service_call_adaptation", [True, False])
async def test_manual_control(
    hass,
    adapt_only_on_bare_turn_on,
    proactive_service_call_adaptation,
):
    """Test the 'manual control' tracking."""
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {
            CONF_ADAPT_ONLY_ON_BARE_TURN_ON: adapt_only_on_bare_turn_on,
            CONF_INTERCEPT: proactive_service_call_adaptation,
        },
    )
    assert switch._take_over_control
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_ON

    context = switch.create_context("test")  # needs to be passed to update method
    manual_control = switch.manager.manual_control

    async def update():
        await switch._update_attrs_and_maybe_adapt_lights(context=context, transition=0)
        await hass.async_block_till_done()

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_1, **kwargs},
            blocking=True,
        )
        _LOGGER.debug("Turn light %s, to %s", "on" if state else "off", kwargs)
        await hass.async_block_till_done()
        await update()

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
            extra_service_data = {CONF_LIGHTS: [ENTITY_LIGHT_1]}
        _LOGGER.debug(f"{switch.manager.manual_control=}")
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
        _LOGGER.debug(f"{switch.manager.manual_control=}")
        _LOGGER.debug("Called set_manual_control with %s", set_to)
        await hass.async_block_till_done()
        await update()
        _LOGGER.debug("End of change_manual_control")

    def increased_brightness():
        return (light._attr_brightness + 100) % 255

    def increased_color_temp():
        return max(
            (light._attr_color_temp + 100) % light.max_color_temp_kelvin,
            light.min_color_temp_kelvin,
        )

    # Nothing is manually controlled
    await update()
    assert not manual_control[ENTITY_LIGHT_1]
    # Call light.turn_on for ENTITY_LIGHT_1
    await turn_light(True, brightness=increased_brightness())
    # Check that ENTITY_LIGHT_1 is manually controlled
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.BRIGHTNESS
    # Per-attribute state attributes should reflect this
    state_attrs = hass.states.get(switch.entity_id).attributes
    assert ENTITY_LIGHT_1 in state_attrs["manual_control"]
    assert ENTITY_LIGHT_1 in state_attrs["manual_control_brightness"]
    assert ENTITY_LIGHT_1 not in state_attrs["manual_control_color"]
    # Test adaptive_lighting.set_manual_control
    await change_manual_control(False)
    # Check that ENTITY_LIGHT_1 is not manually controlled
    assert not manual_control[ENTITY_LIGHT_1]
    state_attrs = hass.states.get(switch.entity_id).attributes
    assert ENTITY_LIGHT_1 not in state_attrs["manual_control"]
    assert ENTITY_LIGHT_1 not in state_attrs["manual_control_brightness"]
    assert ENTITY_LIGHT_1 not in state_attrs["manual_control_color"]

    # Check that toggling light off to on resets manual control
    await change_manual_control(True)
    assert manual_control[ENTITY_LIGHT_1]
    await turn_light(False)
    assert not manual_control[ENTITY_LIGHT_1], manual_control
    await turn_light(True, brightness=increased_brightness())
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_ON
    # Turning on from OFF with brightness:
    # - With adapt_only_on_bare_turn_on=True: SHOULD mark as manually controlled (to preserve scenes)
    # - With adapt_only_on_bare_turn_on=False: should NOT mark (fix for issue #1378)
    if adapt_only_on_bare_turn_on:
        assert (
            manual_control[ENTITY_LIGHT_1] == LightControlAttributes.BRIGHTNESS
        ), manual_control
    else:
        assert not manual_control[ENTITY_LIGHT_1], manual_control
    # Reset for next test
    await turn_light(False)
    await turn_light(True)
    assert not manual_control[ENTITY_LIGHT_1], manual_control
    # Now change brightness while ON - this should always be manual control
    await turn_light(True, brightness=increased_brightness())
    assert (
        manual_control[ENTITY_LIGHT_1] == LightControlAttributes.BRIGHTNESS
    ), manual_control

    # Toggling the main or sleep switch resets manual control by default.
    for entity_id in [switch.entity_id, switch.sleep_mode_switch.entity_id]:
        await change_manual_control(True)
        assert manual_control[ENTITY_LIGHT_1]
        await turn_switch(False, entity_id)
        await turn_switch(True, entity_id)
        assert not manual_control[ENTITY_LIGHT_1]

    # Check that manual control is still enabled if set while bulb is off.
    # Test issue #37
    await turn_light(False)
    await change_manual_control(True)
    await turn_light(True)
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.ALL

    # Check that when 'adapt_brightness' is off, changing the brightness
    # doesn't mark it as manually controlled but changing color_temp
    # does
    await turn_light(False)
    await turn_light(True)  # reset manually controlled status
    assert not manual_control[ENTITY_LIGHT_1]
    await switch.adapt_brightness_switch.async_turn_off()
    await turn_light(True, brightness=increased_brightness())
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.BRIGHTNESS
    mired_range = (light.min_color_temp_kelvin, light.max_color_temp_kelvin)
    kelvin_range = (
        color_temperature_mired_to_kelvin(mired_range[1]),
        color_temperature_mired_to_kelvin(mired_range[0]),
    )
    ptp_kelvin = kelvin_range[1] - kelvin_range[0]
    await turn_light(
        True,
        color_temp_kelvin=(light._attr_color_temp + 100) % ptp_kelvin,
    )
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.ALL
    await switch.adapt_brightness_switch.async_turn_on()  # turn on again

    # Check that when 'adapt_color' is off, changing the color
    # doesn't mark it as manually controlled but changing brightness
    # does
    await turn_light(False)  # reset manually controlled status
    await turn_light(True)
    assert not manual_control[ENTITY_LIGHT_1]
    await switch.adapt_color_switch.async_turn_off()
    await turn_light(True, color_temp_kelvin=increased_color_temp())
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.COLOR
    await turn_light(True, brightness=increased_brightness())
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.ALL

    # Check that when 'adapt_color' adapt_brightness are both off
    # nothing marks it as manually controlled
    await turn_light(False)  # reset manually controlled status
    await turn_light(True)
    await switch.adapt_color_switch.async_turn_off()
    await switch.adapt_brightness_switch.async_turn_off()
    assert not manual_control[ENTITY_LIGHT_1]
    await turn_light(True, color_temp_kelvin=increased_color_temp())
    await turn_light(True, brightness=increased_brightness())
    await turn_light(
        True,
        color_temp_kelvin=increased_color_temp(),
        brightness=increased_brightness(),
    )
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.ALL
    # Turn switches on again
    await switch.adapt_color_switch.async_turn_on()
    await switch.adapt_brightness_switch.async_turn_on()

    # Check that when no lights are specified, all are reset
    await change_manual_control(True, {CONF_LIGHTS: switch.lights})
    assert all(manual_control[eid] for eid in switch.lights)
    # do not pass "lights" so reset all
    await change_manual_control(False, {})
    assert all(not manual_control[eid] for eid in switch.lights)

    # Turn off light and turn on using adaptive_lighting.apply
    await turn_light(False)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_APPLY,
        {
            ATTR_ENTITY_ID: switch.entity_id,
            CONF_LIGHTS: [ENTITY_LIGHT_1],
            CONF_TURN_ON_LIGHTS: True,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_ON
    assert not manual_control[ENTITY_LIGHT_1]

    # Check that manual control `True` sets all attributes
    await change_manual_control(False)
    assert not manual_control[ENTITY_LIGHT_1]
    await change_manual_control(True)
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.ALL
    state_attrs = hass.states.get(switch.entity_id).attributes
    assert state_attrs["manual_control_brightness"] == [ENTITY_LIGHT_1]
    assert state_attrs["manual_control_color"] == [ENTITY_LIGHT_1]

    # Check that manual control `False` unsets all attributes
    await change_manual_control(False)
    assert not manual_control[ENTITY_LIGHT_1]

    # Check that manual control attributes can be selectively set
    await change_manual_control("brightness")
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.BRIGHTNESS
    await change_manual_control("color")
    assert manual_control[ENTITY_LIGHT_1] == LightControlAttributes.COLOR
    state_attrs = hass.states.get(switch.entity_id).attributes
    assert state_attrs["manual_control_brightness"] == []
    assert state_attrs["manual_control_color"] == [ENTITY_LIGHT_1]


@pytest.mark.parametrize("reset_on_sleep", [None, True, False])
async def test_sleep_mode_manual_control_reset(hass, reset_on_sleep):
    """Keep the old default and preserve manual brightness only when opted out."""
    options = {CONF_MIN_BRIGHTNESS: 50, CONF_MAX_BRIGHTNESS: 50}
    if reset_on_sleep is not None:
        options[CONF_RESET_MANUAL_CONTROL_ON_SLEEP_MODE_CHANGE] = reset_on_sleep
    switch, (light, *_) = await setup_lights_and_switch(hass, options)

    for service, adapted_brightness in [(SERVICE_TURN_ON, 3), (SERVICE_TURN_OFF, 128)]:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: light.entity_id, ATTR_BRIGHTNESS: 200},
            blocking=True,
        )
        await hass.async_block_till_done()
        assert switch.manager.get_manual_control_attributes(light.entity_id)
        await hass.services.async_call(
            SWITCH_DOMAIN,
            service,
            {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
        if reset_on_sleep is False:
            assert switch.manager.get_manual_control_attributes(light.entity_id)
            assert hass.states.get(light.entity_id).attributes[ATTR_BRIGHTNESS] == 200
        else:
            assert not switch.manager.get_manual_control_attributes(light.entity_id)
            assert (
                hass.states.get(light.entity_id).attributes[ATTR_BRIGHTNESS]
                == adapted_brightness
            )


async def test_sleep_mode_preserves_manual_control_and_cancels_old_adaptation(hass):
    """A queued pre-sleep command must not overwrite a preserved manual setting."""
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {CONF_RESET_MANUAL_CONTROL_ON_SLEEP_MODE_CHANGE: False},
    )
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def pending_service_data():
        waiting.set()
        await release.wait()
        yield {ATTR_ENTITY_ID: light.entity_id, ATTR_BRIGHTNESS: 1}

    data = AdaptationData(
        light.entity_id,
        switch.create_context("test"),
        0,
        pending_service_data(),
        force=False,
        max_length=1,
        attributes=LightControlAttributes.BRIGHTNESS,
    )
    task = asyncio.create_task(switch.execute_cancellable_adaptation_calls(data))
    await waiting.wait()
    try:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: light.entity_id, ATTR_BRIGHTNESS: 200},
            blocking=True,
        )
        await hass.async_block_till_done()
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
    finally:
        release.set()
        await task
    await hass.async_block_till_done()
    assert switch.manager.get_manual_control_attributes(light.entity_id)
    assert hass.states.get(light.entity_id).attributes[ATTR_BRIGHTNESS] == 200


@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize("mode", list(TakeOverControlMode))
async def test_auto_reset_manual_control(hass, mode):
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {CONF_AUTORESET_CONTROL: 0.1, CONF_TAKE_OVER_CONTROL_MODE: mode},
    )
    context = switch.create_context("test")  # needs to be passed to update method
    manual_control = switch.manager.manual_control

    async def update():
        await switch._update_attrs_and_maybe_adapt_lights(context=context, transition=0)
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
            "Turn light %s to state %s, to %s",
            light.entity_id,
            state,
            kwargs,
        )

    _LOGGER.debug("Start test auto reset manual control")
    await turn_light(True, brightness=1)
    await turn_light(True, brightness=10)
    assert manual_control[light.entity_id] == LightControlAttributes.BRIGHTNESS
    assert (
        switch.extra_state_attributes["autoreset_time_remaining"][light.entity_id] > 0
    )
    await update()
    # The auto reset must also re-adapt the light right away, not only clear the
    # flag. Collect the 'light.turn_on' calls made with the 'autoreset' context.
    autoreset_calls: list[Event] = []

    async def _on_call_service(event: Event) -> None:
        if (
            event.data.get("domain") == LIGHT_DOMAIN
            and event.data.get("service") == SERVICE_TURN_ON
            and is_our_context(event.context, "autoreset")
        ):
            autoreset_calls.append(event)

    remove_listener = hass.bus.async_listen(EVENT_CALL_SERVICE, _on_call_service)
    await asyncio.sleep(0.3)  # Should be enough time for auto reset
    await hass.async_block_till_done()
    remove_listener()
    assert not manual_control[light.entity_id], (light, manual_control)
    assert (
        light.entity_id not in switch.extra_state_attributes["autoreset_time_remaining"]
    )
    assert autoreset_calls, "auto reset did not re-adapt the light"

    # Do a couple of quick changes and check that light is not reset
    for i in range(3):
        _LOGGER.debug("Quick change %s", i)
        await turn_light(True, brightness=(i + 1) * 20)
        await asyncio.sleep(0.05)  # Less than 0.1
        assert manual_control[light.entity_id]

    await update()
    await asyncio.sleep(0.3)  # Wait the auto reset time
    assert not manual_control[light.entity_id]


@pytest.mark.parametrize("intercept", [False, True])
@pytest.mark.parametrize("mode", list(TakeOverControlMode))
@pytest.mark.parametrize(
    ("attribute", "value", "next_value", "manual_attributes"),
    [
        (ATTR_BRIGHTNESS, 10, 20, LightControlAttributes.BRIGHTNESS),
        (ATTR_COLOR_TEMP_KELVIN, 2000, 2200, LightControlAttributes.COLOR),
    ],
)
async def test_interval_adaptation_preserves_manual_control_timeout(
    hass,
    freezer,
    cleanup,
    intercept,
    mode,
    attribute,
    value,
    next_value,
    manual_attributes,
):
    """Adaptation must not postpone auto reset; another manual change must."""
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {
            CONF_AUTORESET_CONTROL: 7200,
            CONF_TAKE_OVER_CONTROL_MODE: mode,
            CONF_DETECT_NON_HA_CHANGES: False,
            CONF_INTERCEPT: intercept,
        },
    )

    async def change_manually(value):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: light.entity_id, attribute: value},
            blocking=True,
        )
        await hass.async_block_till_done()

    for manual_value in (value, next_value):
        # A new external change to the already-manual axis restarts the timer.
        await change_manually(manual_value)
        assert (
            switch.extra_state_attributes["autoreset_time_remaining"][light.entity_id]
            == 7200
        )
        for elapsed in (90, 180):
            freezer.tick(90)
            await switch._async_update_at_interval_action()
            await hass.async_block_till_done()
            assert (
                switch.manager.get_manual_control_attributes(light.entity_id)
                == manual_attributes
            )
            assert (
                switch.extra_state_attributes["autoreset_time_remaining"][
                    light.entity_id
                ]
                == 7200 - elapsed
            )

    # An external bare turn-on also keeps its existing timer restart behavior.
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: light.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert (
        switch.extra_state_attributes["autoreset_time_remaining"][light.entity_id]
        == 7200
    )


@pytest.mark.parametrize("mode", list(TakeOverControlMode))
@pytest.mark.parametrize("service_data", [{}, {ATTR_BRIGHTNESS: 20}])
async def test_mixed_turn_on_restarts_manual_control_timeout(
    hass,
    freezer,
    cleanup,
    mode,
    service_data,
):
    """A mixed-target request must renew manual control on its skipped light."""
    switch, (manual_light, _, off_light) = await setup_lights_and_switch(
        hass,
        {
            CONF_AUTORESET_CONTROL: 7200,
            CONF_TAKE_OVER_CONTROL_MODE: mode,
            CONF_DETECT_NON_HA_CHANGES: False,
            CONF_INTERCEPT: True,
        },
        all_lights=True,
    )
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: manual_light.entity_id, ATTR_BRIGHTNESS: 10},
        blocking=True,
    )
    await hass.async_block_till_done()
    freezer.tick(90)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: [manual_light.entity_id, off_light.entity_id],
            **service_data,
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    # HA dispatches the original external event before interception. It renews
    # manual control even though the skipped target is replayed in our context.
    assert hass.states.is_state(off_light.entity_id, STATE_ON)
    assert is_our_context(
        switch.manager.turn_on_event[manual_light.entity_id].context,
        "skipped",
    )
    assert (
        switch.manager.get_manual_control_attributes(manual_light.entity_id)
        == LightControlAttributes.BRIGHTNESS
    )
    assert (
        switch.extra_state_attributes["autoreset_time_remaining"][
            manual_light.entity_id
        ]
        == 7200
    )


@pytest.mark.parametrize("intercept", [True, False])
@pytest.mark.parametrize(
    ("service_data", "brightness", "color"),
    [
        ({ATTR_BRIGHTNESS: 200}, True, False),
        ({"brightness_step": 5}, True, False),
        ({ATTR_COLOR_TEMP_KELVIN: 4000}, False, True),
        ({ATTR_BRIGHTNESS: 200, ATTR_COLOR_TEMP_KELVIN: 4000}, True, True),
    ],
)
async def test_manual_control_state_updates_without_adaptation(
    hass,
    intercept,
    service_data,
    brightness,
    color,
):
    """Publish manual state on service changes and resets, without an interval tick."""
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {
            CONF_INTERCEPT: intercept,
            CONF_MIN_BRIGHTNESS: 50,
            CONF_MAX_BRIGHTNESS: 50,
        },
    )
    events = []
    hass.bus.async_listen(f"{DOMAIN}.manual_control", events.append)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: light.entity_id, **service_data},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    attrs = hass.states.get(switch.entity_id).attributes
    assert attrs["manual_control"] == [light.entity_id]
    assert attrs["manual_control_brightness"] == (
        [light.entity_id] if brightness else []
    )
    assert attrs["manual_control_color"] == ([light.entity_id] if color else [])
    assert len(events) == 1

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: light.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    attrs = hass.states.get(switch.entity_id).attributes
    assert attrs["manual_control"] == []
    assert attrs["manual_control_brightness"] == []
    assert attrs["manual_control_color"] == []


async def test_manual_control_state_updates_shared_switches(hass):
    """Publish shared state on both profiles when one receives a service call."""
    switch, (light, *_) = await setup_lights_and_switch(hass)
    _, other = await setup_switch(
        hass,
        {CONF_NAME: "other", CONF_LIGHTS: [light.entity_id]},
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {
            ATTR_ENTITY_ID: switch.entity_id,
            CONF_LIGHTS: [light.entity_id],
            CONF_MANUAL_CONTROL: "brightness",
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    for profile in (switch, other):
        attrs = hass.states.get(profile.entity_id).attributes
        assert attrs["manual_control"] == [light.entity_id]
        assert attrs["manual_control_brightness"] == [light.entity_id]
        assert attrs["manual_control_color"] == []

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {ATTR_ENTITY_ID: other.entity_id, CONF_MANUAL_CONTROL: False},
        blocking=True,
    )
    await hass.async_block_till_done()
    for profile in (switch, other):
        attrs = hass.states.get(profile.entity_id).attributes
        assert attrs["manual_control"] == []
        assert attrs["manual_control_brightness"] == []
        assert attrs["manual_control_color"] == []


async def test_manual_control_state_ignores_incomplete_entries(hass):
    """An entry awaiting platform setup must not break another profile's updates."""
    switch, (light, *_) = await setup_lights_and_switch(hass)
    pending = MockConfigEntry(domain=DOMAIN, data={CONF_NAME: "pending"})
    pending.add_to_hass(hass)
    hass.data[DOMAIN][pending.entry_id] = {}

    switch.manager.set_manual_control_attributes(light.entity_id)
    await hass.async_block_till_done()
    assert hass.states.get(switch.entity_id).attributes["manual_control"] == [
        light.entity_id,
    ]


async def test_adaptation_attribute_selection(hass):
    """Test the 'manual control' tracking."""
    switch, (light, *_) = await setup_lights_and_switch(hass)

    # Assert default settings
    assert switch._take_over_control
    assert switch._take_over_control_mode == TakeOverControlMode.PAUSE_ALL

    # Check that PAUSE_ALL leads to adaptation of all attributes when none are manually controlled
    assert (
        switch.manager.get_manual_control_attributes(ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.ALL
    )

    # Check that PAUSE_ALL leads to no adaptation when a single attribute is manually controlled
    switch.manager.add_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.BRIGHTNESS,
    )
    assert (
        switch.manager.get_manual_control_attributes(ENTITY_LIGHT_1)
        == LightControlAttributes.BRIGHTNESS
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )

    # Check that PAUSE_ALL leads to no adaptation when all attributes are manually controlled
    switch.manager.add_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.COLOR,
    )
    assert (
        switch.manager.get_manual_control_attributes(ENTITY_LIGHT_1)
        == LightControlAttributes.ALL
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )

    switch._take_over_control_mode = TakeOverControlMode.PAUSE_CHANGED
    switch.manager.set_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.NONE,
    )

    # Check that PAUSE_CHANGED leads to adaptation of all attributes when none are manually controlled
    assert (
        switch.manager.get_manual_control_attributes(ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.ALL
    )

    # Check that PAUSE_CHANGED leads to adaptation of the remaining non-manual attributes
    switch.manager.add_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.BRIGHTNESS,
    )
    assert (
        switch.manager.get_manual_control_attributes(ENTITY_LIGHT_1)
        == LightControlAttributes.BRIGHTNESS
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.COLOR
    )

    # Check that PAUSE_CHANGED leads to no adaptation when all attributes are manually controlled
    switch.manager.add_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.COLOR,
    )
    assert (
        switch.manager.get_manual_control_attributes(ENTITY_LIGHT_1)
        == LightControlAttributes.ALL
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )

    await switch.adapt_brightness_switch.async_turn_off()

    # Check that with adapt_brightness off and PAUSE_CHANGED, only color is adapted when none are manually controlled
    switch._take_over_control_mode = TakeOverControlMode.PAUSE_CHANGED
    switch.manager.set_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.NONE,
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.COLOR
    )

    # Check that with adapt_brightness off and PAUSE_CHANGED, nothing is adapted when color is manually controlled
    switch._take_over_control_mode = TakeOverControlMode.PAUSE_CHANGED
    switch.manager.set_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.COLOR,
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )

    # Check that with adapt_brightness off and PAUSE_ALL, only color is adapted when none are manually controlled
    switch._take_over_control_mode = TakeOverControlMode.PAUSE_ALL
    switch.manager.set_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.NONE,
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.COLOR
    )

    # Check that with adapt_brightness off and PAUSE_ALL, nothing is adapted when color is manually controlled
    switch._take_over_control_mode = TakeOverControlMode.PAUSE_ALL
    switch.manager.set_manual_control_attributes(
        ENTITY_LIGHT_1,
        LightControlAttributes.COLOR,
    )
    assert (
        switch.manager.get_adaption_control_attributes(switch, ENTITY_LIGHT_1)
        == LightControlAttributes.NONE
    )


async def test_apply_service(hass):
    """Test adaptive_lighting.apply service."""
    switch, (_, _, light) = await setup_lights_and_switch(hass)
    entity_id = light.entity_id
    assert entity_id not in switch.lights

    def increased_brightness():
        return max(1, (light._attr_brightness + 100) % 255)

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
                ATTR_ENTITY_ID: switch.entity_id,
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


async def test_apply_service_uses_each_switch_transition(hass):
    """Test global apply resolves omitted transition for each profile."""
    await setup_lights(hass)
    _, switch_1 = await setup_switch(
        hass,
        {
            CONF_NAME: "switch 1",
            CONF_LIGHTS: [ENTITY_LIGHT_1],
            CONF_INITIAL_TRANSITION: 3,
        },
    )
    _, switch_2 = await setup_switch(
        hass,
        {
            CONF_NAME: "switch 2",
            CONF_LIGHTS: [ENTITY_LIGHT_2],
            CONF_INITIAL_TRANSITION: 7,
        },
    )

    with (
        patch.object(switch_1, "_adapt_light", new=AsyncMock()) as adapt_1,
        patch.object(switch_2, "_adapt_light", new=AsyncMock()) as adapt_2,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_APPLY,
            {ATTR_ENTITY_ID: [switch_1.entity_id, switch_2.entity_id]},
            blocking=True,
        )
        assert adapt_1.await_args.kwargs["transition"] == 3
        assert adapt_2.await_args.kwargs["transition"] == 7

        adapt_1.reset_mock()
        adapt_2.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_APPLY,
            {
                ATTR_ENTITY_ID: [switch_1.entity_id, switch_2.entity_id],
                CONF_TRANSITION: 0,
            },
            blocking=True,
        )
        assert adapt_1.await_args.kwargs["transition"] == 0
        assert adapt_2.await_args.kwargs["transition"] == 0


async def test_switch_off_on_off(hass):
    """Test switch rapid off_on_off."""

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_1, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()

    async def update():
        await switch._update_attrs_and_maybe_adapt_lights(
            context=switch.create_context("test"),
            transition=0,
        )
        await hass.async_block_till_done()

    switch, _ = await setup_lights_and_switch(hass)

    for turn_light_state_at_end in [True, False]:
        # Turn light on
        await turn_light(True)
        # Turn light off with transition
        await turn_light(False, transition=1)

        assert not switch.manager.manual_control[ENTITY_LIGHT_1]
        # Set state to on after a second (like happens IRL)
        await asyncio.sleep(1e-3)
        hass.states.async_set(ENTITY_LIGHT_1, STATE_ON)
        # Set state to off after a second (like happens IRL)
        await asyncio.sleep(1e-3)
        hass.states.async_set(ENTITY_LIGHT_1, STATE_OFF)

        # Now we test whether the sleep task is there
        assert ENTITY_LIGHT_1 in switch.manager.sleep_tasks
        sleep_task = switch.manager.sleep_tasks[ENTITY_LIGHT_1]
        assert not sleep_task.cancelled()

        # A 'light.turn_on' event should cancel that task
        await turn_light(turn_light_state_at_end)
        await update()
        state = hass.states.get(ENTITY_LIGHT_1).state
        if turn_light_state_at_end:
            assert sleep_task.cancelled()
            assert state == STATE_ON
        else:
            assert state == STATE_OFF


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
    kwargs = {
        "light": "light.test",
        "context": Context(),
    }
    assert not _attributes_have_changed(
        old_attributes=attributes_1,
        new_attributes=attributes_1,
        **kwargs,
    )
    for key, value in attributes_2.items():
        attrs = dict(attributes_1)
        attrs[key] = value
        assert _attributes_have_changed(
            old_attributes=attributes_1,
            new_attributes=attrs,
            **kwargs,
        )
    # Test color mode switches - feature added to detect external changes
    # (e.g., when Hue scenes change light from color_temp to RGB mode)
    # See: https://github.com/basnijholt/adaptive-lighting/issues/1275
    #
    # All mode switches are now detected bidirectionally by checking original
    # attributes BEFORE conversion in _has_color_mode_changed().
    _LOGGER.debug(
        "Test switch from color_temp to rgb_color - should detect mode change",
    )
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_RGB_COLOR: (255, 166, 87)},
        **kwargs,
    )
    _LOGGER.debug(
        "Test switch from rgb_color to color_temp - should detect mode change",
    )
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_RGB_COLOR: (255, 166, 87)},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        **kwargs,
    )
    _LOGGER.debug("Test switch from color_temp to color_xy - should detect mode change")
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_XY_COLOR: (0.526, 0.387)},
        **kwargs,
    )
    _LOGGER.debug("Test switch from color_xy to color_temp - should detect mode change")
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 1, ATTR_XY_COLOR: (0.526, 0.387)},
        new_attributes={ATTR_BRIGHTNESS: 1, ATTR_COLOR_TEMP_KELVIN: 2702},
        **kwargs,
    )


async def test_state_change_handlers(hass):
    """Test AdaptiveLightingManager's EVENT_STATE_CHANGED listener.
    ======================
    Sequence of events:
    1. Transition from sleep mode to normal.
    2. Create simulated transition events for that adapt.
    3. Fire all simulated transition events.
    4. Assert all possible problems that would result.
    Also tests significant changes.
    """
    # Keep adaptive brightness distinct from the manual values 20, 40, and 50.
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {CONF_MIN_BRIGHTNESS: 50, CONF_MAX_BRIGHTNESS: 50},
    )
    context = switch.create_context("test")  # needs to be passed to update method

    # [Config options]:
    transition_used = 2
    total_events = 5

    async def set_brightness(val: int):
        # 'Unsafe' set but we know what we're doing.
        hass.states.async_set(
            ENTITY_LIGHT_1,
            "on",
            {ATTR_BRIGHTNESS: val, ATTR_SUPPORTED_FEATURES: 1},
        )
        await hass.async_block_till_done()
        # Call code in AdaptiveLightingManager
        hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "new_state": {
                    ATTR_ENTITY_ID: ENTITY_LIGHT_1,
                    "state": "on",
                    ATTR_BRIGHTNESS: val,
                },
            },
        )
        await hass.async_block_till_done()

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_1, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()

    async def update(force: bool = False):
        await switch._update_attrs_and_maybe_adapt_lights(
            context=context,
            force=force,
            transition=0,
        )
        await hass.async_block_till_done()

    # 1. Adapt to sleep without a transition.
    # Should only be one state change.
    _LOGGER.debug('test_state_change_handling: Turn on "sleep mode"')
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert switch.manager.our_last_state_on_change.get(ENTITY_LIGHT_1)
    assert len(switch.manager.our_last_state_on_change[ENTITY_LIGHT_1]) == 1
    assert not switch.manager.transition_timers.get(ENTITY_LIGHT_1)
    last_service_data = deepcopy(switch.manager.last_service_data)
    assert last_service_data.get(ENTITY_LIGHT_1)

    # 2 Adapt from sleep with a 'transition'.
    await switch.sleep_mode_switch.async_turn_off()
    await switch._update_attrs_and_maybe_adapt_lights(
        context=context,
        force=False,
        transition=0,
    )
    await hass.async_block_till_done()
    current_service_data = switch.manager.last_service_data
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
                    light,
                    "on",
                    attributes=current_service_data,
                    context=context,
                ),
            },
        )
        assert not switch.manager.transition_timers.get(light)

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
        assert switch.manager.transition_timers.get(light)
        # 2.5 Simulate a transition. There's no other way to do this in the demo.
        events = create_transition_events(
            light=light,
            state=hass.states.get(light),
            last=last_service_data[light],
            current=current_service_data[light],
            total_events=total_events,
        )
        # 3. Fire simulated events for our AdaptiveLightingManager
        for event in events:
            _LOGGER.debug("Test EVENT_STATE_CHANGED listener")
            hass.bus.async_fire(EVENT_STATE_CHANGED, event)
            await hass.async_block_till_done()
            # On real systems HA fires transition state changes every ~3 seconds.
            # asyncio.sleep(3)
    # 4. Assert the transition timer started and everything was filled.
    listener = switch.manager
    assert listener.our_last_state_on_change.get(ENTITY_LIGHT_1)
    assert len(listener.our_last_state_on_change[ENTITY_LIGHT_1]) == total_events
    assert listener.transition_timers.get(ENTITY_LIGHT_1)

    # 5. Execute some checks during a transition
    _LOGGER.debug("Test detect_non_ha_changes:")
    switch._take_over_control = True
    assert switch._take_over_control
    switch._detect_non_ha_changes = True
    assert switch._detect_non_ha_changes
    await asyncio.sleep(transition_used / 3)
    # Ensure the timer still exists
    timer = listener.transition_timers.get(ENTITY_LIGHT_1)
    assert timer
    assert timer.is_running()
    last_service_data = deepcopy(current_service_data)
    await update()
    assert not switch.manager.manual_control[ENTITY_LIGHT_1]
    await update()
    assert not switch.manager.manual_control[ENTITY_LIGHT_1]
    timer = listener.transition_timers.get(ENTITY_LIGHT_1)
    assert timer
    assert timer.is_running()
    # Ensure the light did not adapt during the transition.
    assert last_service_data == current_service_data

    # 6. Assert everything after the transition finishes.
    await asyncio.sleep(transition_used)
    assert listener.our_last_state_on_change.get(ENTITY_LIGHT_1)
    assert len(listener.our_last_state_on_change[ENTITY_LIGHT_1]) == total_events
    # Timer should be done and reset now.
    # This is the assert that I can't fix.
    timer = listener.transition_timers.get(ENTITY_LIGHT_1)
    assert not timer or not timer.is_running()

    # build last service data
    await update(force=False)

    # force=True should not reset manual control.
    await turn_light(True, brightness=40)
    await turn_light(True, brightness=20)
    await update(force=False)
    assert (
        switch.manager.manual_control[ENTITY_LIGHT_1]
        == LightControlAttributes.BRIGHTNESS
    )
    await update(force=True)
    assert (
        switch.manager.manual_control[ENTITY_LIGHT_1]
        == LightControlAttributes.BRIGHTNESS
    )

    # turn light off then on should reset manual control.
    await turn_light(False)
    await turn_light(True)
    assert not switch.manager.manual_control[ENTITY_LIGHT_1]

    await turn_light(True, brightness=50)
    _LOGGER.debug("Test: Brightness set to %s", 50)

    # On next update ENTITY_LIGHT_1 should be marked as manually controlled
    await update(force=False)
    assert switch.manager.last_service_data.get(ENTITY_LIGHT_1) is not None
    assert switch.manager.our_last_state_on_change.get(ENTITY_LIGHT_1) is not None
    assert (
        switch.manager.manual_control[ENTITY_LIGHT_1]
        == LightControlAttributes.BRIGHTNESS
    )


def test_is_our_context():
    """Test is_our_context function."""
    context = create_context(DOMAIN, "test", 0)
    assert is_our_context(context)
    assert not is_our_context(None)
    assert not is_our_context(Context())


async def test_unload_switch(hass):
    """Test removing Adaptive Lighting."""
    entry, switch = await setup_switch(hass, {})
    switch.manager.set_auto_reset_manual_control_times([ENTITY_LIGHT_1], 60)
    switch.manager.set_manual_control_attributes(ENTITY_LIGHT_1)
    timer = switch.manager.auto_reset_manual_control_timers[ENTITY_LIGHT_1]
    assert timer.is_running()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass.data
    assert not timer.is_running()


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


async def test_offset_too_large(hass):
    """Test that update fails when the sunrise offset is too large.

    A 12-hour offset causes sun events to be out of order (e.g., sunrise after sunset),
    which makes the adaptive lighting algorithm fail with a ValueError.
    """
    _, switch = await setup_switch(hass, {CONF_SUNRISE_OFFSET: 3600 * 12})
    with pytest.raises(ValueError, match=r"sun events.*not in the expected order"):
        await switch._update_attrs_and_maybe_adapt_lights(
            context=switch.create_context("test"),
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


async def test_async_update_at_interval_action(hass):
    """Test '_async_update_at_interval_action' method."""
    _, switch = await setup_switch(hass, {})
    await switch._async_update_at_interval_action()


async def test_stagger_offset_deterministic_and_bounded(hass):
    """Test switches get stable relative delays within the interval."""
    interval = datetime.timedelta(seconds=90)

    _, switch_a = await setup_switch(hass, {CONF_NAME: "switch_a"})
    _, switch_b = await setup_switch(hass, {CONF_NAME: "switch_b"})

    offset_a_1 = switch_a._stagger_offset(interval)
    offset_a_2 = switch_a._stagger_offset(interval)
    assert offset_a_1 == offset_a_2

    offset_b = switch_b._stagger_offset(interval)
    assert offset_a_1 != offset_b

    for offset in (offset_a_1, offset_b):
        assert datetime.timedelta(0) <= offset < interval


async def test_disable_cancels_pending_stagger(hass):
    """Test disabling the switch cancels delayed interval registration."""
    switch_module = "homeassistant.components.adaptive_lighting.switch"
    with (
        patch(
            f"{switch_module}.AdaptiveSwitch._stagger_offset",
            return_value=datetime.timedelta(seconds=10),
        ) as mock_offset,
        patch(
            f"{switch_module}.async_track_time_interval",
            return_value=lambda: None,
        ) as mock_track_interval,
    ):
        _, switch = await setup_switch(hass, {})
        mock_offset.return_value = datetime.timedelta(seconds=0.05)
        switch._update_time_interval_listener()
        await switch.async_turn_off()
        await asyncio.sleep(0.1)

    mock_track_interval.assert_not_called()


async def test_reconfigure_replaces_stagger_and_preserves_interval(hass):
    """Test the replacement starts at offset + interval and keeps its cadence."""
    calls: list[float] = []
    two_calls = asyncio.Event()
    loop = asyncio.get_running_loop()
    stagger = datetime.timedelta(seconds=0.2)

    async def record_interval(_now=None):
        calls.append(loop.time())
        if len(calls) == 2:
            two_calls.set()

    with patch(
        "homeassistant.components.adaptive_lighting.switch.AdaptiveSwitch._stagger_offset",
        return_value=datetime.timedelta(seconds=10),
    ) as mock_offset:
        _, switch = await setup_switch(hass, {})
        switch._interval = datetime.timedelta(0)
        mock_offset.return_value = stagger
        effective_interval = (
            switch._interval
            + datetime.timedelta(milliseconds=switch._send_split_delay)
            + datetime.timedelta(seconds=0.5)
        )

        with patch.object(
            switch,
            "_async_update_at_interval_action",
            side_effect=record_interval,
        ):
            switch._update_time_interval_listener()
            await asyncio.sleep(0.02)

            replacement_started = loop.time()
            switch._update_time_interval_listener()
            await asyncio.wait_for(two_calls.wait(), timeout=2)
            await switch.async_turn_off()

    first_delay = calls[0] - replacement_started
    interval_seconds = effective_interval.total_seconds()
    expected_first_delay = interval_seconds + stagger.total_seconds()
    assert expected_first_delay - 0.1 <= first_delay < expected_first_delay + 0.5
    assert interval_seconds - 0.1 <= calls[1] - calls[0] < interval_seconds + 0.5


@pytest.mark.parametrize("separate_turn_on_commands", (True, False))
async def test_separate_turn_on_commands(hass, separate_turn_on_commands):
    """Test 'separate_turn_on_commands' argument."""
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {
            CONF_SEPARATE_TURN_ON_COMMANDS: separate_turn_on_commands,
            # Keep normal brightness distinct from sleep mode at any time of day.
            CONF_MIN_BRIGHTNESS: 50,
            CONF_MAX_BRIGHTNESS: 50,
        },
    )
    # We just turn sleep mode on and off which should change the
    # brightness and color. We don't test whether the number are exactly
    # what we expect because we do this in other tests already, we merely
    # check whether the brightness and color_temp change.
    context = switch.create_context("test")  # needs to be passed to update method
    brightness = light.brightness
    color_temp = light.color_temp_kelvin
    await switch.sleep_mode_switch.async_turn_on()
    await switch._update_attrs_and_maybe_adapt_lights(context=context)
    await hass.async_block_till_done()

    # TODO: figure out why `light.brightness` is not updating
    attrs = hass.states.get(light.entity_id).attributes
    sleep_brightness = attrs["brightness"]
    sleep_color_temp = attrs["color_temp_kelvin"]

    assert sleep_brightness != brightness
    assert sleep_color_temp != color_temp

    await switch.sleep_mode_switch.async_turn_off()
    await switch._update_attrs_and_maybe_adapt_lights(context=context)
    await hass.async_block_till_done()

    attrs = hass.states.get(light.entity_id).attributes
    brightness = attrs["brightness"]
    color_temp = attrs["color_temp_kelvin"]

    assert sleep_brightness != brightness
    assert sleep_color_temp != color_temp


def mock_area_registry(
    hass: HomeAssistant,
) -> ar.AreaRegistry:
    """Mock the Area Registry."""
    area = ar.AreaEntry(
        aliases=set(),
        floor_id="test-floor",
        humidity_entity_id=None,
        icon=None,
        id="test-area",
        name="Test Area",
        picture=None,
        temperature_entity_id=None,
    )
    return mock_ha_area_registry(hass, {area.id: area})


async def test_light_switch_in_specific_area(hass):
    switch, (light, *_) = await setup_lights_and_switch(hass)

    mock_area_registry(hass)

    entity = entity_registry.async_get(hass).async_get_or_create(
        LIGHT_DOMAIN,
        "template",
        light.unique_id,
    )
    entity = entity_registry.async_get(hass).async_update_entity(
        entity.entity_id,
        area_id="test-area",
    )
    _LOGGER.debug("test-area entity: %s", entity)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_AREA_ID: entity.area_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert light.entity_id in switch.manager.last_service_data
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_AREA_ID: entity.area_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    _LOGGER.debug(
        "switch.manager.last_service_data: %s",
        switch.manager.last_service_data,
    )
    assert light.entity_id not in switch.manager.last_service_data


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
                ATTR_ENTITY_ID: switch.entity_id,
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
        match="value must be at most 100",
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

    # testing with "configuration" and setting a new value
    await change_switch_settings(
        **{CONF_USE_DEFAULTS: "configuration", CONF_MIN_COLOR_TEMP: 3000},
    )
    assert switch._sun_light_settings.min_color_temp == 3000

    # testing with "configuration" should revert back to 2500
    await change_switch_settings(**{CONF_USE_DEFAULTS: "configuration"})
    assert switch._sun_light_settings.min_color_temp == 2500


@pytest.mark.parametrize("target", ["entity", "area", "device", "all"])
async def test_change_switch_settings_entity_targets(hass, device_registry, target):
    """Test settings changes through Home Assistant entity targets."""
    _, switch = await setup_switch(hass, {})
    mock_area_registry(hass)
    registry_entry = entity_registry.async_get(hass).async_get(switch.entity_id)
    assert registry_entry is not None
    assert registry_entry.device_id is not None
    device_registry.async_update_device(
        registry_entry.device_id,
        area_id="test-area",
    )
    service_data = {
        "entity": {ATTR_ENTITY_ID: switch.entity_id},
        "area": {ATTR_AREA_ID: "test-area"},
        "device": {ATTR_DEVICE_ID: registry_entry.device_id},
        "all": {ATTR_ENTITY_ID: "all"},
    }[target]

    with patch.object(
        switch,
        "_set_changeable_settings",
        wraps=switch._set_changeable_settings,
    ) as set_settings:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CHANGE_SWITCH_SETTINGS,
            {**service_data, CONF_MAX_BRIGHTNESS: 50},
            blocking=True,
        )

    set_settings.assert_called_once()
    assert switch._sun_light_settings.max_brightness == 50


async def test_change_switch_settings_ignores_unknown_entity(hass):
    """Test an unknown entity target does not change a loaded profile."""
    _, switch = await setup_switch(hass, {})

    with patch.object(switch, "_set_changeable_settings") as set_settings:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CHANGE_SWITCH_SETTINGS,
            {
                ATTR_ENTITY_ID: "switch.does_not_exist",
                CONF_MAX_BRIGHTNESS: 50,
            },
            blocking=True,
        )

    set_settings.assert_not_called()


async def test_change_switch_settings_checks_entity_permissions(
    hass,
    hass_read_only_user,
):
    """Test settings changes require permission to control the target entity."""
    _, switch = await setup_switch(hass, {})

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CHANGE_SWITCH_SETTINGS,
            {
                ATTR_ENTITY_ID: switch.entity_id,
                CONF_MAX_BRIGHTNESS: 50,
            },
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )

    assert switch._sun_light_settings.max_brightness == DEFAULT_MAX_BRIGHTNESS


async def test_cancellable_service_calls_task(hass):
    """Test the creation and execution of the task that wraps adaptation service calls."""
    light, *_ = await setup_lights(hass)
    _, switch = await setup_switch(hass, {CONF_SEPARATE_TURN_ON_COMMANDS: True})
    context = switch.create_context("test")

    assert switch.manager.adaptation_tasks_color.get(light.entity_id) is None

    service_data = {
        ATTR_BRIGHTNESS: 10,
        ATTR_COLOR_TEMP_KELVIN: 10,
        ATTR_ENTITY_ID: light.entity_id,
    }
    adaptation_data = AdaptationData(
        light.entity_id,
        context,
        0,
        _create_service_call_data_iterator(hass, [service_data], False),
        force=False,
        max_length=1,
        attributes=LightControlAttributes.ALL,
    )
    await switch.execute_cancellable_adaptation_calls(adaptation_data)

    task = switch.manager.adaptation_tasks_brightness.get(light.entity_id)
    task2 = switch.manager.adaptation_tasks_color.get(light.entity_id)
    assert task is task2
    assert task is not None
    assert task.done()


async def test_service_calls_task_cancellation(hass):
    """Tests if the task that wraps ongoing adaptation service calls gets cancelled."""
    _, switch = await setup_switch(hass, {})
    entity_id = "test_id"

    task = asyncio.ensure_future(asyncio.sleep(1))
    switch.manager.adaptation_tasks_brightness[entity_id] = task

    switch.manager.cancel_ongoing_adaptation_calls(entity_id)

    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert task.cancelled()


async def _turn_on_and_track_event_contexts(
    hass: HomeAssistant,
    context_id: str | Context,
    entity_id,
    return_full_events: bool = False,
):
    context = context_id if isinstance(context_id, Context) else Context(id=context_id)
    event_context_ids = []
    events = []

    async def turn_on_off_event_listener(event: Event) -> None:
        event_context_ids.append(event.context.id)
        events.append(event)

    hass.bus.async_listen(EVENT_CALL_SERVICE, turn_on_off_event_listener)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
        context=context,
    )
    await hass.async_block_till_done()
    if return_full_events:
        return events
    return event_context_ids


async def _admin_context(hass: HomeAssistant, context_id: str) -> Context:
    """Create a user-originated context accepted by entity service checks."""
    user = await hass.auth.async_create_user(context_id, group_ids=[GROUP_ID_ADMIN])
    return Context(
        id=context_id,
        parent_id="automation_origin",
        user_id=user.id,
    )


async def test_apply_service_context_links_to_origin(hass):
    """The apply service links its light call to the originating service call."""
    switch, (_, _, light) = await setup_lights_and_switch(hass)
    origin = await _admin_context(hass, "apply_origin")
    events: list[Event] = []

    async def listener(event: Event) -> None:
        if (
            event.data.get("domain") == LIGHT_DOMAIN
            and event.data.get("service") == SERVICE_TURN_ON
        ):
            events.append(event)

    remove_listener = hass.bus.async_listen(EVENT_CALL_SERVICE, listener)
    try:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_APPLY,
            {
                ATTR_ENTITY_ID: switch.entity_id,
                CONF_LIGHTS: [light.entity_id],
                CONF_TURN_ON_LIGHTS: True,
            },
            blocking=True,
            context=origin,
        )
        await hass.async_block_till_done()
    finally:
        remove_listener()

    assert len(events) == 1
    assert events[0].context.parent_id == origin.id
    assert events[0].context.user_id is None


async def test_single_light_intercept_keeps_origin_context(hass):
    """A directly intercepted call keeps the original context unchanged."""
    await setup_lights_and_switch(hass, {CONF_INTERCEPT: True}, True)
    origin = await _admin_context(hass, "single_intercept_origin")

    events = await _turn_on_and_track_event_contexts(
        hass,
        origin,
        ENTITY_LIGHT_3,
        return_full_events=True,
    )

    assert len(events) == 1
    assert events[0].context.id == origin.id
    assert events[0].context.parent_id == origin.parent_id
    assert events[0].context.user_id == origin.user_id


async def test_multi_profile_intercept_context_links_to_origin(hass):
    """A secondary profile adaptation links its new call to the origin."""
    lights, _, _ = await setup_proactive_multiple_lights_two_switches(hass)
    origin = await _admin_context(hass, "multi_profile_origin")

    events = await _turn_on_and_track_event_contexts(
        hass,
        origin,
        lights[:2],
        return_full_events=True,
    )
    secondary_events = [event for event in events if ":ntrc:" in event.context.id]

    assert len(secondary_events) == 1
    assert secondary_events[0].context.parent_id == origin.id
    assert secondary_events[0].context.user_id is None


async def test_skipped_light_context_links_to_origin(hass):
    """A split call for an unmanaged light links its new call to the origin."""
    lights, _, _ = await setup_proactive_multiple_lights_two_switches(hass)
    origin = await _admin_context(hass, "skipped_light_origin")

    events = await _turn_on_and_track_event_contexts(
        hass,
        origin,
        [lights[0], lights[2]],
        return_full_events=True,
    )
    skipped_events = [event for event in events if ":skpp:" in event.context.id]

    assert len(skipped_events) == 1
    assert skipped_events[0].context.parent_id == origin.id
    assert skipped_events[0].context.user_id is None


def _mock_sun_light_settings(switch: AdaptiveSwitch, settings: dict[str, Any]):
    sun_light_settings_mock = Mock()
    sun_light_settings_mock.get_settings = Mock(return_value=settings)
    switch._sun_light_settings = sun_light_settings_mock


async def test_proactive_adaptation(hass):
    """Validate that a proactive adaptation updates the original service call."""
    switch, _ = await setup_lights_and_switch(hass, {CONF_INTERCEPT: True}, True)

    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )

    event_context_ids = await _turn_on_and_track_event_contexts(
        hass,
        "test_context",
        ENTITY_LIGHT_3,
    )

    # Expect a single service call
    assert len(event_context_ids) == 1
    assert event_context_ids == ["test_context"]

    # Expect adapted light state
    state = hass.states.get(ENTITY_LIGHT_3)
    # Sun light settings use %, state only contains absolute
    assert state.attributes[ATTR_BRIGHTNESS] == 171  # == 67%
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 3448


async def test_proactive_adaptation_with_separate_commands(hass):
    """Validate that a split proactive adaptation yields one additional service call."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {
            CONF_INTERCEPT: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
        },
        True,
    )

    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )

    origin = await _admin_context(hass, "separate_commands_origin")
    events = await _turn_on_and_track_event_contexts(
        hass,
        origin,
        ENTITY_LIGHT_3,
        return_full_events=True,
    )
    # Wait for all adaptation tasks to complete
    await asyncio.gather(*switch.manager.adaptation_tasks)
    await hass.async_block_till_done()
    event_context_ids = [event.context.id for event in events]

    # Expect two service calls
    assert len(event_context_ids) == 2, event_context_ids
    assert event_context_ids[0] == origin.id
    assert is_our_context_id(event_context_ids[1])
    assert events[1].context.parent_id == origin.id
    assert events[1].context.user_id is None

    # Expect adapted light state
    state = hass.states.get(ENTITY_LIGHT_3)
    assert state.attributes[ATTR_BRIGHTNESS] == 171
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 3448


async def test_proactive_adaptation_toggle(hass):
    """Validate that a proactive adaptation updates service calls which toggle a light on,
    but not those which toggle off.

    This test is based on the fact that contexts of proactive adaptations are recorded.
    """
    switch, _ = await setup_lights_and_switch(hass, {CONF_INTERCEPT: True}, True)

    # Toggle ON
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TOGGLE,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_3},
        blocking=True,
        context=Context(id="test1"),
    )

    assert switch.manager.is_proactively_adapting("test1")

    # Toggle OFF
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TOGGLE,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_3},
        blocking=True,
        context=Context(id="test2"),
    )

    assert not switch.manager.is_proactively_adapting("test2")


async def test_proactive_adaptation_transition_override(hass):
    """Validate that transitions in service calls are preferred over the default transition."""
    switch, (_, _, light3) = await setup_lights_and_switch(
        hass,
        {
            CONF_INTERCEPT: True,
            CONF_INITIAL_TRANSITION: 123,
        },
        True,
    )
    with patch.object(
        light3,
        "async_turn_on",
        wraps=light3.async_turn_on,
    ) as patched_async_turn_on:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_3},
            blocking=True,
        )

        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_3, ATTR_TRANSITION: 456},
            blocking=True,
        )
        await hass.async_block_till_done()

    # Assert that default is used when no transition is specified in service call
    assert patched_async_turn_on.call_args_list, patched_async_turn_on.call_args_list
    kwargs = patched_async_turn_on.call_args_list[0].kwargs
    assert set({ATTR_TRANSITION: 123}.items()).issubset(kwargs.items())

    # Assert that specified service call transition takes precedence over default
    kwargs = patched_async_turn_on.call_args_list[1].kwargs
    assert set({ATTR_TRANSITION: 456}.items()).issubset(kwargs.items())

    # Cleanup
    switch.manager.cancel_ongoing_adaptation_calls(ENTITY_LIGHT_3)


async def setup_proactive_multiple_lights_two_switches(hass):
    await setup_lights(hass)
    # Setup switches
    lights = [
        ENTITY_LIGHT_1,
        ENTITY_LIGHT_2,
        ENTITY_LIGHT_3,
    ]
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: lights},
        blocking=True,
    )
    defaults = {
        CONF_SUNRISE_TIME: datetime.time(SUNRISE.hour),
        CONF_SUNSET_TIME: datetime.time(SUNSET.hour),
        CONF_INITIAL_TRANSITION: 0,
        CONF_TRANSITION: 0,
        CONF_DETECT_NON_HA_CHANGES: True,
        CONF_PREFER_RGB_COLOR: False,
        CONF_MIN_COLOR_TEMP: 2500,  # to not coincide with sleep_color_temp}
        CONF_INTERCEPT: True,
    }
    _, switch1 = await setup_switch(
        hass,
        {CONF_NAME: "switch1", CONF_LIGHTS: [ENTITY_LIGHT_1], **defaults},
    )
    _, switch2 = await setup_switch(
        hass,
        {CONF_NAME: "switch2", CONF_LIGHTS: [ENTITY_LIGHT_2], **defaults},
    )
    assert hass.states.get(switch1.entity_id).state == STATE_ON
    assert hass.states.get(switch2.entity_id).state == STATE_ON
    assert all(hass.states.get(light).state == STATE_OFF for light in lights)
    return lights, switch1, switch2


async def test_proactive_multiple_lights_all_at_once(hass):
    """Create switch and demo lights."""
    lights, switch1, switch2 = await setup_proactive_multiple_lights_two_switches(hass)
    _LOGGER.debug("Start test_proactive_multiple_lights_all_at_once")
    # Setup demo lights and turn on
    events = await _turn_on_and_track_event_contexts(
        hass,
        "test1",
        lights,
        return_full_events=True,
    )
    assert len(events) == 3, events

    # Original turn_on call that is intercepted
    assert events[0].context.id == "test1"
    assert events[0].data["service_data"][ATTR_ENTITY_ID] == lights

    # The `has_intercepted` path
    assert events[1].data["service_data"][ATTR_ENTITY_ID] == ENTITY_LIGHT_2
    assert ":ntrc:" in events[1].context.id

    # The skipped lights, the one not in a switch
    assert events[2].data["service_data"][ATTR_ENTITY_ID] == [ENTITY_LIGHT_3]
    assert ":skpp:" in events[2].context.id

    assert switch1.manager.is_proactively_adapting("test1")
    assert switch2.manager.is_proactively_adapting("test1")

    await hass.async_block_till_done()

    assert all(hass.states.get(light).state == STATE_ON for light in lights)

    # Turn on second time even though already on
    events = await _turn_on_and_track_event_contexts(
        hass,
        "test2",
        lights,
        return_full_events=True,
    )
    assert len(events) == 1, events
    assert events[0].context.id == "test2"


async def test_proactive_multiple_lights_turn_on_non_managed_light(hass):
    """Create switch and demo lights."""
    lights, switch1, switch2 = await setup_proactive_multiple_lights_two_switches(hass)
    turn_ons = await _turn_on_and_track_event_contexts(hass, "test1", lights)
    assert len(turn_ons) == 3, turn_ons
    await hass.async_block_till_done()
    assert all(hass.states.get(light).state == STATE_ON for light in lights)

    # Turn off ENTITY_LIGHT_3 (which is not in a switch), leaving the other two on
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_3},
        blocking=True,
        context=Context(id="test2"),
    )

    # Now turn on all lights again, which means the code gets to "if skipped: if not has_intercepted:"
    turn_ons = await _turn_on_and_track_event_contexts(hass, "test2", ENTITY_LIGHT_3)
    assert len(turn_ons) == 1, turn_ons


async def test_proactive_multiple_lights_turn_on_managed_lights_only(hass):
    """Create switch and demo lights."""
    lights, switch1, switch2 = await setup_proactive_multiple_lights_two_switches(hass)
    _LOGGER.debug("Start test_proactive_multiple_lights_all_at_once")
    # Setup demo lights and turn on
    events = await _turn_on_and_track_event_contexts(
        hass,
        "test1",
        lights[:-1],
        return_full_events=True,
    )
    assert len(events) == 2, events

    # Original turn_on call that is intercepted
    assert events[0].context.id == "test1"
    assert events[0].data["service_data"][ATTR_ENTITY_ID] == lights[:-1]

    # The `has_intercepted` path
    assert events[1].data["service_data"][ATTR_ENTITY_ID] == ENTITY_LIGHT_2
    assert ":ntrc:" in events[1].context.id
    assert ATTR_BRIGHTNESS in events[1].data["service_data"]


async def test_proactive_multiple_lights_one_switch_and_one_skipped(hass):
    """Create switch and demo lights."""
    lights, switch1, switch2 = await setup_proactive_multiple_lights_two_switches(hass)
    two_lights = [lights[0], lights[-1]]
    _LOGGER.debug("Start test_proactive_multiple_lights_all_at_once")
    # Setup demo lights and turn on
    events = await _turn_on_and_track_event_contexts(
        hass,
        "test1",
        two_lights,
        return_full_events=True,
    )
    assert len(events) == 2, events

    # Original turn_on call that is intercepted
    assert events[0].context.id == "test1"
    assert events[0].data["service_data"][ATTR_ENTITY_ID] == two_lights

    # The skipped lights, the one not in a switch
    assert events[1].data["service_data"][ATTR_ENTITY_ID] == [ENTITY_LIGHT_3]
    assert ":skpp:" in events[1].context.id

    assert switch1.manager.is_proactively_adapting("test1")
    assert switch2.manager.is_proactively_adapting("test1")

    await hass.async_block_till_done()

    assert all(hass.states.get(light).state == STATE_ON for light in two_lights)


async def test_two_switches_for_single_light(hass):
    """Test the case where someone has two switches for a single light.

    One switch for brightness and another for color.
    """
    extra_conf = {CONF_INTERCEPT: True}
    switch1, (light1, *_) = await setup_lights_and_switch(
        hass,
        extra_conf | {CONF_NAME: "switch1"},
        all_lights=True,
    )
    switch2, (light2, *_) = await setup_lights_and_switch(
        hass,
        extra_conf | {CONF_NAME: "switch2"},
        all_lights=True,
    )
    assert light1.entity_id == light2.entity_id

    # One switch controls brightness the other color
    await switch1.adapt_color_switch.async_turn_off()
    await switch2.adapt_brightness_switch.async_turn_off()

    assert switch1.adapt_brightness_switch.is_on
    assert switch2.adapt_color_switch.is_on

    async def turn_light(state, **kwargs):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON if state else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_1, **kwargs},
            blocking=True,
        )
        await hass.async_block_till_done()
        _LOGGER.debug("Turn light %s, to %s", state, kwargs)

    def increased_brightness():
        return (light1._attr_brightness + 100) % 255

    def increased_color_temp():
        return max(
            (light1._attr_color_temp + 100) % light1.max_color_temp_kelvin,
            light1.min_color_temp_kelvin,
        )

    assert light1.is_on
    await turn_light(True, brightness=increased_brightness())
    await turn_light(True, color_temp_kelvin=increased_color_temp())

    attrs = hass.states.get(light1.entity_id).attributes
    before_brightness = attrs[ATTR_BRIGHTNESS]
    before_color_temp = attrs[ATTR_COLOR_TEMP_KELVIN]

    # Turn off "light1"
    await turn_light(False)

    # Turn on "light1"
    await turn_light(True)

    # Assert that the brightness and color temp have changed
    attrs = hass.states.get(light1.entity_id).attributes
    after_brightness = attrs[ATTR_BRIGHTNESS]
    after_color_temp = attrs[ATTR_COLOR_TEMP_KELVIN]
    assert before_brightness != after_brightness
    assert before_color_temp != after_color_temp


async def test_adapt_until_sleep_and_rgb_colors(hass):
    """Test setting up the Adaptive Lighting switches with different timezones.

    Also test the (sleep) brightness and color temperature settings.
    """
    lat, long, timezone = (32.87336, -117.22743, "US/Pacific")
    await async_process_ha_core_config(
        hass,
        {"latitude": lat, "longitude": long, "time_zone": timezone, "country": "US"},
    )
    switch, lights = await setup_lights_and_switch(
        hass,
        {
            CONF_SUNRISE_TIME: datetime.time(SUNRISE.hour),
            CONF_SUNSET_TIME: datetime.time(SUNSET.hour),
            CONF_ADAPT_UNTIL_SLEEP: True,
            CONF_SLEEP_RGB_OR_COLOR_TEMP: "rgb_color",
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
        with patch(
            "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
            return_value=time,
        ):
            await switch._update_attrs_and_maybe_adapt_lights(context=context)
            await hass.async_block_till_done()

    # At sunset the brightness should be max and color_temp at the smallest value
    await patch_time_and_update(sunset)
    assert not switch._settings["force_rgb_color"]
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == min_color_temp

    # One hour before sunset the brightness should be max and color_temp
    # not at the smallest value yet.
    await patch_time_and_update(before_sunset)
    assert not switch._settings["force_rgb_color"]
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] > min_color_temp
    assert "color_temp_kelvin" in switch.manager.last_service_data[ENTITY_LIGHT_1]

    # One hour after sunset the brightness should be down and use RGB
    await patch_time_and_update(after_sunset)
    assert switch._settings["force_rgb_color"]
    assert switch._settings[ATTR_BRIGHTNESS_PCT] < DEFAULT_MAX_BRIGHTNESS
    assert "rgb_color" in switch.manager.last_service_data[ENTITY_LIGHT_1]

    # At sunrise the brightness should be max and use Kelvin
    await patch_time_and_update(sunrise)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] == min_color_temp
    assert "color_temp_kelvin" in switch.manager.last_service_data[ENTITY_LIGHT_1]

    # One hour before sunrise the brightness should smaller than max
    # and use RGB
    await patch_time_and_update(before_sunrise)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] < DEFAULT_MAX_BRIGHTNESS
    assert "rgb_color" in switch.manager.last_service_data[ENTITY_LIGHT_1]

    # One hour after sunrise the brightness should be up and it should use Kelvin
    await patch_time_and_update(after_sunrise)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_MAX_BRIGHTNESS
    assert switch._settings["color_temp_kelvin"] > min_color_temp
    assert "color_temp_kelvin" in switch.manager.last_service_data[ENTITY_LIGHT_1]

    # Turn on sleep mode which make the brightness and color_temp
    # deterministic regardless of the time
    await switch.sleep_mode_switch.async_turn_on()
    await switch._update_attrs_and_maybe_adapt_lights(context=context)
    assert switch._settings[ATTR_BRIGHTNESS_PCT] == DEFAULT_SLEEP_BRIGHTNESS
    assert switch._settings["rgb_color"] == DEFAULT_SLEEP_RGB_COLOR


def test_lerp_color_hsv():
    assert lerp_color_hsv((255, 0, 0), (0, 255, 0), 0) == (255, 0, 0)
    assert lerp_color_hsv((255, 0, 0), (0, 255, 0), 1) == (0, 255, 0)
    assert lerp_color_hsv((255, 0, 0), (0, 255, 0), 0.5) == (255, 255, 0)
    assert lerp_color_hsv((0, 0, 255), (255, 255, 255), 0.5) == (128, 255, 128)

    # Tests that the interpolation is consistent
    for t in [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]:
        color = lerp_color_hsv((255, 0, 0), (0, 255, 0), t)
        inverted_color = lerp_color_hsv((0, 255, 0), (255, 0, 0), 1 - t)
        assert color == inverted_color

    with pytest.raises(AssertionError):
        lerp_color_hsv((255, 0, 0), (0, 255, 0), 1.1)


async def test_expand_light_groups_waits_for_group_state(hass):
    """Test expansion waits until a light group's state is available."""
    await setup_switch(hass, {})
    group = "light.pending_group"
    members = ["light.light_1", "light.light_2"]

    assert _expand_light_groups(hass, [group]) == [group]

    hass.states.async_set(group, STATE_ON, {ATTR_ENTITY_ID: members})

    assert _expand_light_groups(hass, [group]) == members


@pytest.mark.parametrize("proactive_service_call_adaptation", [True, False])
@pytest.mark.parametrize("take_over_control", [True, False])
@pytest.mark.parametrize("multi_light_intercept", [True, False])
async def test_light_group(
    hass,
    proactive_service_call_adaptation,
    take_over_control,
    multi_light_intercept,
    cleanup,
):
    lights = await setup_lights(hass, with_group=True)
    all_entity_ids = [light.entity_id for light in lights]
    entity_ids = all_entity_ids[:3]  # the last two are in the group
    entity_ids.append("light.light_group")
    _, switch = await setup_switch(
        hass,
        {
            CONF_LIGHTS: entity_ids,
            CONF_INTERCEPT: proactive_service_call_adaptation,
            CONF_TAKE_OVER_CONTROL: take_over_control,
            CONF_MULTI_LIGHT_INTERCEPT: multi_light_intercept,
        },
    )
    await hass.async_block_till_done()
    assert switch.is_on
    assert all(eid in switch.lights for eid in all_entity_ids)

    # Set the brightness of the group twice, once to turn it on and once to
    # trigger manual control
    for _ in range(2):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.light_group", ATTR_BRIGHTNESS_PCT: 50},
            blocking=True,
        )
        await hass.async_block_till_done()

    await switch._update_attrs_and_maybe_adapt_lights(
        context=switch.create_context("test"),
    )
    await hass.async_block_till_done()

    if take_over_control:
        assert switch.manager.manual_control["light.light_4"]
        assert switch.manager.manual_control["light.light_5"]
    else:
        assert not switch.manager.manual_control["light.light_4"]
        assert not switch.manager.manual_control["light.light_5"]

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "light.light_group"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert not switch.manager.manual_control["light.light_4"]
    assert not switch.manager.manual_control["light.light_5"]
    events = await _turn_on_and_track_event_contexts(
        hass,
        "testing",
        "light.light_group",
        return_full_events=True,
    )
    if proactive_service_call_adaptation and multi_light_intercept:
        await asyncio.gather(*switch.manager.adaptation_tasks)
        # Both lights should be adapted via interception, so with the original context
        # [
        #     "testing",  # original call light 4
        #     "testing",  # original call light 5
        # ]

        assert events[0].data["service_data"][ATTR_ENTITY_ID] == "light.light_group"
        assert events[0].context.id == "testing"
        assert events[1].data["service_data"][ATTR_ENTITY_ID] == [
            "light.light_4",
            "light.light_5",
        ]
        assert events[1].context.id == "testing"
    else:
        assert events[0].data["service_data"][ATTR_ENTITY_ID] == "light.light_group"
        assert events[0].context.id == "testing"
        assert events[1].data["service_data"][ATTR_ENTITY_ID] == [
            "light.light_4",
            "light.light_5",
        ]
        assert events[1].context.id == "testing"
        e1 = events[2].data["service_data"][ATTR_ENTITY_ID]
        e2 = events[3].data["service_data"][ATTR_ENTITY_ID]
        assert (e1 == "light.light_4" and e2 == "light.light_5") or (
            e1 == "light.light_5" and e2 == "light.light_4"
        )
        assert ":lght:" in events[2].context.id
        assert ":lght:" in events[3].context.id
        assert len(events) == 4
        assert not switch.manager.is_proactively_adapting(events[0].context.id)
        assert not switch.manager.is_proactively_adapting(events[1].context.id)

    # Turn off all lights, and then turn on all lights
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: all_entity_ids},
        blocking=True,
    )
    await hass.async_block_till_done()

    # This turns on light_1, light_2, light_3, light_group (which is light_4 and light_5)
    # This should result in the intercepted adaptation of light_1, light_2, light_3
    # and skip the light_group first. Then on a second light.turn_on where the
    # light_group is expanded, with a :skpp: context_id, this goes trhough another iteration,
    # and then the light_group is adapted.
    events = await _turn_on_and_track_event_contexts(
        hass,
        "testing",
        entity_ids,
        return_full_events=True,
    )
    if proactive_service_call_adaptation and multi_light_intercept:
        await asyncio.gather(*switch.manager.adaptation_tasks)
        # Original call
        assert events[0].data["service_data"][ATTR_ENTITY_ID] == [
            "light.light_1",
            "light.light_2",
            "light.light_3",
            "light.light_group",
        ]
        assert events[0].context.id == "testing"
        # Skipped call with light_group
        assert events[1].data["service_data"][ATTR_ENTITY_ID] == ["light.light_group"]
        assert ":skpp:" in events[1].context.id
        # HA automatically forwarded call with light_group expanded with same context
        assert events[2].data["service_data"][ATTR_ENTITY_ID] == [
            "light.light_4",
            "light.light_5",
        ]
        assert ":skpp:" in events[2].context.id
        assert len(events) == 3


def _state_changed_event(entity_id: str, ts: float, context: Context) -> Event:
    return Event(
        EVENT_STATE_CHANGED,
        {"entity_id": entity_id},
        time_fired_timestamp=ts,
        context=context,
    )


def _turn_on_service_event(entity_ids: list[str], ts: float, context: Context) -> Event:
    return Event(
        EVENT_CALL_SERVICE,
        {
            "domain": LIGHT_DOMAIN,
            "service": SERVICE_TURN_ON,
            "service_data": {ATTR_ENTITY_ID: entity_ids},
        },
        time_fired_timestamp=ts,
        context=context,
    )


async def test_just_turned_off_group_context_reuse(hass, cleanup):
    """Group 'off' → 'on' with a reused 'turn_off' context must still adapt.

    When a member of a light group is turned on (e.g., by a motion sensor
    automation) while the group is off, the group turns on as a side effect,
    but Home Assistant may reuse the context of the earlier 'turn_off' call
    for the group's state change. `just_turned_off` used to treat this as a
    polling artifact and cancel adaptation.

    Regression test for https://github.com/basnijholt/adaptive-lighting/issues/1378
    """
    await setup_lights(hass, with_group=True)
    _, switch = await setup_switch(hass, {CONF_LIGHTS: ["light.light_group"]})
    await hass.async_block_till_done()
    manager = switch.manager

    group = "light.light_group"
    member = "light.light_4"
    now = dt_util.utcnow().timestamp()
    turn_off_context = Context()

    # The group was turned off 2 seconds ago...
    manager.on_to_off_event[group] = _state_changed_event(
        group,
        now - 2,
        turn_off_context,
    )
    # ...then an automation turned on a member light with a fresh context...
    manager.turn_on_event[member] = _turn_on_service_event(
        [member],
        now - 0.5,
        Context(),
    )
    # ...which turned the group back on, but HA reused the old turn_off context.
    manager.off_to_on_event[group] = _state_changed_event(
        group,
        now,
        turn_off_context,
    )

    # The member's turn_on explains the group's turn-on: adaptation must proceed.
    assert not await manager.just_turned_off(group)

    # A member turn_on from *before* the group was turned off does not explain
    # the group's turn-on: this must still be treated as a polling artifact.
    manager.turn_on_event[member] = _turn_on_service_event(
        [member],
        now - 10,
        Context(),
    )
    assert await manager.just_turned_off(group)

    # Without any member turn_on event, the matching context IDs must still be
    # treated as a polling artifact.
    del manager.turn_on_event[member]
    assert await manager.just_turned_off(group)


async def test_just_turned_off_same_automation_context(hass, cleanup):
    """'turn_off' and 'turn_on' from one automation share a context.

    An automation calling 'light.turn_off' and later 'light.turn_on' reuses
    its own context for both service calls, so the 'on' → 'off' and
    'off' → 'on' state changes have matching context IDs. The turn_on service
    call must take precedence over the matching-context polling-artifact check.
    """
    await setup_lights(hass)
    _, switch = await setup_switch(hass, {CONF_LIGHTS: [ENTITY_LIGHT_1]})
    await hass.async_block_till_done()
    manager = switch.manager

    now = dt_util.utcnow().timestamp()
    automation_context = Context()

    manager.on_to_off_event[ENTITY_LIGHT_1] = _state_changed_event(
        ENTITY_LIGHT_1,
        now - 2,
        automation_context,
    )
    manager.turn_on_event[ENTITY_LIGHT_1] = _turn_on_service_event(
        [ENTITY_LIGHT_1],
        now - 0.5,
        automation_context,
    )
    manager.off_to_on_event[ENTITY_LIGHT_1] = _state_changed_event(
        ENTITY_LIGHT_1,
        now,
        automation_context,
    )
    assert not await manager.just_turned_off(ENTITY_LIGHT_1)

    # A stale turn_on with an unrelated context does not explain the
    # 'off' → 'on' state change: still a polling artifact.
    manager.turn_on_event[ENTITY_LIGHT_1] = _turn_on_service_event(
        [ENTITY_LIGHT_1],
        now - 10,
        Context(),
    )
    assert await manager.just_turned_off(ENTITY_LIGHT_1)

    # A stale turn_on *sharing the automation's context* but fired before the
    # 'on' → 'off' state change (i.e., 'turn_on' → delay → 'turn_off' in one
    # automation run) does not explain the 'off' → 'on' state change either:
    # `turn_on_event` entries are never cleaned up, so without the time bounds
    # this would defeat the polling-artifact detection.
    manager.turn_on_event[ENTITY_LIGHT_1] = _turn_on_service_event(
        [ENTITY_LIGHT_1],
        now - 10,
        automation_context,
    )
    assert await manager.just_turned_off(ENTITY_LIGHT_1)


async def test_just_turned_off_group_context_reuse_end_to_end(hass, cleanup):
    """Drive the issue #1378 scenario through the real event bus listeners.

    Unlike `test_just_turned_off_group_context_reuse`, which calls
    `just_turned_off` directly, this test fires the service and state-changed
    events on the bus. Light groups are normally expanded out of
    `manager.lights`, but they can remain tracked in real setups (e.g., when a
    group is nested inside another configured group or is unavailable during
    setup), which is the configuration under which issue #1378 was reported.
    """
    await setup_lights(hass, with_group=True)
    _, switch = await setup_switch(hass, {CONF_LIGHTS: ["light.light_group"]})
    await hass.async_block_till_done()
    manager = switch.manager

    group = "light.light_group"
    member = "light.light_4"
    assert member in manager.lights
    # Simulate a setup in which the group entity itself remains tracked.
    manager.lights.add(group)

    turn_off_context = Context()
    # The group was turned off...
    hass.bus.async_fire(
        EVENT_STATE_CHANGED,
        {
            "entity_id": group,
            "old_state": State(group, STATE_ON),
            "new_state": State(group, STATE_OFF),
        },
        context=turn_off_context,
    )
    await hass.async_block_till_done()
    assert group in manager.on_to_off_event

    # ...then an automation turned on a member light with a fresh context...
    hass.bus.async_fire(
        EVENT_CALL_SERVICE,
        {
            "domain": LIGHT_DOMAIN,
            "service": SERVICE_TURN_ON,
            "service_data": {ATTR_ENTITY_ID: [member]},
        },
        context=Context(),
    )
    await hass.async_block_till_done()
    assert member in manager.turn_on_event

    # ...which turned the group back on, but HA reused the old turn_off context.
    with patch.object(
        AdaptiveSwitch,
        "_respond_to_off_to_on_event",
        AsyncMock(),
    ) as respond:
        hass.bus.async_fire(
            EVENT_STATE_CHANGED,
            {
                "entity_id": group,
                "old_state": State(group, STATE_OFF),
                "new_state": State(group, STATE_ON),
            },
            context=turn_off_context,
        )
        await hass.async_block_till_done()

    # Adaptation must not have been cancelled as a polling artifact.
    respond.assert_called_once()
    assert respond.call_args[0][0] == group


@pytest.mark.parametrize("brightness_mode", ["linear", "tanh"])
@pytest.mark.parametrize(("dark", "light"), ([900, 1800], [1800, 900], [1800, 1800]))
async def test_brightness_mode(hass, brightness_mode, dark, light):
    """Test brightness mode.

    We are not testing the "default" mode because that is tested in all other tests.
    """
    is_symmetric = dark == light
    _, switch = await setup_switch(
        hass,
        {
            CONF_SUNRISE_TIME: datetime.time(SUNRISE.hour),
            CONF_SUNSET_TIME: datetime.time(SUNSET.hour),
            CONF_BRIGHTNESS_MODE: brightness_mode,
            CONF_BRIGHTNESS_MODE_TIME_DARK: datetime.timedelta(seconds=dark),
            CONF_BRIGHTNESS_MODE_TIME_LIGHT: datetime.timedelta(seconds=light),
        },
    )

    context = switch.create_context("test")  # needs to be passed to update method
    min_brightness = switch._sun_light_settings.min_brightness
    max_brightness = switch._sun_light_settings.max_brightness
    brightness_range = max_brightness - min_brightness
    brightness_event = min_brightness + brightness_range / 2
    dark = switch._sun_light_settings.brightness_mode_time_dark
    light = switch._sun_light_settings.brightness_mode_time_light

    sunset = SUNSET.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
    before_sunset = sunset - light
    after_sunset = sunset + dark
    sunrise = SUNRISE.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(dt_util.UTC)
    before_sunrise = sunrise - dark
    after_sunrise = sunrise + light

    light_brightness = (
        max_brightness
        if brightness_mode == "linear"
        else 0.95 * brightness_range + min_brightness
    )
    dark_brightness = (
        min_brightness
        if brightness_mode == "linear"
        else 0.05 * brightness_range + min_brightness
    )

    def is_approx_equal(a, b):
        return abs(a - b) < 0.01

    async def patch_time_and_update(time):
        with patch(
            "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
            return_value=time,
        ):
            await switch._update_attrs_and_maybe_adapt_lights(context=context)
            await hass.async_block_till_done()

    if is_symmetric:
        # At sunset the brightness should be 50%
        await patch_time_and_update(sunset)
        assert is_approx_equal(switch._settings[ATTR_BRIGHTNESS_PCT], brightness_event)

    # Before sunset the brightness should be max
    await patch_time_and_update(before_sunset)
    assert is_approx_equal(switch._settings[ATTR_BRIGHTNESS_PCT], light_brightness)

    # After sunset the brightness should be dark_brightness
    await patch_time_and_update(after_sunset)
    assert is_approx_equal(switch._settings[ATTR_BRIGHTNESS_PCT], dark_brightness)

    if is_symmetric:
        # At sunrise the brightness should be 50%
        await patch_time_and_update(sunrise)
        assert is_approx_equal(switch._settings[ATTR_BRIGHTNESS_PCT], brightness_event)

    # Before sunrise the brightness should be min
    await patch_time_and_update(before_sunrise)
    assert is_approx_equal(switch._settings[ATTR_BRIGHTNESS_PCT], dark_brightness)

    # After sunrise the brightness should be light_brightness
    await patch_time_and_update(after_sunrise)
    assert is_approx_equal(switch._settings[ATTR_BRIGHTNESS_PCT], light_brightness)


async def test_simple_switch_initial_state_not_none(hass):
    """Test that SimpleSwitch._state is not None after __init__.

    Regression test for https://github.com/basnijholt/adaptive-lighting/issues/1264

    When an entity is disabled in Home Assistant, async_added_to_hass() is never
    called. Previously, SimpleSwitch._state was initialized to None and only set
    to True/False in async_added_to_hass(). This caused an infinite loop in
    AdaptiveSwitch._setup_listeners() which waits for all SimpleSwitch._state
    to be not None.

    The fix is to initialize _state to the initial_state value in __init__.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_NAME: DEFAULT_NAME})
    entry.add_to_hass(hass)

    # Create a SimpleSwitch without calling async_added_to_hass
    # (simulating a disabled entity)
    switch = SimpleSwitch(
        which="Test",
        initial_state=True,
        hass=hass,
        config_entry=entry,
        icon="mdi:test",
    )

    # Before the fix: _state would be None, causing infinite loop
    # After the fix: _state should be the initial_state value
    assert switch._state is not None, (
        "SimpleSwitch._state should not be None after __init__. "
        "This would cause an infinite loop in _setup_listeners when the entity is disabled."
    )
    assert switch._state is True  # Should be the initial_state value


async def test_simple_switch_state_after_async_added_to_hass(hass):
    """Test that SimpleSwitch._state is properly set after async_added_to_hass.

    This ensures the fix for #1264 doesn't break normal entity initialization.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_NAME: DEFAULT_NAME})
    entry.add_to_hass(hass)

    # Create switches with different initial states
    switch_true = SimpleSwitch(
        which="Test True",
        initial_state=True,
        hass=hass,
        config_entry=entry,
        icon="mdi:test",
    )
    switch_false = SimpleSwitch(
        which="Test False",
        initial_state=False,
        hass=hass,
        config_entry=entry,
        icon="mdi:test",
    )

    # Verify initial state is set correctly
    assert switch_true._state is True
    assert switch_false._state is False

    # Call async_added_to_hass (simulating normal entity setup)
    # Since there's no last state, it should use the initial_state
    await switch_true.async_added_to_hass()
    await switch_false.async_added_to_hass()

    # State should still be correct after async_added_to_hass
    assert switch_true._state is True
    assert switch_false._state is False


def test_attributes_have_changed_light_mode_switch():
    """Test detection of external light mode changes (color_temp vs rgb vs xy).

    Regression test for https://github.com/basnijholt/adaptive-lighting/issues/1275

    When a user activates a Hue Scene (or similar) via an external app, the light
    may switch from color_temp mode to RGB/XY mode (or vice versa). This should be
    detected as an external change so AL doesn't immediately override it.

    The _has_color_mode_changed() function checks the original attributes BEFORE
    any conversion, enabling bidirectional mode change detection.
    """
    context = Context()
    base_kwargs = {
        "light": "light.test",
        "context": context,
    }
    kwargs_adapt_color = base_kwargs

    # color_temp → RGB
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 0, 0)},
        **kwargs_adapt_color,
    ), "Should detect color_temp → RGB mode switch"

    # color_temp → XY
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_XY_COLOR: (0.64, 0.33)},
        **kwargs_adapt_color,
    ), "Should detect color_temp → XY mode switch"

    # RGB → color_temp
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 0, 0)},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
        **kwargs_adapt_color,
    ), "Should detect RGB → color_temp mode switch"

    # RGB → XY
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 0, 0)},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_XY_COLOR: (0.64, 0.33)},
        **kwargs_adapt_color,
    ), "Should detect RGB → XY mode switch"

    # XY → color_temp
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_XY_COLOR: (0.64, 0.33)},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
        **kwargs_adapt_color,
    ), "Should detect XY → color_temp mode switch"

    # XY → RGB
    assert _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_XY_COLOR: (0.64, 0.33)},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 0, 0)},
        **kwargs_adapt_color,
    ), "Should detect XY → RGB mode switch"

    # No mode change - same type with same values shouldn't be detected
    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
        **kwargs_adapt_color,
    ), "Same color_temp should not be detected as change"

    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 0, 0)},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 0, 0)},
        **kwargs_adapt_color,
    ), "Same RGB should not be detected as change"

    assert not _attributes_have_changed(
        old_attributes={ATTR_BRIGHTNESS: 128, ATTR_XY_COLOR: (0.64, 0.33)},
        new_attributes={ATTR_BRIGHTNESS: 128, ATTR_XY_COLOR: (0.64, 0.33)},
        **kwargs_adapt_color,
    ), "Same XY should not be detected as change"


# Regression tests for bugs found in PR #1348 by @protyposis
# See: https://github.com/basnijholt/adaptive-lighting/pull/1348


async def test_multi_light_intercept_prepares_adaptation_for_first_entity(hass):
    """Test that adaptation data is prepared for the first entity, not the last.

    Regression test for a bug where `entity_id` from a for-loop was used after
    the loop ended, causing `prepare_adaptation_data` to be called with only
    the last entity's ID instead of the first.

    In `_service_interceptor_turn_on_single_light_handler`:
    ```python
    for entity_id in entity_ids:
        self.clear_proactively_adapting(entity_id)

    adaptation_data = await switch.prepare_adaptation_data(
        entity_id,  # BUG: This uses the last entity_id from the loop!
        transition,
    )
    ```

    The adaptation data should be prepared for the first entity in the list since
    that's the one whose service call is being intercepted and modified.

    See: https://github.com/basnijholt/adaptive-lighting/pull/1348
    """
    switch, _ = await setup_lights_and_switch(hass, {CONF_INTERCEPT: True}, True)

    # Turn off all lights first
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: [ENTITY_LIGHT_1, ENTITY_LIGHT_2, ENTITY_LIGHT_3]},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Mock prepare_adaptation_data to track which entity_id it's called with
    original_prepare = switch.prepare_adaptation_data
    called_with_entities = []

    async def mock_prepare_adaptation_data(light, *args, **kwargs):
        called_with_entities.append(light)
        return await original_prepare(light, *args, **kwargs)

    switch.prepare_adaptation_data = mock_prepare_adaptation_data

    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )

    # Turn on multiple lights at once - this triggers the interceptor
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: [ENTITY_LIGHT_1, ENTITY_LIGHT_2]},
        blocking=True,
    )
    await hass.async_block_till_done()

    # The bug causes prepare_adaptation_data to be called with the LAST entity
    # (ENTITY_LIGHT_2) instead of the FIRST entity (ENTITY_LIGHT_1)
    assert len(called_with_entities) >= 1, "prepare_adaptation_data should be called"

    # The first call should be for ENTITY_LIGHT_1 (the first entity in the list)
    # since the intercepted service call will apply to all entities in entity_ids
    # BUG: Currently this fails because entity_id is ENTITY_LIGHT_2 (the last one)
    assert called_with_entities[0] == ENTITY_LIGHT_1, (
        f"prepare_adaptation_data should be called with the first entity "
        f"({ENTITY_LIGHT_1}), but was called with {called_with_entities[0]}. "
        f"This indicates the bug where the last entity from the for-loop is used."
    )


async def test_skipped_lights_context_not_from_arbitrary_switch(hass):
    """Test that context for skipped lights uses manager, not an arbitrary switch.

    Regression test for a bug where the context for skipped lights was created
    using `switch.create_context("skipped")` where `switch` was from the last
    iteration of a for-loop, which had no relationship to the skipped lights.

    The fix uses `self.create_context("skipped")` on the AdaptiveLightingManager
    instead, which uses "manager" as the context name.

    See: https://github.com/basnijholt/adaptive-lighting/pull/1348
    """
    # Setup two switches with different lights
    lights, switch1, switch2 = await setup_proactive_multiple_lights_two_switches(hass)

    # Turn on all three lights at once:
    # - ENTITY_LIGHT_1 is in switch1
    # - ENTITY_LIGHT_2 is in switch2
    # - ENTITY_LIGHT_3 is not in any switch (will be skipped)
    events = await _turn_on_and_track_event_contexts(
        hass,
        "test_skipped_context",
        lights,
        return_full_events=True,
    )

    # Find the skipped event (contains ":skpp:" in context)
    skipped_events = [e for e in events if ":skpp:" in e.context.id]
    assert (
        len(skipped_events) == 1
    ), f"Expected 1 skipped event, got {len(skipped_events)}"

    skipped_event = skipped_events[0]
    skipped_context_id = skipped_event.context.id

    # Extract the name_hash from the context
    # Context format: {timestamp}:{al}:{name_hash}:{which_short}:{index}
    context_parts = skipped_context_id.split(":")
    assert len(context_parts) >= 4, f"Unexpected context format: {skipped_context_id}"

    # The context should still be recognized as ours
    assert is_our_context_id(skipped_context_id), "Skipped context should be recognized"
    assert is_our_context_id(
        skipped_context_id,
        "skipped",
    ), "Skipped context should have 'skipped' marker"

    # Verify the skipped lights are the ones not in any switch
    assert skipped_event.data["service_data"][ATTR_ENTITY_ID] == [ENTITY_LIGHT_3]

    # After the fix, the context should use "manager" as the name, not a switch name.
    # The name_hash is the 3rd segment (index 2) in the context ID.
    name_hash_in_context = context_parts[2]
    expected_manager_hash = short_hash("manager")
    assert name_hash_in_context == expected_manager_hash, (
        f"Skipped context should use 'manager' hash ({expected_manager_hash}), "
        f"but got {name_hash_in_context}. This indicates the context is still "
        f"being created from an arbitrary switch instead of the manager."
    )


async def test_automation_turn_on_from_off_not_marked_as_manual_control(hass):
    """Test that turning on a light from OFF via automation is not marked as manual control.

    Regression test for https://github.com/basnijholt/adaptive-lighting/issues/1378

    When an automation turns on a light from OFF state with brightness/color attributes,
    the light should NOT be marked as manually controlled. Adaptive Lighting should
    adapt the light normally.

    The bug in v1.30.0 was that `update_manually_controlled_from_event` was called for
    ALL `light.turn_on` events, not just when the light was already ON. This caused
    lights turned on by automations to be incorrectly marked as "manually controlled".
    """
    switch, _ = await setup_lights_and_switch(
        hass,
        {
            CONF_TAKE_OVER_CONTROL: True,
            CONF_DETECT_NON_HA_CHANGES: False,
        },
    )

    # Ensure light is OFF
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_1},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_OFF

    # Verify light is not manually controlled
    assert not switch.manager.manual_control.get(
        ENTITY_LIGHT_1,
    ), "Light should not be manually controlled before test"

    # Simulate an automation turning on the light with brightness
    # This is an external call (not from AL) with brightness attribute
    external_context = Context(id="automation_context_12345")
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: ENTITY_LIGHT_1,
            ATTR_BRIGHTNESS: 255,
        },
        blocking=True,
        context=external_context,
    )
    await hass.async_block_till_done()

    # The light should be ON
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_ON

    # CRITICAL: The light should NOT be marked as manually controlled!
    # The bug in v1.30.0 would incorrectly mark this as manual control because
    # the turn_on had a brightness attribute.
    manual_control_attrs = switch.manager.manual_control.get(ENTITY_LIGHT_1)
    assert not manual_control_attrs, (
        f"Bug confirmed: Light was incorrectly marked as manually controlled "
        f"(attributes: {manual_control_attrs}) when turned on from OFF state. "
        f"Lights turned on from OFF by automations should NOT be marked as "
        f"manually controlled - only lights that were already ON and then had "
        f"their brightness/color changed externally should be marked as such."
    )


@pytest.mark.parametrize("intercept", [True, False])
async def test_adapt_only_on_bare_turn_on_respects_pause_changed_mode(hass, intercept):
    """Test that adapt_only_on_bare_turn_on respects take_over_control_mode=PAUSE_CHANGED.

    When adapt_only_on_bare_turn_on=True and take_over_control_mode=PAUSE_CHANGED,
    turning on a light from OFF with only brightness should:
    1. Mark ONLY brightness as manually controlled (not all attributes)
    2. Continue adapting color (since only brightness was specified)

    This test verifies the integration of #1356 (individual attribute tracking)
    with adapt_only_on_bare_turn_on. Prior to the fix, the code would return early
    after marking attributes as manually controlled, skipping all adaptation
    including unspecified attributes like color.

    The test is parameterized with intercept=True/False to verify consistency
    between the intercept path and the reactive (event-based) path.
    """
    switch, _ = await setup_lights_and_switch(
        hass,
        {
            CONF_TAKE_OVER_CONTROL: True,
            CONF_TAKE_OVER_CONTROL_MODE: TakeOverControlMode.PAUSE_CHANGED.value,
            CONF_ADAPT_ONLY_ON_BARE_TURN_ON: True,
            CONF_DETECT_NON_HA_CHANGES: False,
            CONF_INTERCEPT: intercept,
        },
    )

    # Verify settings
    assert switch._take_over_control
    assert switch._take_over_control_mode == TakeOverControlMode.PAUSE_CHANGED
    assert switch._adapt_only_on_bare_turn_on

    # Ensure light is OFF
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_1},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_OFF

    # Clear any prior service data
    switch.manager.last_service_data.pop(ENTITY_LIGHT_1, None)

    # Turn on light from OFF with only brightness (simulating a scene or automation)
    external_context = Context(id="scene_turn_on_with_brightness")
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: ENTITY_LIGHT_1,
            ATTR_BRIGHTNESS: 200,  # Only brightness specified
        },
        blocking=True,
        context=external_context,
    )
    await hass.async_block_till_done()

    # Light should be ON
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_ON

    # 1. Verify that ONLY brightness is marked as manually controlled
    manual_control_attrs = switch.manager.manual_control.get(ENTITY_LIGHT_1)
    assert manual_control_attrs == LightControlAttributes.BRIGHTNESS, (
        f"Expected only BRIGHTNESS to be marked as manually controlled, "
        f"but got: {manual_control_attrs}. With adapt_only_on_bare_turn_on=True, "
        f"only the attributes specified in the turn_on call should be marked."
    )

    # 2. Verify that color WAS adapted (last_service_data should have color_temp)
    last_service_data = switch.manager.last_service_data.get(ENTITY_LIGHT_1)
    assert last_service_data is not None, (
        "Bug: last_service_data is None, meaning adaptation was skipped entirely. "
        "With PAUSE_CHANGED mode, color should still be adapted since only brightness "
        "was marked as manually controlled."
    )
    assert ATTR_COLOR_TEMP_KELVIN in last_service_data, (
        f"Bug: Color was not adapted. last_service_data={last_service_data}. "
        f"With take_over_control_mode=PAUSE_CHANGED and only brightness marked "
        f"as manually controlled, color_temp should still be adapted."
    )


async def test_detect_non_ha_changes_with_separate_turn_on_commands(hass):
    """Regression test for detect_non_ha_changes with separate_turn_on_commands.

    With separate_turn_on_commands=True, each adaptation cycle makes two sequential
    light.turn_on calls (brightness, then color). If the second call overwrites
    last_service_data instead of merging, brightness is dropped — and
    _attributes_have_changed silently skips the brightness comparison, so a direct
    Zigbee brightness change is never detected as manual control.
    """
    switch, (light, *_) = await setup_lights_and_switch(
        hass,
        {
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_DETECT_NON_HA_CHANGES: True,
            CONF_TAKE_OVER_CONTROL: True,
        },
    )

    context = switch.create_context("test")

    async def update(force: bool = False):
        await switch._update_attrs_and_maybe_adapt_lights(
            context=context,
            force=force,
            transition=0,
        )
        await hass.async_block_till_done()

    await update(force=True)

    last_sd = switch.manager.last_service_data.get(ENTITY_LIGHT_1)
    assert last_sd is not None, "last_service_data not set after force adapt"
    assert (
        ATTR_BRIGHTNESS in last_sd
    ), f"brightness missing from last_service_data after split calls: {last_sd}"
    assert (
        ATTR_COLOR_TEMP_KELVIN in last_sd or ATTR_RGB_COLOR in last_sd
    ), f"color missing from last_service_data after split calls: {last_sd}"

    al_brightness = light.brightness
    assert al_brightness is not None
    switch.manager.manual_control[ENTITY_LIGHT_1] = LightControlAttributes.NONE

    manual_brightness = (
        al_brightness - 120 if al_brightness >= 120 else al_brightness + 120
    )
    set_light_brightness(light, manual_brightness)

    async def _flush_attr_state(hass, entity_id):
        """Mimic a ZHA attribute report: write current hardware state to HA."""
        light.async_write_ha_state()

    with patch(
        "homeassistant.components.adaptive_lighting.switch.async_update_entity",
        new=AsyncMock(side_effect=_flush_attr_state),
    ):
        await update(force=False)

        assert LightControlAttributes.BRIGHTNESS in switch.manager.manual_control.get(
            ENTITY_LIGHT_1,
            LightControlAttributes.NONE,
        ), (
            f"manual_control={switch.manager.manual_control.get(ENTITY_LIGHT_1)}, "
            f"last_service_data={switch.manager.last_service_data.get(ENTITY_LIGHT_1)}"
        )

        await update(force=False)

    assert (
        light.brightness == manual_brightness
    ), f"AL overrode manual brightness {manual_brightness} with {al_brightness}"


async def test_fresh_install_entity_ids(hass):
    """Test the entity ids a new install gets with device-relative naming."""
    _, switch = await setup_switch(hass, {})

    assert switch.entity_id == ENTITY_SWITCH
    assert switch.sleep_mode_switch.entity_id == ENTITY_SLEEP_MODE_SWITCH
    assert switch.adapt_brightness_switch.entity_id == ENTITY_ADAPT_BRIGHTNESS_SWITCH
    assert switch.adapt_color_switch.entity_id == ENTITY_ADAPT_COLOR_SWITCH


async def test_existing_entity_ids_are_preserved(hass):
    """Test an install predating this change keeps its entity ids.

    The unique ids are unchanged, so the entity registry must keep the
    classic `..._sleep_mode_<name>` id instead of renaming the entity.
    """
    classic_entity_id = f"{_SWITCH_FMT}_sleep_mode_{DEFAULT_NAME}"
    assert classic_entity_id != ENTITY_SLEEP_MODE_SWITCH

    registry = entity_registry.async_get(hass)
    registry.async_get_or_create(
        SWITCH_DOMAIN,
        DOMAIN,
        f"{DEFAULT_NAME}_sleep_mode",
        suggested_object_id=classic_entity_id.split(".", 1)[1],
    )

    _, switch = await setup_switch(hass, {})

    assert switch.sleep_mode_switch.entity_id == classic_entity_id


def test_validate_ui_options_win_over_stale_data():
    """A UI-configured entry's `options` (from the options flow) must win.

    `data` for a `SOURCE_USER` entry either only holds the entry name, or -
    for entries created before `data`/`options` were split - a stale
    snapshot from initial setup. Either way, a later change made through
    the options flow (stored in `options`) must not be silently discarded
    by that stale/legacy `data`.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_USER,
        data={CONF_NAME: DEFAULT_NAME, CONF_LIGHTS: ["light.a"]},
        options={CONF_LIGHTS: ["light.a", "light.b"]},
    )

    result = validate(entry)

    assert result[CONF_LIGHTS] == ["light.a", "light.b"]


def test_validate_yaml_data_wins_over_stray_options():
    """A YAML-imported entry's `data` must keep winning over `options`.

    YAML configuration is the source of truth for a `SOURCE_IMPORT` entry,
    so any leftover `options` (e.g. from a UI setup that predates the YAML
    import) must not override it.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_IMPORT,
        data={CONF_NAME: DEFAULT_NAME, CONF_LIGHTS: ["light.a"]},
        options={CONF_LIGHTS: ["light.b"]},
    )

    result = validate(entry)

    assert result[CONF_LIGHTS] == ["light.a"]


@pytest.mark.parametrize("service", [SERVICE_TURN_ON, SERVICE_TOGGLE])
@pytest.mark.parametrize("explicit", [False, True], ids=["area", "direct"])
@pytest.mark.parametrize("managed", [False, True], ids=["unmanaged", "managed"])
@pytest.mark.parametrize(
    "registry_settings",
    [
        {},
        {"entity_category": EntityCategory.CONFIG},
        {"entity_category": EntityCategory.DIAGNOSTIC},
        {"hidden_by": entity_registry.RegistryEntryHider.USER},
    ],
    ids=["normal", "config", "diagnostic", "hidden"],
)
async def test_intercept_preserves_area_target_exclusions(
    hass: HomeAssistant,
    service: str,
    explicit: bool,
    managed: bool,
    registry_settings: dict[str, Any],
):
    """Area calls exclude hidden/categorized lights; direct calls honor them."""
    await setup_lights(hass)
    mock_area_registry(hass)
    registry = entity_registry.async_get(hass)
    lights = [ENTITY_LIGHT_1, ENTITY_LIGHT_2, ENTITY_LIGHT_3]
    for light in lights:
        registry.async_update_entity(light, area_id="test-area")
    registry.async_update_entity(ENTITY_LIGHT_3, **registry_settings)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: lights},
        blocking=True,
    )
    await hass.async_block_till_done()
    await setup_switch(
        hass,
        {
            CONF_LIGHTS: (
                [ENTITY_LIGHT_1, ENTITY_LIGHT_3] if managed else [ENTITY_LIGHT_1]
            ),
            CONF_INTERCEPT: True,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_BRIGHTNESS: 50,
            CONF_MAX_BRIGHTNESS: 50,
        },
    )
    assert all(hass.states.get(light).state == STATE_OFF for light in lights)

    target = {ATTR_ENTITY_ID: lights} if explicit else {ATTR_AREA_ID: "test-area"}
    await hass.services.async_call(LIGHT_DOMAIN, service, target, blocking=True)
    await hass.async_block_till_done()

    # Both normal lights turn on; only the managed one gets adaptive brightness.
    assert hass.states.get(ENTITY_LIGHT_1).state == STATE_ON
    assert hass.states.get(ENTITY_LIGHT_1).attributes[ATTR_BRIGHTNESS] == 128
    assert hass.states.get(ENTITY_LIGHT_2).state == STATE_ON
    assert hass.states.get(ENTITY_LIGHT_2).attributes.get(ATTR_BRIGHTNESS) != 128
    target_state = hass.states.get(ENTITY_LIGHT_3)
    if registry_settings and not explicit:
        assert target_state.state == STATE_OFF
    else:
        assert target_state.state == STATE_ON
        if managed:
            assert target_state.attributes[ATTR_BRIGHTNESS] == 128
        else:
            assert target_state.attributes.get(ATTR_BRIGHTNESS) != 128


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("target_group", [False, True])
@pytest.mark.parametrize("skip_redundant", [False, True])
async def test_multi_light_intercept_adapts_every_member(
    hass,
    split,
    target_group,
    skip_redundant,
    cleanup,
):
    """Each member receives brightness and color, including split follow-up calls."""
    lights = await setup_lights(hass, with_group=True)
    # The second member already has target brightness; its color still needs work.
    set_light_brightness(lights[4], 171)
    lights[4].async_write_ha_state()
    members = ["light.light_4", "light.light_5"]
    _, switch = await setup_switch(
        hass,
        {
            CONF_LIGHTS: members,
            CONF_INTERCEPT: True,
            CONF_MULTI_LIGHT_INTERCEPT: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: split,
            CONF_SKIP_REDUNDANT_COMMANDS: skip_redundant,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )
    events = await _turn_on_and_track_event_contexts(
        hass,
        "multi_light_split",
        "light.light_group" if target_group else members,
        return_full_events=True,
    )
    await asyncio.gather(*switch.manager.adaptation_tasks)
    await hass.async_block_till_done()

    if split:
        color_targets = {
            event.data["service_data"][ATTR_ENTITY_ID]
            for event in events
            if ATTR_COLOR_TEMP_KELVIN in event.data["service_data"]
        }
        assert color_targets == set(members)
    for entity_id in members:
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        assert state.attributes[ATTR_BRIGHTNESS] == 171
        assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 3448


@pytest.mark.parametrize("physical_off", [False, True])
async def test_split_command_stays_off_after_turn_off(hass, physical_off):
    """An actual OFF between brightness and color cancels the pending command."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_INTERCEPT: True, CONF_SEPARATE_TURN_ON_COMMANDS: True},
        all_lights=True,
    )
    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )
    events = await _turn_on_and_track_event_contexts(
        hass,
        "split_then_off",
        ENTITY_LIGHT_3,
        return_full_events=True,
    )
    assert len(events) == 1
    assert hass.states.get(ENTITY_LIGHT_3).state == STATE_ON
    if physical_off:
        # Device reports may retain the context of the preceding turn-on.
        state = hass.states.get(ENTITY_LIGHT_3)
        hass.states.async_set(
            ENTITY_LIGHT_3,
            STATE_OFF,
            state.attributes,
            context=Context(id="split_then_off"),
        )
    else:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_3},
            blocking=True,
        )
    await hass.async_block_till_done()
    await asyncio.gather(*switch.manager.adaptation_tasks)
    await hass.async_block_till_done()

    turn_on_events = [
        event for event in events if event.data["service"] == SERVICE_TURN_ON
    ]
    assert len(turn_on_events) == 1
    assert hass.states.get(ENTITY_LIGHT_3).state == STATE_OFF


@pytest.mark.parametrize("brightness_only_member", [0, 1])
async def test_multi_light_split_with_brightness_only_member(
    hass,
    brightness_only_member,
    cleanup,
):
    """A brightness-only member must not consume another member's color command."""
    lights = await setup_lights(hass, with_group=True)
    members = ["light.light_4", "light.light_5"]
    light = lights[3 + brightness_only_member]
    # Legacy YAML support outlived the old entity storage fields.
    if hasattr(light, "_supported_color_modes"):
        light._supported_color_modes = {ColorMode.BRIGHTNESS}
        light._color_mode = ColorMode.BRIGHTNESS
    else:
        light._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        light._attr_color_mode = ColorMode.BRIGHTNESS
    light.async_write_ha_state()
    _, switch = await setup_switch(
        hass,
        {
            CONF_LIGHTS: members,
            CONF_INTERCEPT: True,
            CONF_MULTI_LIGHT_INTERCEPT: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )
    events = await _turn_on_and_track_event_contexts(
        hass,
        "mixed_split",
        members,
        return_full_events=True,
    )
    await asyncio.gather(*switch.manager.adaptation_tasks)
    await hass.async_block_till_done()
    color_targets = [
        event.data["service_data"][ATTR_ENTITY_ID]
        for event in events
        if ATTR_COLOR_TEMP_KELVIN in event.data["service_data"]
    ]
    assert color_targets == [members[1 - brightness_only_member]]
    for entity_id in members:
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        assert state.attributes[ATTR_BRIGHTNESS] == 171
    assert (
        hass.states.get(members[1 - brightness_only_member]).attributes[
            ATTR_COLOR_TEMP_KELVIN
        ]
        == 3448
    )


@pytest.mark.parametrize("off_member", [0, 1])
@pytest.mark.parametrize("physical_off", [False, True])
async def test_multi_light_split_cancels_only_member_turned_off(
    hass,
    off_member,
    physical_off,
    cleanup,
):
    """An OFF member stays off while the other finishes its color adaptation."""
    await setup_lights(hass, with_group=True)
    members = ["light.light_4", "light.light_5"]
    _, switch = await setup_switch(
        hass,
        {
            CONF_LIGHTS: members,
            CONF_INTERCEPT: True,
            CONF_MULTI_LIGHT_INTERCEPT: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )
    resume = asyncio.Event()
    original_execute = switch._execute_adaptation_calls

    async def wait_before_followup(data):
        await resume.wait()
        await original_execute(data)

    with patch.object(switch, "_execute_adaptation_calls", new=wait_before_followup):
        events = await _turn_on_and_track_event_contexts(
            hass,
            "member_off",
            members,
            return_full_events=True,
        )
        off_entity = members[off_member]
        state = hass.states.get(off_entity)
        assert state.state == STATE_ON
        if physical_off:
            hass.states.async_set(
                off_entity,
                STATE_OFF,
                state.attributes,
                context=Context(id="member_off"),
            )
        else:
            await hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: off_entity},
                blocking=True,
            )
        await hass.async_block_till_done()
        resume.set()
        await asyncio.gather(*switch.manager.adaptation_tasks)
        await hass.async_block_till_done()

    color_targets = [
        event.data["service_data"][ATTR_ENTITY_ID]
        for event in events
        if ATTR_COLOR_TEMP_KELVIN in event.data["service_data"]
    ]
    assert color_targets == [members[1 - off_member]]
    assert hass.states.get(off_entity).state == STATE_OFF
    other_state = hass.states.get(members[1 - off_member])
    assert other_state.state == STATE_ON
    assert other_state.attributes[ATTR_BRIGHTNESS] == 171
    assert other_state.attributes[ATTR_COLOR_TEMP_KELVIN] == 3448


@pytest.mark.parametrize(
    "off_action",
    [SERVICE_TURN_OFF, SERVICE_TOGGLE, "physical", "transition"],
)
async def test_forced_split_apply_stays_off(hass, off_action, cleanup):
    """Even forced apply must cancel its remaining color command after OFF."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_INTERCEPT: True, CONF_SEPARATE_TURN_ON_COMMANDS: True},
        all_lights=True,
    )
    _mock_sun_light_settings(
        switch,
        {
            ATTR_BRIGHTNESS_PCT: 67,
            ATTR_COLOR_TEMP_KELVIN: 3448,
            "force_rgb_color": False,
        },
    )
    events = []
    light_on = asyncio.Event()
    waiting_for_color = asyncio.Event()
    resume = asyncio.Event()
    calls_read = 0
    original_next = AdaptationData.next_service_call_data

    async def next_with_color_barrier(data):
        nonlocal calls_read
        calls_read += 1
        if calls_read == 2:
            waiting_for_color.set()
            await resume.wait()
        return await original_next(data)

    async def track_service(event):
        if event.data["domain"] == LIGHT_DOMAIN:
            events.append(event)

    async def track_state(event):
        if (
            event.data[ATTR_ENTITY_ID] == ENTITY_LIGHT_3
            and event.data["new_state"] is not None
            and event.data["new_state"].state == STATE_ON
        ):
            light_on.set()

    hass.bus.async_listen(EVENT_CALL_SERVICE, track_service)
    hass.bus.async_listen(EVENT_STATE_CHANGED, track_state)
    with patch.object(
        AdaptationData,
        "next_service_call_data",
        new=next_with_color_barrier,
    ):
        applying = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                SERVICE_APPLY,
                {
                    ATTR_ENTITY_ID: switch.entity_id,
                    CONF_LIGHTS: [ENTITY_LIGHT_3],
                    CONF_TURN_ON_LIGHTS: True,
                },
                blocking=True,
            ),
        )
        await asyncio.wait_for(waiting_for_color.wait(), timeout=1)
        await asyncio.wait_for(light_on.wait(), timeout=1)
        if off_action == "physical":
            state = hass.states.get(ENTITY_LIGHT_3)
            hass.states.async_set(
                ENTITY_LIGHT_3,
                STATE_OFF,
                state.attributes,
                context=state.context,
            )
        else:
            service_data = {ATTR_ENTITY_ID: ENTITY_LIGHT_3}
            if off_action == "transition":
                service_data[ATTR_TRANSITION] = 1
            await hass.services.async_call(
                LIGHT_DOMAIN,
                SERVICE_TURN_OFF if off_action == "transition" else off_action,
                service_data,
                blocking=True,
            )
        await hass.async_block_till_done()
        resume.set()
        await applying
        await hass.async_block_till_done()

    turn_on_events = [
        event for event in events if event.data["service"] == SERVICE_TURN_ON
    ]
    assert len(turn_on_events) == 1
    assert ATTR_BRIGHTNESS in turn_on_events[0].data["service_data"]
    assert ATTR_COLOR_TEMP_KELVIN not in turn_on_events[0].data["service_data"]
    assert hass.states.get(ENTITY_LIGHT_3).state == STATE_OFF
