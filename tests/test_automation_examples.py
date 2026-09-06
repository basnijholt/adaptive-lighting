"""Execute the automation examples published in README.md."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import yaml
from homeassistant.components import automation, script
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    LightControlAttributes,
)
from homeassistant.components.adaptive_lighting.const import (
    CONF_INITIAL_TRANSITION,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_NAME,
    CONF_SLEEP_BRIGHTNESS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_SLEEP_RGB_OR_COLOR_TEMP,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    CONF_TRANSITION,
    DOMAIN,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
)
from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_CALL_SERVICE,
    EVENT_STATE_CHANGED,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import CoreState, Event, HomeAssistant, State, callback
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from tests.common import async_fire_time_changed

from .test_switch import setup_switch

if TYPE_CHECKING:
    from collections.abc import Callable

README = Path(__file__).resolve().parents[1] / "README.md"


def _yaml_documents(summary: str) -> list[object]:
    """Load every YAML fence from one README details block."""
    readme = README.read_text()
    details = re.search(
        rf"<summary>{re.escape(summary)}</summary>(.*?)</details>",
        readme,
        flags=re.DOTALL,
    )
    assert details is not None, f"README example not found: {summary}"
    blocks = re.findall(r"```yaml\n(.*?)```", details.group(1), flags=re.DOTALL)
    assert blocks, f"README example has no YAML: {summary}"
    return [yaml.safe_load(block) for block in blocks]


async def _setup_automation(hass: HomeAssistant, config: object) -> None:
    """Load an extracted automation through Home Assistant."""
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {automation.DOMAIN: config},
    )
    await hass.async_block_till_done()


async def _setup_script(hass: HomeAssistant, config: dict) -> None:
    """Load an extracted script through Home Assistant."""
    assert await async_setup_component(hass, script.DOMAIN, config)
    await hass.async_block_till_done()


async def _setup_template_lights(
    hass: HomeAssistant,
    names: list[str],
) -> None:
    """Create color-temperature and RGB lights with documented entity IDs."""
    lights = [
        {
            "name": name,
            "unique_id": name.lower().replace(" ", "_"),
            "turn_on": None,
            "turn_off": None,
            "set_level": None,
            "set_temperature": None,
            "set_rgb": None,
        }
        for name in names
    ]
    assert await async_setup_component(
        hass,
        "template",
        {"template": {"light": lights}},
    )
    await hass.async_block_till_done()


def _state_waiter(
    hass: HomeAssistant,
    entity_id: str,
    predicate: Callable[[State], bool],
) -> tuple[asyncio.Future[State], Callable[[], None]]:
    """Return a future that resolves when an entity state matches a predicate."""
    future = hass.loop.create_future()

    @callback
    def state_changed(event: Event) -> None:
        new_state = event.data.get("new_state")
        if (
            not future.done()
            and new_state is not None
            and new_state.entity_id == entity_id
            and predicate(new_state)
        ):
            future.set_result(new_state)

    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, state_changed)
    return future, remove_listener


def _prepare_hass_startup(hass: HomeAssistant) -> None:
    """Reset the standard running test fixture to exercise a real HA start."""
    hass.set_state(CoreState.not_running)


async def test_schedule_profile_executes_blocks_and_restore(
    hass: HomeAssistant,
) -> None:
    """Catch ignored attribute changes, incomplete restore, or switch coupling."""
    summary = "Use a Schedule helper as a step-based custom lighting profile."
    automation_config = _yaml_documents(summary)[-1]
    _, adaptive_switch = await setup_switch(
        hass,
        {
            CONF_NAME: "Living Room",
            CONF_LIGHTS: ["light.manually_controlled"],
            CONF_MIN_BRIGHTNESS: 8,
            CONF_MAX_BRIGHTNESS: 88,
            CONF_MIN_COLOR_TEMP: 2100,
            CONF_MAX_COLOR_TEMP: 5100,
        },
    )
    adaptive_switch.manager.set_manual_control_attributes(
        "light.manually_controlled",
        LightControlAttributes.BRIGHTNESS,
    )
    hass.states.async_set(
        "schedule.adaptive_lighting_profile",
        STATE_OFF,
    )
    await _setup_automation(hass, automation_config)

    hass.states.async_set(
        "schedule.adaptive_lighting_profile",
        STATE_ON,
        {"brightness_pct": 20, "color_temp_kelvin": 2500},
    )
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.min_brightness == 20
    assert adaptive_switch._sun_light_settings.max_brightness == 20
    assert adaptive_switch._sun_light_settings.min_color_temp == 2500
    assert adaptive_switch._sun_light_settings.max_color_temp == 2500

    hass.states.async_set(
        "schedule.adaptive_lighting_profile",
        STATE_ON,
        {"brightness_pct": 60, "color_temp_kelvin": 4000},
    )
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.min_brightness == 60
    assert adaptive_switch._sun_light_settings.max_brightness == 60
    assert adaptive_switch._sun_light_settings.min_color_temp == 4000
    assert adaptive_switch._sun_light_settings.max_color_temp == 4000

    hass.states.async_set("schedule.adaptive_lighting_profile", STATE_OFF)
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.min_brightness == 8
    assert adaptive_switch._sun_light_settings.max_brightness == 88
    assert adaptive_switch._sun_light_settings.min_color_temp == 2100
    assert adaptive_switch._sun_light_settings.max_color_temp == 5100
    assert adaptive_switch.manager.manual_control["light.manually_controlled"]

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: adaptive_switch.entity_id},
        blocking=True,
    )
    hass.states.async_set(
        "schedule.adaptive_lighting_profile",
        STATE_ON,
        {"brightness_pct": 35, "color_temp_kelvin": 2750},
    )
    await hass.async_block_till_done()
    assert adaptive_switch.is_on is False
    assert adaptive_switch._sun_light_settings.min_brightness == 35
    assert adaptive_switch._sun_light_settings.max_color_temp == 2750


async def test_schedule_profile_reapplies_at_startup(hass: HomeAssistant) -> None:
    """Verify startup applies the already-active schedule block."""
    _prepare_hass_startup(hass)
    summary = "Use a Schedule helper as a step-based custom lighting profile."
    automation_config = _yaml_documents(summary)[-1]
    _, adaptive_switch = await setup_switch(hass, {CONF_NAME: "Living Room"})
    hass.states.async_set(
        "schedule.adaptive_lighting_profile",
        STATE_ON,
        {"brightness_pct": 20, "color_temp_kelvin": 2500},
    )
    await _setup_automation(hass, automation_config)

    await hass.async_start()
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.min_brightness == 20
    assert adaptive_switch._sun_light_settings.max_brightness == 20
    assert adaptive_switch._sun_light_settings.min_color_temp == 2500
    assert adaptive_switch._sun_light_settings.max_color_temp == 2500


async def test_lux_profile_executes_hysteresis(hass: HomeAssistant) -> None:
    """Catch missing threshold actions or changes inside the dead band."""
    summary = (
        "Reduce daytime brightness when an illuminance sensor detects strong daylight."
    )
    automation_config = _yaml_documents(summary)[0]
    _, adaptive_switch = await setup_switch(
        hass,
        {CONF_NAME: "Living Room", CONF_MAX_BRIGHTNESS: 80},
    )
    hass.states.async_set("sensor.living_room_illuminance", "250")
    await _setup_automation(hass, automation_config)

    hass.states.async_set("sensor.living_room_illuminance", "350")
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.max_brightness == 30

    hass.states.async_set("sensor.living_room_illuminance", "250")
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.max_brightness == 30

    hass.states.async_set("sensor.living_room_illuminance", "150")
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.max_brightness == 100

    hass.states.async_set("sensor.living_room_illuminance", "250")
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.max_brightness == 100


async def test_lux_profile_executes_unknown_recovery_at_startup(
    hass: HomeAssistant,
) -> None:
    """Catch a startup hang or failure to recover from an unknown sensor."""
    _prepare_hass_startup(hass)
    summary = (
        "Reduce daytime brightness when an illuminance sensor detects strong daylight."
    )
    automation_config = _yaml_documents(summary)[0]
    _, adaptive_switch = await setup_switch(
        hass,
        {CONF_NAME: "Living Room", CONF_MAX_BRIGHTNESS: 80},
    )
    hass.states.async_set("sensor.living_room_illuminance", "unknown")
    await _setup_automation(hass, automation_config)
    waiting, remove_listener = _state_waiter(
        hass,
        "automation.adaptive_lighting_limit_brightness_in_daylight",
        lambda state: state.attributes.get("current") == 1,
    )

    await hass.async_start()
    await asyncio.wait_for(waiting, timeout=1)
    remove_listener()
    assert adaptive_switch._sun_light_settings.max_brightness == 80

    hass.states.async_set("sensor.living_room_illuminance", "350")
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.max_brightness == 30


async def test_hue_script_applies_current_values_to_fresh_profile_targets(
    hass: HomeAssistant,
) -> None:
    """Catch an invalid script wrapper or a one-shot apply that skips off lights."""
    summary = "Turn on Hue-controlled lights with the current Adaptive Lighting values."
    script_config = _yaml_documents(summary)[0]
    await _setup_template_lights(
        hass,
        ["Living Room Ceiling", "Living Room Table"],
    )
    _, adaptive_switch = await setup_switch(
        hass,
        {
            CONF_NAME: "Living Room",
            CONF_LIGHTS: [
                "light.living_room_ceiling",
                "light.living_room_table",
            ],
            CONF_SUNRISE_TIME: "06:00:00",
            CONF_SUNSET_TIME: "18:00:00",
            CONF_MIN_BRIGHTNESS: 10,
            CONF_MAX_BRIGHTNESS: 80,
            CONF_MIN_COLOR_TEMP: 2000,
            CONF_MAX_COLOR_TEMP: 5000,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
        },
    )
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: adaptive_switch.entity_id},
        blocking=True,
    )
    adaptive_switch.manager.set_manual_control_attributes(
        "light.living_room_ceiling",
        LightControlAttributes.BRIGHTNESS | LightControlAttributes.COLOR,
    )
    await _setup_script(hass, script_config)

    noon = datetime(2026, 9, 6, 12, tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(UTC)
    with patch(
        "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
        return_value=noon,
    ):
        await hass.services.async_call(
            script.DOMAIN,
            "living_room_adaptive_lighting",
            blocking=True,
        )
    await hass.async_block_till_done()

    for entity_id in ("light.living_room_ceiling", "light.living_room_table"):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_ON
        assert state.attributes[ATTR_BRIGHTNESS] == 204
        assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 5000
    assert adaptive_switch.is_on is False
    assert adaptive_switch.manager.manual_control["light.living_room_ceiling"]


async def test_rgb_bedtime_script_applies_stage_then_restores_configuration(
    hass: HomeAssistant,
) -> None:
    """Catch a wrong fresh child ID, delayed first stage, or missing restoration."""
    summary = "Use a fixed RGB stage before sleep mode."
    script_config = _yaml_documents(summary)[0]
    await _setup_template_lights(hass, ["Bedroom"])
    _, adaptive_switch = await setup_switch(
        hass,
        {
            CONF_NAME: "Bedroom",
            CONF_LIGHTS: ["light.bedroom"],
            CONF_SLEEP_BRIGHTNESS: 7,
            CONF_SLEEP_COLOR_TEMP: 2300,
            CONF_SLEEP_RGB_OR_COLOR_TEMP: "color_temp",
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
        },
    )
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.bedroom"},
        blocking=True,
    )
    adaptive_switch.manager.set_manual_control_attributes(
        "light.bedroom",
        LightControlAttributes.ALL,
    )
    await _setup_script(hass, script_config)
    light_staged, remove_light_listener = _state_waiter(
        hass,
        "light.bedroom",
        lambda state: (
            state.attributes.get(ATTR_BRIGHTNESS) == 51
            and state.attributes.get(ATTR_RGB_COLOR) == (255, 56, 0)
        ),
    )
    sleep_enabled, remove_sleep_listener = _state_waiter(
        hass,
        "switch.adaptive_lighting_bedroom_sleep_mode",
        lambda state: state.state == STATE_ON,
    )

    await hass.services.async_call(
        script.DOMAIN,
        "adaptive_lighting_bedtime",
        blocking=False,
    )
    await asyncio.wait_for(asyncio.gather(light_staged, sleep_enabled), timeout=1)
    remove_light_listener()
    remove_sleep_listener()
    # Let the script continue from the completed switch action into its delay.
    await asyncio.sleep(0)
    sleep_state = hass.states.get("switch.adaptive_lighting_bedroom_sleep_mode")
    assert sleep_state is not None
    assert sleep_state.state == STATE_ON
    assert adaptive_switch._sun_light_settings.sleep_brightness == 20
    assert adaptive_switch._sun_light_settings.sleep_rgb_or_color_temp == "rgb_color"
    assert adaptive_switch._sun_light_settings.sleep_rgb_color == [255, 56, 0]
    assert not adaptive_switch.manager.manual_control["light.bedroom"]
    bedroom_state = hass.states.get("light.bedroom")
    assert bedroom_state is not None
    assert bedroom_state.attributes[ATTR_BRIGHTNESS] == 51
    assert bedroom_state.attributes[ATTR_RGB_COLOR] == (255, 56, 0)

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=30))
    await hass.async_block_till_done()
    assert adaptive_switch._sun_light_settings.sleep_brightness == 7
    assert adaptive_switch._sun_light_settings.sleep_rgb_or_color_temp == "color_temp"
    assert adaptive_switch._sun_light_settings.sleep_color_temp == 2300
    bedroom_state = hass.states.get("light.bedroom")
    assert bedroom_state is not None
    assert bedroom_state.attributes[ATTR_COLOR_TEMP_KELVIN] == pytest.approx(
        2300,
        abs=5,
    )


async def test_fixed_virtual_day_curve_and_power_automation(
    hass: HomeAssistant,
    freezer,
) -> None:
    """Catch a broken cross-midnight curve or power-trigger branch."""
    summary = "Run a fixed virtual day across midnight."
    integration_config, automation_config = _yaml_documents(summary)
    await _setup_template_lights(hass, ["Indoor Garden"])
    assert isinstance(integration_config, dict)
    assert await async_setup_component(hass, DOMAIN, integration_config)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    adaptive_switch = hass.data[DOMAIN][entry.entry_id][SWITCH_DOMAIN]

    expected_brightness = {
        datetime(2026, 9, 6, 16, tzinfo=dt_util.DEFAULT_TIME_ZONE): 10,
        datetime(2026, 9, 6, 22, tzinfo=dt_util.DEFAULT_TIME_ZONE): 100,
        datetime(2026, 9, 7, 4, tzinfo=dt_util.DEFAULT_TIME_ZONE): 10,
    }
    for now, expected in expected_brightness.items():
        assert adaptive_switch._sun_light_settings.brightness_pct(
            now,
            False,
        ) == pytest.approx(
            expected,
        )

    freezer.move_to(
        datetime(2026, 9, 6, 15, 59, tzinfo=dt_util.DEFAULT_TIME_ZONE),
    )
    await _setup_automation(hass, automation_config)
    await hass.async_start()
    async_fire_time_changed(
        hass,
        datetime(2026, 9, 6, 16, tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(UTC),
    )
    await hass.async_block_till_done()
    garden_state = hass.states.get("light.indoor_garden")
    assert garden_state is not None
    assert garden_state.state == STATE_ON

    async_fire_time_changed(
        hass,
        datetime(2026, 9, 7, 4, tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(UTC),
    )
    await hass.async_block_till_done()
    garden_state = hass.states.get("light.indoor_garden")
    assert garden_state is not None
    assert garden_state.state == STATE_OFF


@pytest.mark.parametrize(
    ("start_hour", "expected_state"),
    [(10, STATE_OFF), (22, STATE_ON)],
)
async def test_fixed_virtual_day_reconciles_power_at_startup(
    hass: HomeAssistant,
    freezer,
    start_hour: int,
    expected_state: str,
) -> None:
    """Catch a power schedule that misses a trigger while HA is offline."""
    _prepare_hass_startup(hass)
    summary = "Run a fixed virtual day across midnight."
    _, automation_config = _yaml_documents(summary)
    await _setup_template_lights(hass, ["Indoor Garden"])
    await _setup_automation(hass, automation_config)
    freezer.move_to(
        datetime(2026, 9, 6, start_hour, tzinfo=dt_util.DEFAULT_TIME_ZONE),
    )

    await hass.async_start()
    await hass.async_block_till_done()

    garden_state = hass.states.get("light.indoor_garden")
    assert garden_state is not None
    assert garden_state.state == expected_state


async def test_autoreset_manual_control_uses_one_renewable_timer(
    hass: HomeAssistant,
) -> None:
    """Validate the documented built-in timeout and its renewal behavior."""
    summary = "Automatically reset manual control after one hour."
    integration_config = _yaml_documents(summary)[0]
    await _setup_template_lights(hass, ["Living Room"])
    assert isinstance(integration_config, dict)
    assert await async_setup_component(hass, DOMAIN, integration_config)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    adaptive_switch = hass.data[DOMAIN][entry.entry_id][SWITCH_DOMAIN]
    assert adaptive_switch._auto_reset_manual_control_time == 3600

    service_data = {
        ATTR_ENTITY_ID: adaptive_switch.entity_id,
        CONF_LIGHTS: ["light.living_room"],
        "manual_control": True,
    }
    await hass.services.async_call(
        DOMAIN,
        "set_manual_control",
        service_data,
        blocking=True,
    )
    first_timer = adaptive_switch.manager.auto_reset_manual_control_timers[
        "light.living_room"
    ]
    first_task = first_timer.task

    await hass.services.async_call(
        DOMAIN,
        "set_manual_control",
        service_data,
        blocking=True,
    )
    renewed_timer = adaptive_switch.manager.auto_reset_manual_control_timers[
        "light.living_room"
    ]
    await asyncio.sleep(0)
    assert renewed_timer is first_timer
    assert renewed_timer.task is not first_task
    assert first_task is not None
    assert first_task.cancelled()
    assert adaptive_switch.manager.manual_control["light.living_room"]

    await renewed_timer.callback()
    assert not adaptive_switch.manager.manual_control["light.living_room"]


async def test_sleep_toggle_uses_fresh_profile_entity_ids(
    hass: HomeAssistant,
) -> None:
    """Execute state triggers against fresh child entity IDs."""
    summary = (
        'Toggle multiple Adaptive Lighting switches to "sleep mode" using an '
        "<code>input_boolean.sleep_mode</code>."
    )
    automation_config = _yaml_documents(summary)[0]
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"sleep_mode": {}}},
    )
    await setup_switch(hass, {CONF_NAME: "Living Room"})
    await setup_switch(hass, {CONF_NAME: "Bedroom"})
    await _setup_automation(hass, automation_config)

    await hass.services.async_call(
        "input_boolean",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "input_boolean.sleep_mode"},
        blocking=True,
    )
    await hass.async_block_till_done()
    for entity_id in (
        "switch.adaptive_lighting_living_room_sleep_mode",
        "switch.adaptive_lighting_bedroom_sleep_mode",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_ON

    await hass.services.async_call(
        "input_boolean",
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "input_boolean.sleep_mode"},
        blocking=True,
    )
    await hass.async_block_till_done()
    for entity_id in (
        "switch.adaptive_lighting_living_room_sleep_mode",
        "switch.adaptive_lighting_bedroom_sleep_mode",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_OFF


async def test_sleep_toggle_applies_restored_state_at_startup(
    hass: HomeAssistant,
) -> None:
    """Verify startup applies the input boolean's restored state."""
    _prepare_hass_startup(hass)
    summary = (
        'Toggle multiple Adaptive Lighting switches to "sleep mode" using an '
        "<code>input_boolean.sleep_mode</code>."
    )
    automation_config = _yaml_documents(summary)[0]
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"sleep_mode": {}}},
    )
    await setup_switch(hass, {CONF_NAME: "Living Room"})
    await hass.services.async_call(
        "input_boolean",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "input_boolean.sleep_mode"},
        blocking=True,
    )
    await _setup_automation(hass, automation_config)

    await hass.async_start()
    await hass.async_block_till_done()
    state = hass.states.get("switch.adaptive_lighting_living_room_sleep_mode")
    assert state is not None
    assert state.state == STATE_ON


