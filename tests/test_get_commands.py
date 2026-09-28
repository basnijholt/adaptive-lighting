"""Tests for the `adaptive_lighting.get_commands` service."""

import datetime
import json
import re
from pathlib import Path
from unittest.mock import patch

import homeassistant.util.dt as dt_util
import pytest
import yaml
from homeassistant.components.adaptive_lighting.const import (
    ATTR_ADAPT_BRIGHTNESS,
    ATTR_ADAPT_COLOR,
    CONF_ADAPT_ONLY_ON_BARE_TURN_ON,
    CONF_ADAPT_UNTIL_SLEEP,
    CONF_COMMANDS_TIME,
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_PREFER_RGB_COLOR,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_RGB_OR_COLOR_TEMP,
    CONF_TRANSITION,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_RGB_COLOR,
    DOMAIN,
    SERVICE_APPLY,
    SERVICE_GET_COMMANDS,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from .test_switch import (
    CONF_INTERCEPT,
    ENTITY_LIGHT_1,
    ENTITY_LIGHT_2,
    ENTITY_LIGHT_3,
    SUNRISE,
    _track_adaptive_light_calls,
    async_process_ha_core_config,
    cleanup,  # noqa: F401  # fixture
    reset_time_zone,  # noqa: F401  # fixture
    setup_lights,
    setup_lights_and_switch,
    setup_switch,
)

UTCNOW = "homeassistant.components.adaptive_lighting.color_and_brightness.utcnow"

pytestmark = pytest.mark.usefixtures("cleanup")


def _noon() -> datetime.datetime:
    """Noon (in the test's time zone) on the day of the fixed sun events."""
    return SUNRISE.replace(hour=12, tzinfo=dt_util.DEFAULT_TIME_ZONE).astimezone(
        dt_util.UTC,
    )


def _today_at(switch, time: datetime.time) -> datetime.datetime:
    """The time of day today, in UTC, in the switch's time zone."""
    tz = switch._sun_light_settings.timezone
    return dt_util.as_utc(
        datetime.datetime.combine(dt_util.now(tz).date(), time, tzinfo=tz),
    )


async def _get_commands(hass, switch, **data):
    return await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_COMMANDS,
        {ATTR_ENTITY_ID: switch.entity_id, **data},
        blocking=True,
        return_response=True,
    )


