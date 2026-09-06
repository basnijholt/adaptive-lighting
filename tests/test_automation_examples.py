"""Execute the automation examples published in README.md."""

from __future__ import annotations

import asyncio
import re
import shutil
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
    CONF_AUTORESET_CONTROL,
    CONF_BRIGHTNESS_MODE,
    CONF_BRIGHTNESS_MODE_TIME_DARK,
    CONF_BRIGHTNESS_MODE_TIME_LIGHT,
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
    CONF_TAKE_OVER_CONTROL_MODE,
    CONF_TRANSITION,
    DOMAIN,
)
from homeassistant.components.blueprint.models import Blueprint
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
from homeassistant.util import yaml as yaml_util

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


def _blueprint_config(hass, tmp_path, filename, inputs, alias):
    """Install an actual published blueprint for Home Assistant to load."""
    relative_path = f"adaptive_lighting/{filename}"
    hass.config.config_dir = str(tmp_path)
    destination = tmp_path / "blueprints" / "automation" / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(README.parent / "blueprints" / "automation" / filename, destination)
    return {
        "alias": alias,
        "use_blueprint": {"path": relative_path, "input": inputs},
    }


@pytest.fixture(params=["yaml", "blueprint"])
def published_automation(hass: HomeAssistant, tmp_path: Path, request):
    """Use the published YAML or blueprint with the same behavioral assertions."""

    def config(summary, filename, inputs):
        yaml_config = _yaml_documents(summary)[-1]
        if request.param == "yaml":
            return yaml_config
        return _blueprint_config(
            hass,
            tmp_path,
            filename,
            inputs,
            yaml_config[0]["alias"],
        )

    return config


@pytest.mark.parametrize(
    "path",
    sorted((README.parent / "blueprints" / "automation").glob("*.yaml")),
    ids=lambda path: path.stem,
)
def test_published_blueprint_schema(path: Path) -> None:
    """Validate every published blueprint with Home Assistant's own schema."""
    blueprint = Blueprint(
        yaml_util.load_yaml(str(path)),
        expected_domain=automation.DOMAIN,
        schema=automation.config.AUTOMATION_BLUEPRINT_SCHEMA,
    )
    assert blueprint.validate() is None


@pytest.fixture(params=["yaml", "blueprint", "blueprint-custom-minimum"])
def minimum_automation_config(hass: HomeAssistant, tmp_path: Path, request):
    """Run the same behavior checks against both published formats."""
    if request.param == "yaml":
        return _yaml_documents(
            "Turn a light off when its adaptive brightness target reaches the minimum.",
        )[0]
    inputs = {
        "adaptive_switch": "switch.adaptive_lighting_living_room",
        "brightness_switch": "switch.adaptive_lighting_living_room_adapt_brightness",
        "light_entity": "light.living_room",
    }
    if request.param == "blueprint-custom-minimum":
        inputs["minimum_pct"] = 10
    return _blueprint_config(
        hass,
        tmp_path,
        "turn_off_at_minimum.yaml",
        inputs,
        "Turn off at minimum",
    )