async def test_alarm_script_updates_its_profile_once(
    hass: HomeAssistant,
    freezer,
) -> None:
    """Execute the alarm script and verify one profile update with a 12-hour day."""
    summary = "Set sunrise and sunset from an alarm."
    script_config = _yaml_documents(summary)[0]
    freezer.move_to(
        datetime(2026, 11, 1, 0, 30, tzinfo=dt_util.DEFAULT_TIME_ZONE),
    )
    _, adaptive_switch = await setup_switch(hass, {CONF_NAME: "Alarm Lights"})
    await _setup_script(hass, script_config)
    calls = []

    def record_service_call(event) -> None:
        if (
            event.data["domain"] == DOMAIN
            and event.data["service"] == "change_switch_settings"
        ):
            calls.append(event)

    hass.bus.async_listen(EVENT_CALL_SERVICE, record_service_call)
    await hass.services.async_call(
        script.DOMAIN,
        "set_adaptive_lighting_alarm_times",
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    sunrise = adaptive_switch._sun_light_settings.sunrise_time
    sunset = adaptive_switch._sun_light_settings.sunset_time
    assert sunrise is not None
    assert sunset is not None
    sunrise_seconds = sunrise.hour * 3600 + sunrise.minute * 60 + sunrise.second
    sunset_seconds = sunset.hour * 3600 + sunset.minute * 60 + sunset.second
    assert (sunset_seconds - sunrise_seconds) % (24 * 3600) == 12 * 3600