async def test_get_commands_match_what_apply_sends(hass):
    """With the switch's defaults, the commands are exactly what `apply` sends."""
    switch, _ = await setup_lights_and_switch(hass)
    # In the evening, when brightness and color change by the minute
    with patch(UTCNOW, return_value=_today_at(switch, datetime.time(23, 0))):
        commands = await _get_commands(hass, switch)
        calls = _track_adaptive_light_calls(hass)
        await hass.services.async_call(
            DOMAIN,
            SERVICE_APPLY,
            {ATTR_ENTITY_ID: switch.entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert set(commands) == set(switch.lights)
    sent = {call[ATTR_ENTITY_ID]: call for call in calls}
    for light in switch.lights:
        assert [c["service_data"] for c in commands[light]] == [sent[light]]
        assert commands[light][0]["delay"] == 0


async def test_get_commands_for_a_time(hass):
    """The commands for a time are those the regular adaptation makes at it."""
    switch, _ = await setup_lights_and_switch(hass)
    time = datetime.time(23, 30)
    with patch(UTCNOW, return_value=_today_at(switch, time)):
        at_that_time = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    with patch(UTCNOW, return_value=_noon()):
        now = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
        for_time = await _get_commands(
            hass,
            switch,
            lights=[ENTITY_LIGHT_1],
            **{CONF_COMMANDS_TIME: "23:30:00"},
        )
    assert for_time == at_that_time
    assert for_time != now
    assert list(for_time) == [ENTITY_LIGHT_1]


async def test_get_commands_is_read_only(hass):
    """Nothing is sent, and manual control and the switch's settings are kept."""
    switch, _ = await setup_lights_and_switch(hass)
    unmarked = await _get_commands(hass, switch, **{CONF_COMMANDS_TIME: "23:30:00"})
    switch.manager.set_manual_control_attributes(ENTITY_LIGHT_1)
    manual_control = dict(switch.manager.manual_control)
    settings = dict(switch._settings)
    calls = _track_adaptive_light_calls(hass, ours_only=False)
    commands = await _get_commands(hass, switch, **{CONF_COMMANDS_TIME: "23:30:00"})
    await hass.async_block_till_done()
    assert calls == []
    assert switch.manager.manual_control == manual_control
    assert switch._settings == settings
    # Manual control doesn't change the commands
    assert commands == unmarked


async def test_get_commands_split(hass):
    """With separate commands, they're returned in order with the waits between."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_SEPARATE_TURN_ON_COMMANDS: True, CONF_SEND_SPLIT_DELAY: 100},
        all_lights=True,
    )
    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_3],  # supports transitions
        **{CONF_TRANSITION: 2},
    )
    calls = commands[ENTITY_LIGHT_3]
    assert [set(c["service_data"]) for c in calls] == [
        {ATTR_ENTITY_ID, ATTR_BRIGHTNESS, ATTR_TRANSITION},
        {ATTR_ENTITY_ID, ATTR_COLOR_TEMP_KELVIN, ATTR_TRANSITION},
    ]
    assert [c["service_data"][ATTR_TRANSITION] for c in calls] == [1, 1]
    assert [c["delay"] for c in calls] == [0, pytest.approx(1.1)]


async def test_get_commands_follow_adapt_switches(hass):
    """What's adapted follows the switch's adapt switches, unless specified."""
    switch, _ = await setup_lights_and_switch(hass)
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: switch.adapt_color_switch.entity_id},
        blocking=True,
    )
    commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    (call,) = commands[ENTITY_LIGHT_1]
    assert ATTR_BRIGHTNESS in call["service_data"]
    assert ATTR_COLOR_TEMP_KELVIN not in call["service_data"]
    assert ATTR_RGB_COLOR not in call["service_data"]

    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{ATTR_ADAPT_COLOR: True, ATTR_ADAPT_BRIGHTNESS: False},
    )
    (call,) = commands[ENTITY_LIGHT_1]
    assert ATTR_BRIGHTNESS not in call["service_data"]
    assert ATTR_COLOR_TEMP_KELVIN in call["service_data"]

    # Nothing to adapt
    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{ATTR_ADAPT_BRIGHTNESS: False},
    )
    assert commands == {ENTITY_LIGHT_1: []}


async def test_get_commands_color_choice(hass):
    """RGB follows the switch's `prefer_rgb_color`; dimmers get no color."""
    switch, _ = await setup_lights_and_switch(hass, {CONF_PREFER_RGB_COLOR: True})
    commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    (call,) = commands[ENTITY_LIGHT_1]
    assert isinstance(call["service_data"][ATTR_RGB_COLOR], list)
    assert ATTR_COLOR_TEMP_KELVIN not in call["service_data"]

    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{CONF_PREFER_RGB_COLOR: False},
    )
    (call,) = commands[ENTITY_LIGHT_1]
    assert ATTR_COLOR_TEMP_KELVIN in call["service_data"]

    with patch(
        "homeassistant.components.adaptive_lighting.switch._supported_features",
        return_value={"brightness"},
    ):
        commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    (call,) = commands[ENTITY_LIGHT_1]
    assert set(call["service_data"]) == {ATTR_ENTITY_ID, ATTR_BRIGHTNESS}


async def test_get_commands_sleep_mode(hass):
    """In sleep mode, the commands are for the sleep settings, whatever the time."""
    switch, _ = await setup_lights_and_switch(hass)
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
        blocking=True,
    )
    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{CONF_COMMANDS_TIME: "12:00:00"},
    )
    (call,) = commands[ENTITY_LIGHT_1]
    assert call["service_data"][ATTR_BRIGHTNESS] == round(
        255 * DEFAULT_SLEEP_BRIGHTNESS / 100,
    )


async def test_get_commands_all_lights_of_switches(hass):
    """Without lights, all lights of the switch, whether on or off."""
    switch, _ = await setup_lights_and_switch(hass)
    await hass.services.async_call(
        "light",
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_2},
        blocking=True,
    )
    commands = await _get_commands(hass, switch)
    assert set(commands) == {ENTITY_LIGHT_1, ENTITY_LIGHT_2}
    assert all(commands.values())