@pytest.mark.parametrize("manual_control", [False, True])
@pytest.mark.parametrize("trigger_kind", ["interval", "sleep"])
@patch(
    "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
    new=dt_util.utcnow,
)
async def test_minimum_brightness_power_automation(
    hass: HomeAssistant,
    freezer,
    manual_control: bool,
    trigger_kind: str,
    minimum_automation_config,
) -> None:
    """Catch exact-float comparisons, repeated power actions, or lost manual control."""
    minimum = (
        minimum_automation_config.get("use_blueprint", {})
        .get("input", {})
        .get("minimum_pct", 1)
        if isinstance(minimum_automation_config, dict)
        else 1
    )
    freezer.move_to(datetime(2026, 9, 6, 18, 58, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    await _setup_template_lights(hass, ["Living Room"])
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.living_room", ATTR_BRIGHTNESS: 77},
        blocking=True,
    )
    _, adaptive_switch = await setup_switch(
        hass,
        {
            CONF_NAME: "Living Room",
            CONF_LIGHTS: ["light.living_room"],
            CONF_MIN_BRIGHTNESS: minimum,
            CONF_MAX_BRIGHTNESS: 100,
            CONF_BRIGHTNESS_MODE: "linear",
            CONF_BRIGHTNESS_MODE_TIME_DARK: timedelta(hours=1),
            CONF_BRIGHTNESS_MODE_TIME_LIGHT: timedelta(hours=1),
            CONF_SUNRISE_TIME: "06:00:00",
            CONF_SUNSET_TIME: "18:00:00",
            CONF_TRANSITION: 0,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    if manual_control:
        await hass.services.async_call(
            DOMAIN,
            "set_manual_control",
            {ATTR_ENTITY_ID: adaptive_switch.entity_id, "manual_control": True},
            blocking=True,
        )
    await _setup_automation(hass, minimum_automation_config)
    off_calls = []

    @callback
    def record_off(event: Event) -> None:
        if (
            event.data["domain"] == LIGHT_DOMAIN
            and event.data["service"] == SERVICE_TURN_OFF
        ):
            off_calls.append(event.data["service_data"])

    hass.bus.async_listen(EVENT_CALL_SERVICE, record_off)
    assert hass.states.get("light.living_room").state == STATE_ON
    assert adaptive_switch.extra_state_attributes["brightness_pct"] > minimum + 1

    # The curve is above the minimum, but rounds to the same brightness command.
    freezer.move_to(datetime(2026, 9, 6, 18, 59, 50, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    if trigger_kind == "sleep":
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "switch.adaptive_lighting_living_room_sleep_mode"},
            blocking=True,
        )
    else:
        await adaptive_switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    if trigger_kind == "sleep":
        assert adaptive_switch.extra_state_attributes["brightness_pct"] == 1
    else:
        assert (
            minimum
            < adaptive_switch.extra_state_attributes["brightness_pct"]
            < minimum + 0.2
        )
    # The default sleep-mode policy clears manual control before publishing its target.
    should_turn_off = not manual_control or trigger_kind == "sleep"
    assert hass.states.get("light.living_room").state == (
        STATE_OFF if should_turn_off else STATE_ON
    )
    assert len(off_calls) == int(should_turn_off)

    # Further target changes inside the minimum command range do not retrigger.
    freezer.move_to(datetime(2026, 9, 6, 19, 1, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    await adaptive_switch._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert adaptive_switch.extra_state_attributes["brightness_pct"] == (
        1 if trigger_kind == "sleep" else minimum
    )
    assert len(off_calls) == int(should_turn_off)

    if should_turn_off:
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.living_room"},
            blocking=True,
        )
        await hass.async_block_till_done()
        assert hass.states.get("light.living_room").state == STATE_ON
        assert len(off_calls) == 1


@pytest.mark.parametrize("previous", [None, "unknown", "unavailable"])
async def test_minimum_brightness_ignores_missing_previous_target(
    hass: HomeAssistant,
    previous: str | None,
    minimum_automation_config,
) -> None:
    """A missing target must not become a numeric crossing during recovery."""
    await _setup_template_lights(hass, ["Living Room"])
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.living_room"},
        blocking=True,
    )
    _, adaptive_switch = await setup_switch(
        hass,
        {
            CONF_NAME: "Living Room",
            CONF_LIGHTS: ["light.living_room"],
            CONF_MIN_BRIGHTNESS: 1,
            CONF_MAX_BRIGHTNESS: 1,
            CONF_TRANSITION: 0,
            CONF_INITIAL_TRANSITION: 0,
        },
    )
    await _setup_automation(hass, minimum_automation_config)
    attributes = dict(hass.states.get(adaptive_switch.entity_id).attributes)
    assert attributes["brightness_pct"] == 1
    if previous is None:
        hass.states.async_remove(adaptive_switch.entity_id)
    else:
        hass.states.async_set(
            adaptive_switch.entity_id,
            previous,
            {**attributes, "brightness_pct": previous},
        )
    await hass.async_block_till_done()
    hass.states.async_set(adaptive_switch.entity_id, STATE_ON, attributes)
    await hass.async_block_till_done()
    assert hass.states.get("light.living_room").state == STATE_ON


@pytest.mark.parametrize("previous_manual", [None, "color", "brightness"])
@patch(
    "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow",
    new=dt_util.utcnow,
)
async def test_minimum_manual_control_lifecycle(
    hass: HomeAssistant,
    freezer,
    published_automation,
    previous_manual: str | None,
) -> None:
    """Pause at the calculated floor, preserve other flags, and reset on off/on."""
    freezer.move_to(datetime(2026, 9, 6, 18, 58, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    config = published_automation(
        "Pause brightness at the minimum using manual control.",
        "manual_control_at_minimum.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_living_room",
            "brightness_switch": "switch.adaptive_lighting_living_room_adapt_brightness",
            "light_entity": "light.living_room",
        },
    )
    await _setup_template_lights(hass, ["Living Room"])
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.living_room", ATTR_BRIGHTNESS: 77},
        blocking=True,
    )
    _, profile = await setup_switch(
        hass,
        {
            CONF_NAME: "Living Room",
            CONF_LIGHTS: ["light.living_room"],
            CONF_MIN_BRIGHTNESS: 1,
            CONF_MAX_BRIGHTNESS: 100,
            CONF_MIN_COLOR_TEMP: 3000,
            CONF_MAX_COLOR_TEMP: 3000,
            CONF_BRIGHTNESS_MODE: "linear",
            CONF_BRIGHTNESS_MODE_TIME_DARK: timedelta(hours=1),
            CONF_BRIGHTNESS_MODE_TIME_LIGHT: timedelta(hours=1),
            CONF_SUNRISE_TIME: "06:00:00",
            CONF_SUNSET_TIME: "18:00:00",
            CONF_TRANSITION: 0,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TAKE_OVER_CONTROL_MODE: "pause_changed",
        },
    )
    if previous_manual:
        await hass.services.async_call(
            DOMAIN,
            "set_manual_control",
            {ATTR_ENTITY_ID: profile.entity_id, "manual_control": previous_manual},
            blocking=True,
        )
    await _setup_automation(hass, config)
    manual_calls = []

    @callback
    def record_manual_call(event: Event) -> None:
        if (
            event.data["domain"] == DOMAIN
            and event.data["service"] == "set_manual_control"
        ):
            manual_calls.append(event.data["service_data"])

    hass.bus.async_listen(EVENT_CALL_SERVICE, record_manual_call)
    freezer.move_to(datetime(2026, 9, 6, 18, 59, 50, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    await profile._async_update_at_interval_action()
    await hass.async_block_till_done()
    flags = profile.manager.get_manual_control_attributes("light.living_room")
    assert LightControlAttributes.BRIGHTNESS in flags
    assert (LightControlAttributes.COLOR in flags) is (previous_manual == "color")
    assert len(manual_calls) == (0 if previous_manual == "brightness" else 1)
    paused_brightness = hass.states.get("light.living_room").attributes[ATTR_BRIGHTNESS]
    assert profile.is_on
    assert profile.adapt_brightness_switch.is_on
    if previous_manual != "brightness":
        assert paused_brightness == 3

    freezer.move_to(datetime(2026, 9, 6, 19, 1, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    await profile._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert len(manual_calls) == (0 if previous_manual == "brightness" else 1)
    await hass.services.async_call(
        DOMAIN,
        "change_switch_settings",
        {
            ATTR_ENTITY_ID: profile.entity_id,
            CONF_MIN_BRIGHTNESS: 100,
            CONF_MAX_BRIGHTNESS: 100,
            CONF_MIN_COLOR_TEMP: 5000,
            CONF_MAX_COLOR_TEMP: 5000,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get("light.living_room")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == paused_brightness
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == pytest.approx(
        3000 if previous_manual == "color" else 5000,
        abs=5,
    )
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "light.living_room"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert not profile.manager.get_manual_control_attributes("light.living_room")
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.living_room"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("light.living_room").attributes[ATTR_BRIGHTNESS] == 255

    # Another crossing can pause again, but clearing it at the floor must stick.
    await hass.services.async_call(
        DOMAIN,
        "change_switch_settings",
        {
            ATTR_ENTITY_ID: profile.entity_id,
            CONF_MIN_BRIGHTNESS: 1,
            CONF_MAX_BRIGHTNESS: 1,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert profile.manager.get_manual_control_attributes("light.living_room")
    await hass.services.async_call(
        DOMAIN,
        "set_manual_control",
        {ATTR_ENTITY_ID: profile.entity_id, "manual_control": False},
        blocking=True,
    )
    await profile._async_update_at_interval_action()
    await hass.async_block_till_done()
    assert not profile.manager.get_manual_control_attributes("light.living_room")

    if previous_manual is None:
        await hass.services.async_call(
            DOMAIN,
            "change_switch_settings",
            {
                ATTR_ENTITY_ID: profile.entity_id,
                CONF_MIN_BRIGHTNESS: 50,
                CONF_MAX_BRIGHTNESS: 50,
                CONF_AUTORESET_CONTROL: 1,
            },
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "change_switch_settings",
            {
                ATTR_ENTITY_ID: profile.entity_id,
                CONF_MIN_BRIGHTNESS: 1,
                CONF_MAX_BRIGHTNESS: 1,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        assert profile.manager.get_manual_control_attributes("light.living_room")
        cleared, remove_listener = _state_waiter(
            hass,
            profile.entity_id,
            lambda state: state.attributes.get("manual_control_brightness") == [],
        )
        freezer.tick(timedelta(seconds=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await asyncio.wait_for(cleared, timeout=2)
        remove_listener()
        await hass.async_block_till_done()
        assert not profile.manager.get_manual_control_attributes("light.living_room")


@pytest.mark.parametrize(
    "abort_entity",
    [
        "light.living_room",
        "switch.adaptive_lighting_living_room",
        "switch.adaptive_lighting_living_room_adapt_brightness",
    ],
)
async def test_minimum_manual_control_aborts_when_disabled(
    hass: HomeAssistant,
    published_automation,
    abort_entity: str,
) -> None:
    """Abandon a pending wait immediately when the light or profile is disabled."""
    config = published_automation(
        "Pause brightness at the minimum using manual control.",
        "manual_control_at_minimum.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_living_room",
            "brightness_switch": "switch.adaptive_lighting_living_room_adapt_brightness",
            "light_entity": "light.living_room",
        },
    )
    await _setup_template_lights(hass, ["Living Room"])
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.living_room", ATTR_BRIGHTNESS: 128},
        blocking=True,
    )
    _, profile = await setup_switch(
        hass,
        {
            CONF_NAME: "Living Room",
            CONF_LIGHTS: ["light.living_room"],
            CONF_MIN_BRIGHTNESS: 50,
            CONF_MAX_BRIGHTNESS: 50,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_TAKE_OVER_CONTROL_MODE: "pause_changed",
        },
    )
    await _setup_automation(hass, config)
    waiting, remove_listener = _state_waiter(
        hass,
        "automation.adaptive_lighting_pause_brightness_at_minimum",
        lambda state: state.attributes.get("current") == 1,
    )
    state = hass.states.get(profile.entity_id)
    hass.states.async_set(
        profile.entity_id,
        STATE_ON,
        {**state.attributes, "brightness_pct": 1},
    )
    await asyncio.wait_for(waiting, timeout=1)
    remove_listener()
    assert not profile.manager.get_manual_control_attributes("light.living_room")
    stopped, remove_stopped = _state_waiter(
        hass,
        "automation.adaptive_lighting_pause_brightness_at_minimum",
        lambda state: state.attributes.get("current") == 0,
    )
    await hass.services.async_call(
        abort_entity.split(".", maxsplit=1)[0],
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: abort_entity},
        blocking=True,
    )
    try:
        await asyncio.wait_for(stopped, timeout=1)
    finally:
        remove_stopped()
        if stopped.cancelled():
            await hass.services.async_call(
                automation.DOMAIN,
                SERVICE_TURN_OFF,
                {
                    ATTR_ENTITY_ID: "automation.adaptive_lighting_pause_brightness_at_minimum",
                },
                blocking=True,
            )
    await hass.async_block_till_done()
    assert not profile.manager.get_manual_control_attributes("light.living_room")
    assert (
        hass.states.get(
            "automation.adaptive_lighting_pause_brightness_at_minimum",
        ).attributes["current"]
        == 0
    )

    await hass.services.async_call(
        abort_entity.split(".", maxsplit=1)[0],
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: abort_entity},
        blocking=True,
    )
    await profile._async_update_at_interval_action()
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN,
        "change_switch_settings",
        {
            ATTR_ENTITY_ID: profile.entity_id,
            CONF_MIN_BRIGHTNESS: 1,
            CONF_MAX_BRIGHTNESS: 1,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert (
        profile.manager.get_manual_control_attributes("light.living_room")
        == LightControlAttributes.BRIGHTNESS
    )


async def test_schedule_profile_executes_blocks_and_restore(
    hass: HomeAssistant,
    published_automation,
) -> None:
    """Catch ignored attribute changes, incomplete restore, or switch coupling."""
    summary = "Use a Schedule helper as a step-based custom lighting profile."
    automation_config = published_automation(
        summary,
        "schedule_profile.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_living_room",
            "schedule_entity": "schedule.adaptive_lighting_profile",
        },
    )
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


async def test_schedule_profile_reapplies_at_startup(
    hass: HomeAssistant,
    published_automation,
) -> None:
    """Verify startup applies the already-active schedule block."""
    _prepare_hass_startup(hass)
    summary = "Use a Schedule helper as a step-based custom lighting profile."
    automation_config = published_automation(
        summary,
        "schedule_profile.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_living_room",
            "schedule_entity": "schedule.adaptive_lighting_profile",
        },
    )
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


async def test_lux_profile_executes_hysteresis(
    hass: HomeAssistant,
    published_automation,
) -> None:
    """Catch missing threshold actions or changes inside the dead band."""
    summary = (
        "Reduce daytime brightness when an illuminance sensor detects strong daylight."
    )
    automation_config = published_automation(
        summary,
        "daylight_limit.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_living_room",
            "illuminance_sensor": "sensor.living_room_illuminance",
        },
    )
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
    published_automation,
) -> None:
    """Catch a startup hang or failure to recover from an unknown sensor."""
    _prepare_hass_startup(hass)
    summary = (
        "Reduce daytime brightness when an illuminance sensor detects strong daylight."
    )
    automation_config = published_automation(
        summary,
        "daylight_limit.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_living_room",
            "illuminance_sensor": "sensor.living_room_illuminance",
        },
    )
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


@pytest.mark.parametrize(("high_lux", "low_lux"), [(400, 250), (200, 300), (200, 200)])
async def test_daylight_blueprint_custom_inputs(
    hass: HomeAssistant,
    tmp_path: Path,
    high_lux: int,
    low_lux: int,
) -> None:
    """Use selected entities and limits; invalid threshold order must do nothing."""
    config = _blueprint_config(
        hass,
        tmp_path,
        "daylight_limit.yaml",
        {
            "adaptive_switch": "switch.adaptive_lighting_office",
            "illuminance_sensor": "sensor.office_illuminance",
            "high_lux": high_lux,
            "low_lux": low_lux,
            "daylight_maximum": 20,
            "normal_maximum": 70,
        },
        "Custom daylight",
    )
    _, adaptive_switch = await setup_switch(
        hass,
        {CONF_NAME: "Office", CONF_MAX_BRIGHTNESS: 80},
    )
    hass.states.async_set("sensor.office_illuminance", "300")
    await _setup_automation(hass, config)
    assert hass.states.get("automation.custom_daylight") is not None
    valid_thresholds = high_lux > low_lux
    for lux, expected in [(500, 20), (300, 20), (100, 70)]:
        hass.states.async_set("sensor.office_illuminance", str(lux))
        await hass.async_block_till_done()
        assert adaptive_switch._sun_light_settings.max_brightness == (
            expected if valid_thresholds else 80
        )


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
    published_automation,
) -> None:
    """Execute state triggers against fresh child entity IDs."""
    summary = (
        'Toggle multiple Adaptive Lighting switches to "sleep mode" using an '
        "<code>input_boolean.sleep_mode</code>."
    )
    automation_config = published_automation(
        summary,
        "sleep_mode.yaml",
        {
            "sleep_helper": "input_boolean.sleep_mode",
            "sleep_switches": [
                "switch.adaptive_lighting_living_room_sleep_mode",
                "switch.adaptive_lighting_bedroom_sleep_mode",
            ],
        },
    )
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
    published_automation,
) -> None:
    """Verify startup applies the input boolean's restored state."""
    _prepare_hass_startup(hass)
    summary = (
        'Toggle multiple Adaptive Lighting switches to "sleep mode" using an '
        "<code>input_boolean.sleep_mode</code>."
    )
    automation_config = published_automation(
        summary,
        "sleep_mode.yaml",
        {
            "sleep_helper": "input_boolean.sleep_mode",
            "sleep_switches": [
                "switch.adaptive_lighting_living_room_sleep_mode",
                "switch.adaptive_lighting_bedroom_sleep_mode",
            ],
        },
    )
    assert await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"sleep_mode": {}}},
    )
    await setup_switch(hass, {CONF_NAME: "Living Room"})
    await setup_switch(hass, {CONF_NAME: "Bedroom"})
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