async def test_get_commands_needs_response(hass):
    """It only returns data, so calling it without asking for it is an error."""
    switch, _ = await setup_lights_and_switch(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_COMMANDS,
            {ATTR_ENTITY_ID: switch.entity_id},
            blocking=True,
        )


async def test_get_commands_far_from_utc(
    hass,
    reset_time_zone,  # noqa: F811  # pylint: disable=redefined-outer-name
):
    """A time is calculated like the regular adaptation, also in UTC+14."""
    await async_process_ha_core_config(
        hass,
        {
            "latitude": 1.87,
            "longitude": -157.4,
            "time_zone": "Pacific/Kiritimati",
            "country": "KI",
        },
    )
    await setup_lights(hass)
    _, switch = await setup_switch(
        hass,
        {CONF_LIGHTS: [ENTITY_LIGHT_1], CONF_INITIAL_TRANSITION: 0},
    )
    for time in (datetime.time(0, 10), datetime.time(12)):
        with patch(UTCNOW, return_value=_today_at(switch, time)):
            at_that_time = await _get_commands(hass, switch)
        for_time = await _get_commands(hass, switch, **{CONF_COMMANDS_TIME: time})
        assert for_time == at_that_time


async def test_get_commands_time_like_now_with_transition(hass):
    """With a transition, a time is (like now) for when the transition ends."""
    switch, _ = await setup_lights_and_switch(hass, all_lights=True)
    time = datetime.time(21, 58)
    data = {"lights": [ENTITY_LIGHT_3], CONF_TRANSITION: 300}  # supports transitions
    with patch(UTCNOW, return_value=_today_at(switch, time)):
        at_that_time = await _get_commands(hass, switch, **data)
    for_time = await _get_commands(hass, switch, **data, **{CONF_COMMANDS_TIME: time})
    assert for_time == at_that_time
    (call,) = for_time[ENTITY_LIGHT_3]
    assert call["service_data"][ATTR_TRANSITION] == 300


async def test_get_commands_for_a_daytime(hass):
    """Also during the day, where the color temperature changes by the minute."""
    switch, _ = await setup_lights_and_switch(hass)
    time = datetime.time(6, 30)
    with patch(UTCNOW, return_value=_today_at(switch, time)):
        at_that_time = await _get_commands(hass, switch)
    for_time = await _get_commands(hass, switch, **{CONF_COMMANDS_TIME: time})
    assert for_time == at_that_time
    with patch(UTCNOW, return_value=_today_at(switch, datetime.time(7, 30))):
        an_hour_later = await _get_commands(hass, switch)
    assert for_time != an_hour_later


async def test_get_commands_split_without_transition_support(hass):
    """A light without transitions gets none, and only the split delay between."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_SEPARATE_TURN_ON_COMMANDS: True, CONF_SEND_SPLIT_DELAY: 100},
    )
    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{CONF_TRANSITION: 2},
    )
    calls = commands[ENTITY_LIGHT_1]
    assert all(ATTR_TRANSITION not in c["service_data"] for c in calls)
    assert [c["delay"] for c in calls] == [0, pytest.approx(0.1)]


async def test_get_commands_sleep_rgb(hass):
    """In sleep mode with RGB, the sleep color is sent as RGB."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_SLEEP_RGB_OR_COLOR_TEMP: "rgb_color"},
    )
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: switch.sleep_mode_switch.entity_id},
        blocking=True,
    )
    commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    (call,) = commands[ENTITY_LIGHT_1]
    assert call["service_data"][ATTR_RGB_COLOR] == list(DEFAULT_SLEEP_RGB_COLOR)


async def test_get_commands_rgb_until_sleep(hass):
    """After sunset with `transition_until_sleep` and RGB, the color is RGB."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_SLEEP_RGB_OR_COLOR_TEMP: "rgb_color", CONF_ADAPT_UNTIL_SLEEP: True},
    )
    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{CONF_COMMANDS_TIME: "23:30:00"},
    )
    (call,) = commands[ENTITY_LIGHT_1]
    assert ATTR_RGB_COLOR in call["service_data"]
    assert ATTR_COLOR_TEMP_KELVIN not in call["service_data"]


async def test_get_commands_clamps_color_temp(hass):
    """The color temperature is clamped to what the light supports."""
    switch, _ = await setup_lights_and_switch(hass, {CONF_MIN_COLOR_TEMP: 1000})
    commands = await _get_commands(
        hass,
        switch,
        lights=[ENTITY_LIGHT_1],
        **{CONF_COMMANDS_TIME: "23:30:00"},
    )
    (call,) = commands[ENTITY_LIGHT_1]
    minimum = hass.states.get(ENTITY_LIGHT_1).attributes["min_color_temp_kelvin"]
    assert minimum > 1000
    assert call["service_data"][ATTR_COLOR_TEMP_KELVIN] == minimum


async def test_get_commands_several_switches(hass):
    """Several switches' lights are combined, but a shared light is an error."""
    await setup_lights(hass)
    _, switch_1 = await setup_switch(
        hass,
        {CONF_NAME: "one", CONF_LIGHTS: [ENTITY_LIGHT_1], CONF_INITIAL_TRANSITION: 0},
    )
    _, switch_2 = await setup_switch(
        hass,
        {CONF_NAME: "two", CONF_LIGHTS: [ENTITY_LIGHT_2], CONF_INITIAL_TRANSITION: 0},
    )
    commands = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_COMMANDS,
        {ATTR_ENTITY_ID: [switch_1.entity_id, switch_2.entity_id]},
        blocking=True,
        return_response=True,
    )
    assert set(commands) == {ENTITY_LIGHT_1, ENTITY_LIGHT_2}

    _, switch_3 = await setup_switch(
        hass,
        {CONF_NAME: "three", CONF_LIGHTS: [ENTITY_LIGHT_1]},
    )
    with pytest.raises(ServiceValidationError, match="more than one"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_COMMANDS,
            {ATTR_ENTITY_ID: [switch_1.entity_id, switch_3.entity_id]},
            blocking=True,
            return_response=True,
        )


@pytest.mark.parametrize("expand", [True, False])
async def test_get_commands_light_groups(hass, expand):
    """Light groups are expanded to their members, as the switch does."""
    await setup_lights(hass, with_group=True)
    _, switch = await setup_switch(
        hass,
        {CONF_LIGHTS: ["light.light_group"], CONF_EXPAND_LIGHT_GROUPS: expand},
    )
    commands = await _get_commands(hass, switch)
    expected = {"light.light_4", "light.light_5"} if expand else {"light.light_group"}
    assert set(commands) == expected


async def test_get_commands_unknown_lights(hass):
    """Unknown lights, e.g. typos, are an error rather than left out."""
    switch, _ = await setup_lights_and_switch(hass)
    with pytest.raises(ServiceValidationError, match=r"light\.kitchn"):
        await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1, "light.kitchn"])


def _readme_example() -> dict:
    """The README's example script for `adaptive_lighting.get_commands`."""
    readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text()
    section = readme[readme.index("#### `adaptive_lighting.get_commands`") :]
    match = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert match is not None
    return yaml.safe_load(match.group(1))


@pytest.mark.parametrize(
    ("intercept", "split"),
    [(False, False), (True, False), (False, True)],
)
async def test_get_commands_readme_example(hass, intercept, split):
    """The README's example script makes the calls, for lights that are on."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {
            CONF_INTERCEPT: intercept,
            CONF_SEPARATE_TURN_ON_COMMANDS: split,
            CONF_SEND_SPLIT_DELAY: 100,
        },
    )
    await hass.services.async_call(
        "light",
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_LIGHT_2},
        blocking=True,
    )
    config = _readme_example()
    # At noon, for a time with other settings than now
    config["sequence"][0]["data"][ATTR_ENTITY_ID] = switch.entity_id
    config["sequence"][0]["data"]["time"] = "23:30:00"
    assert await async_setup_component(
        hass,
        "script",
        {"script": {"example": config}},
    )
    with patch(UTCNOW, return_value=_noon()):
        await switch._update_attrs_and_maybe_adapt_lights(
            context=switch.create_context("test"),
            transition=0,
            force=True,
        )
        await hass.async_block_till_done()
        before = dict(hass.states.get(ENTITY_LIGHT_1).attributes)
        commands = await _get_commands(
            hass,
            switch,
            **{CONF_COMMANDS_TIME: "23:30:00"},
        )
        await hass.services.async_call("script", "example", blocking=True)
        await hass.async_block_till_done()
    calls = commands[ENTITY_LIGHT_1]
    assert [c["delay"] > 0 for c in calls] == ([False, True] if split else [False])
    expected = {}
    for call in calls:
        expected.update(call["service_data"])
    state = hass.states.get(ENTITY_LIGHT_1)
    for key in (ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN):
        assert state.attributes[key] == expected[key]
        assert before[key] != expected[key]
    assert hass.states.get(ENTITY_LIGHT_2).state == "off"


@pytest.mark.parametrize("bare_only", [False, True])
async def test_get_commands_turning_light_on(hass, bare_only):
    """Turning a light on with the calls only sticks with `adapt_only_on_bare_turn_on`.

    As documented: otherwise Adaptive Lighting adapts the light for now as it
    turns on, replacing the values.
    """
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_INTERCEPT: True, CONF_ADAPT_ONLY_ON_BARE_TURN_ON: bare_only},
    )
    with patch(UTCNOW, return_value=_noon()):
        await hass.services.async_call(
            "light",
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: ENTITY_LIGHT_1},
            blocking=True,
        )
        commands = await _get_commands(
            hass,
            switch,
            lights=[ENTITY_LIGHT_1],
            **{CONF_COMMANDS_TIME: "23:30:00"},
        )
        (call,) = commands[ENTITY_LIGHT_1]
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            call["service_data"],
            blocking=True,
        )
        await hass.async_block_till_done()
    brightness = hass.states.get(ENTITY_LIGHT_1).attributes[ATTR_BRIGHTNESS]
    assert (brightness == call["service_data"][ATTR_BRIGHTNESS]) == bare_only


async def test_get_commands_default_transition(hass):
    """The transition defaults to the switch's `initial_transition`."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_INITIAL_TRANSITION: 2, CONF_TRANSITION: 30},
        all_lights=True,
    )
    commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_3])
    (call,) = commands[ENTITY_LIGHT_3]  # supports transitions
    assert call["service_data"][ATTR_TRANSITION] == 2


async def test_get_commands_switch_off(hass):
    """The commands are the same when the switch is off."""
    switch, _ = await setup_lights_and_switch(hass)
    data = {CONF_COMMANDS_TIME: "23:30:00"}
    on = await _get_commands(hass, switch, **data)
    await switch.async_turn_off()
    await hass.async_block_till_done()
    assert await _get_commands(hass, switch, **data) == on


async def test_get_commands_lights_by_their_switches(hass):
    """Without a switch, each light's commands are for the switch it's in."""
    await setup_lights(hass)
    _, dim = await setup_switch(
        hass,
        {
            CONF_NAME: "dim",
            CONF_LIGHTS: [ENTITY_LIGHT_1],
            CONF_INITIAL_TRANSITION: 0,
            CONF_MAX_BRIGHTNESS: 20,
        },
    )
    _, bright = await setup_switch(
        hass,
        {
            CONF_NAME: "bright",
            CONF_LIGHTS: [ENTITY_LIGHT_2],
            CONF_INITIAL_TRANSITION: 0,
            CONF_MIN_BRIGHTNESS: 80,
        },
    )
    # Which switches are on doesn't matter
    await bright.async_turn_off()
    await hass.async_block_till_done()

    async def get_commands(**data):
        return await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_COMMANDS,
            data,
            blocking=True,
            return_response=True,
        )

    time = {CONF_COMMANDS_TIME: "12:00:00"}
    commands = await get_commands(lights=[ENTITY_LIGHT_1, ENTITY_LIGHT_2], **time)
    assert commands == {
        **await _get_commands(hass, dim, lights=[ENTITY_LIGHT_1], **time),
        **await _get_commands(hass, bright, lights=[ENTITY_LIGHT_2], **time),
    }
    brightness = {
        light: calls[0]["service_data"][ATTR_BRIGHTNESS]
        for light, calls in commands.items()
    }
    assert brightness[ENTITY_LIGHT_1] < brightness[ENTITY_LIGHT_2]

    with pytest.raises(ServiceValidationError, match="isn't among the lights of any"):
        await get_commands(lights=[ENTITY_LIGHT_3])
    # A light in several switches: the one that's on, like for `apply`
    _, also_dim = await setup_switch(
        hass,
        {CONF_NAME: "also dim", CONF_LIGHTS: [ENTITY_LIGHT_1], CONF_MAX_BRIGHTNESS: 50},
    )
    with pytest.raises(ServiceValidationError, match="more than one switch"):
        await get_commands(lights=[ENTITY_LIGHT_1])
    await dim.async_turn_off()
    await hass.async_block_till_done()
    assert await get_commands(lights=[ENTITY_LIGHT_1], **time) == (
        await _get_commands(hass, also_dim, lights=[ENTITY_LIGHT_1], **time)
    )
    with pytest.raises(ServiceValidationError, match="Pass a switch"):
        await get_commands()


async def test_get_commands_without_switch_is_read_only(hass):
    """Finding the lights' switches doesn't update the switches' lights."""
    switch, _ = await setup_lights_and_switch(hass)
    with patch.object(
        type(switch),
        "_expand_light_groups",
        side_effect=AssertionError("updated the switch's lights"),
    ):
        commands = await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_COMMANDS,
            {CONF_LIGHTS: [ENTITY_LIGHT_1]},
            blocking=True,
            return_response=True,
        )
    assert list(commands) == [ENTITY_LIGHT_1]


@pytest.mark.parametrize("expand", [True, False])
async def test_get_commands_group_without_switch(hass, expand):
    """A group in `lights` is resolved to the switch with the group (or members)."""
    await setup_lights(hass, with_group=True)
    _, switch = await setup_switch(
        hass,
        {CONF_LIGHTS: ["light.light_group"], CONF_EXPAND_LIGHT_GROUPS: expand},
    )
    commands = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_COMMANDS,
        {CONF_LIGHTS: ["light.light_group"]},
        blocking=True,
        return_response=True,
    )
    assert commands == await _get_commands(hass, switch)


async def test_get_commands_only_the_switchs_lights(hass):
    """Only lights in the switch's `lights` are allowed, e.g. not typos."""
    switch, _ = await setup_lights_and_switch(hass)
    assert ENTITY_LIGHT_3 not in switch.lights
    with pytest.raises(ServiceValidationError, match="isn't among the lights"):
        await _get_commands(hass, switch, lights=[ENTITY_LIGHT_3])
    with pytest.raises(
        ServiceValidationError,
        match=rf"'{ENTITY_LIGHT_3}', 'light\.typo' aren't among the lights of"
        rf" '{switch.entity_id}'\.$",
    ):
        await _get_commands(hass, switch, lights=[ENTITY_LIGHT_3, "light.typo"])


@pytest.mark.parametrize("expand", [True, False])
async def test_get_commands_only_configured_entities(hass, expand):
    """Only the entities in the switches' `lights` are allowed, not their members."""
    await setup_lights(hass, with_group=True)
    _, switch = await setup_switch(
        hass,
        {CONF_LIGHTS: ["light.light_group"], CONF_EXPAND_LIGHT_GROUPS: expand},
    )

    async def get_commands(**data):
        return await hass.services.async_call(
            DOMAIN,
            SERVICE_GET_COMMANDS,
            data,
            blocking=True,
            return_response=True,
        )

    for data in (
        {CONF_LIGHTS: ["light.light_4"]},
        {CONF_LIGHTS: ["light.light_4"], ATTR_ENTITY_ID: switch.entity_id},
    ):
        # The error names the light group to pass instead
        with pytest.raises(
            ServiceValidationError,
            match=r"isn't among the lights of .* 'light\.light_group' for",
        ):
            await get_commands(**data)
    assert await get_commands(lights=["light.light_group"]) == (
        await _get_commands(hass, switch)
    )


async def test_get_commands_leaves_out_lights_without_state(hass):
    """A switch's light without a state (e.g., not loaded) is left out."""
    await setup_lights(hass)
    _, switch = await setup_switch(
        hass,
        {CONF_LIGHTS: [ENTITY_LIGHT_1, "light.not_loaded"]},
    )
    commands = await _get_commands(hass, switch)
    assert list(commands) == [ENTITY_LIGHT_1]


async def test_get_commands_response_is_json(hass):
    """The response can be serialized, e.g., for automations and the frontend."""
    switch, _ = await setup_lights_and_switch(hass, {CONF_PREFER_RGB_COLOR: True})
    commands = await _get_commands(hass, switch)
    assert json.loads(json.dumps(commands)) == commands


@pytest.mark.parametrize("skip_redundant", [True, False])
async def test_get_commands_skip_redundant(hass, skip_redundant):
    """With `skip_redundant_commands`, what a light already has is left out."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_SKIP_REDUNDANT_COMMANDS: skip_redundant},
    )
    with patch(UTCNOW, return_value=_noon()):
        full = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
        (call,) = full[ENTITY_LIGHT_1]
        target = call["service_data"]
        # The light has the brightness already, but another color temperature
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: ENTITY_LIGHT_1,
                ATTR_BRIGHTNESS: target[ATTR_BRIGHTNESS],
                ATTR_COLOR_TEMP_KELVIN: target[ATTR_COLOR_TEMP_KELVIN] - 1000,
            },
            blocking=True,
        )
        partial = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
        # And then everything
        await hass.services.async_call("light", SERVICE_TURN_ON, target, blocking=True)
        nothing = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    if not skip_redundant:
        assert partial == nothing == full
        return
    (call,) = partial[ENTITY_LIGHT_1]
    assert set(call["service_data"]) == {ATTR_ENTITY_ID, ATTR_COLOR_TEMP_KELVIN}
    assert nothing == {ENTITY_LIGHT_1: []}


@pytest.mark.parametrize("already_has", ["brightness", "color"])
async def test_get_commands_skip_redundant_split(hass, already_has):
    """A split call with nothing left is dropped, and the rest isn't delayed."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {
            CONF_SKIP_REDUNDANT_COMMANDS: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_SEND_SPLIT_DELAY: 100,
        },
    )
    with patch(UTCNOW, return_value=_noon()):
        full = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
        brightness_call, color_call = full[ENTITY_LIGHT_1]
        brightness = brightness_call["service_data"][ATTR_BRIGHTNESS]
        color_temp = color_call["service_data"][ATTR_COLOR_TEMP_KELVIN]
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: ENTITY_LIGHT_1,
                ATTR_BRIGHTNESS: (
                    brightness if already_has == "brightness" else brightness - 50
                ),
                ATTR_COLOR_TEMP_KELVIN: (
                    color_temp if already_has == "color" else color_temp - 1000
                ),
            },
            blocking=True,
        )
        commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
    remaining = color_call if already_has == "brightness" else brightness_call
    assert commands == {
        ENTITY_LIGHT_1: [{"service_data": remaining["service_data"], "delay": 0}],
    }


async def test_get_commands_skip_redundant_match_what_apply_sends(hass):
    """With `skip_redundant_commands`, the calls are still what `apply` sends."""
    switch, _ = await setup_lights_and_switch(
        hass,
        {CONF_SKIP_REDUNDANT_COMMANDS: True},
    )
    with patch(UTCNOW, return_value=_noon()):
        (call,) = (await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1]))[
            ENTITY_LIGHT_1
        ]
        await hass.services.async_call(
            "light",
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: ENTITY_LIGHT_1,
                ATTR_BRIGHTNESS: call["service_data"][ATTR_BRIGHTNESS],
                ATTR_COLOR_TEMP_KELVIN: (
                    call["service_data"][ATTR_COLOR_TEMP_KELVIN] - 1000
                ),
            },
            blocking=True,
        )
        commands = await _get_commands(hass, switch, lights=[ENTITY_LIGHT_1])
        calls = _track_adaptive_light_calls(hass)
        await hass.services.async_call(
            DOMAIN,
            SERVICE_APPLY,
            {ATTR_ENTITY_ID: switch.entity_id, CONF_LIGHTS: [ENTITY_LIGHT_1]},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert [c["service_data"] for c in commands[ENTITY_LIGHT_1]] == calls
