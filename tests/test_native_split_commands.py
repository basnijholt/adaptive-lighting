"""Native broadcasts preserve the configured brightness/colour split policy."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError

from .support.async_helpers import DelayBarrier
from .support.native_lights import GROUP, RIGHT, TARGET_KELVIN, RecordingMember
from .support.native_scenarios import (
    prepare_reported_members,
    set_manual,
    setup_reported_group,
)


async def _setup_activation(hass, *, split=True, delay=0):
    setup = await setup_reported_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: split, CONF_SEND_SPLIT_DELAY: delay},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    return setup


async def _activate_group(hass, transition=None):
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: GROUP,
            **({ATTR_TRANSITION: transition} if transition is not None else {}),
        },
        blocking=True,
        context=Context(),
    )


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("transition", [None, 2.5])
async def test_native_activation_preserves_configured_command_split(
    hass,
    planner_enabled,
    split,
    transition,
):
    """Splitting retains one broadcast per axis; the default remains combined."""
    setup = await _setup_activation(hass, split=split)
    setup.switch.manager.native_groups.disabled = not planner_enabled

    await _activate_group(hass, transition)
    await hass.async_block_till_done()

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    combined = [
        call
        for call in setup.commands
        if ATTR_BRIGHTNESS in call and ATTR_COLOR_TEMP_KELVIN in call
    ]
    assert bool(combined) is not split, setup.commands
    if planner_enabled:
        assert len(setup.commands) == (3 if split else 2), setup.commands
        assert all(call["target"] == GROUP for call in setup.commands)
        assert len(setup.colour_commands) == 1
        if transition is not None:
            # The original bare power request retains the user's duration;
            # computed brightness/colour divide it according to the split policy.
            assert setup.commands[0][ATTR_TRANSITION] == transition
            assert all(
                call[ATTR_TRANSITION] == (transition / 2 if split else transition)
                for call in setup.commands[1:]
            )


async def test_native_split_waits_between_brightness_and_colour(hass, monkeypatch):
    """The configured millisecond delay starts after brightness has reached devices."""
    setup = await _setup_activation(hass, delay=1234)
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    task = asyncio.create_task(_activate_group(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1.234
        assert len(setup.commands) == 2, setup.commands
        assert setup.commands[-1]["target"] == GROUP
        assert ATTR_BRIGHTNESS in setup.commands[-1]
        assert not setup.colour_commands
        assert all(member.brightness == 128 for member in setup.members)
        assert all(member.physical_kelvin == 4000 for member in setup.members)
        assert not task.done()
    finally:
        delay.release.set()
        await task
    await hass.async_block_till_done()

    assert len(setup.commands) == 3
    assert setup.commands[-1]["target"] == GROUP
    assert ATTR_BRIGHTNESS not in setup.commands[-1]
    assert setup.commands[-1][ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)


@pytest.mark.parametrize(
    "change",
    ["off", "colour", "manual", "membership", "growth", "profile"],
)
async def test_native_split_revalidates_colour_after_delay(hass, monkeypatch, change):
    """A split command may only colour members whose original intent is still valid."""
    setup = await _setup_activation(hass, delay=1234)
    original_members = tuple(setup.members)
    right = original_members[1]
    if change == "growth":
        extra = RecordingMember("light.native_added_later", setup.commands)
        await hass.data[DATA_COMPONENT].async_add_entities([extra])
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    task = asyncio.create_task(_activate_group(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1.234
        assert not setup.colour_commands
        if change == "off":
            await hass.services.async_call(
                "light",
                "turn_off",
                {ATTR_ENTITY_ID: RIGHT},
                blocking=True,
            )
        elif change == "colour":
            await hass.services.async_call(
                "light",
                "turn_on",
                {ATTR_ENTITY_ID: RIGHT, ATTR_COLOR_TEMP_KELVIN: 4500},
                blocking=True,
                context=Context(),
            )
        elif change == "manual":
            await set_manual(hass, setup.switch, RIGHT, "color")
        elif change == "membership":
            setup.group.members.remove(right)
            setup.group.async_write_ha_state()
        elif change == "growth":
            setup.group.members.append(extra)
            setup.group.async_write_ha_state()
        else:
            await setup.switch.async_turn_off()
        after_change = len(setup.commands)
    finally:
        delay.release.set()
        await task
    await hass.async_block_till_done()

    remaining = setup.commands[after_change:]
    assert not any(call["target"] == GROUP for call in remaining), remaining
    assert not any(ATTR_BRIGHTNESS in call for call in remaining), remaining
    if change in {"profile", "manual"}:
        # A native-group source cannot adapt colour when one of its members
        # is manually controlled, matching the existing group-source guard.
        assert remaining == []
        assert all(member.physical_kelvin == 4000 for member in original_members)
    elif change == "growth":
        assert len(remaining) == 3, remaining
        assert {call["target"] for call in remaining} == {
            member.entity_id for member in original_members
        }
        assert all(
            member.physical_kelvin == TARGET_KELVIN for member in original_members
        )
        assert not extra.is_on
        assert extra.physical_kelvin == 4000
    else:
        assert len(remaining) == 2, remaining
        assert not any(call["target"] == RIGHT for call in remaining)
        assert all(call[ATTR_COLOR_TEMP_KELVIN] == TARGET_KELVIN for call in remaining)
        assert right.physical_kelvin == (4500 if change == "colour" else 4000)
        assert right.is_on is (change != "off")


async def test_native_split_cancellation_does_not_flush_colour(hass, monkeypatch):
    """Cancellation between axes never becomes a colour recovery or a retry."""
    setup = await _setup_activation(hass, delay=1234)
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    task = asyncio.create_task(_activate_group(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1.234
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        delay.release.set()
        if not task.done():
            await task
    await hass.async_block_till_done()

    assert len(setup.commands) == 2, setup.commands
    assert not setup.colour_commands
    assert all(member.physical_kelvin == 4000 for member in setup.members)


@pytest.mark.parametrize("failed_axis", [ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN])
async def test_native_split_does_not_retry_failed_axis(hass, monkeypatch, failed_axis):
    """A failed group axis preserves error identity and never becomes member retries."""
    setup = await _setup_activation(hass)
    original_turn_on = setup.group.async_turn_on
    error = HomeAssistantError("native group unavailable")
    attempts = []

    async def fail_axis(**kwargs):
        attempts.append(dict(kwargs))
        if failed_axis in kwargs:
            raise error
        await original_turn_on(**kwargs)

    monkeypatch.setattr(setup.group, "async_turn_on", fail_axis)
    with pytest.raises(HomeAssistantError, match="native group unavailable") as exc:
        await _activate_group(hass)
    assert exc.value is error
    await hass.async_block_till_done()

    assert len(attempts) == (2 if failed_axis == ATTR_BRIGHTNESS else 3)
    assert sum(failed_axis in data for data in attempts) == 1
    assert all(call["target"] == GROUP for call in setup.commands)
    assert len(setup.commands) == (1 if failed_axis == ATTR_BRIGHTNESS else 2)
    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == 4000 for member in setup.members)
    assert [member.brightness for member in setup.members] == (
        [80, 110, 26] if failed_axis == ATTR_BRIGHTNESS else [128, 128, 128]
    )


async def test_native_split_preserves_explicit_combined_group_request(hass):
    """The compatibility option changes computed adaptation, not explicit user data."""
    setup = await _setup_activation(hass)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP, ATTR_BRIGHTNESS: 160, ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert setup.commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_BRIGHTNESS: 160,
            ATTR_COLOR_TEMP_KELVIN: 3500,
        },
    ]
    assert all(member.brightness == 160 for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)


async def test_native_member_fallback_preserves_command_split(hass, monkeypatch):
    """An incompatible group colour leaves the compatible brightness broadcast intact."""
    setup = await _setup_activation(hass)
    original_turn_on = setup.group.async_turn_on

    async def update_group_capability(**kwargs):
        await original_turn_on(**kwargs)
        setup.group._attr_max_color_temp_kelvin = 2500
        setup.group.async_write_ha_state()

    monkeypatch.setattr(setup.group, "async_turn_on", update_group_capability)
    await _activate_group(hass)
    await hass.async_block_till_done()

    assert len(setup.commands) == 5, setup.commands
    assert setup.commands[:2] == [
        {"target": GROUP, "service": "turn_on"},
        {"target": GROUP, "service": "turn_on", ATTR_BRIGHTNESS: 128},
    ]
    assert all(member.is_on for member in setup.members)
    assert all(member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    for member in setup.members:
        commands = [
            call for call in setup.commands if call["target"] == member.entity_id
        ]
        assert commands == [
            {
                "target": member.entity_id,
                "service": "turn_on",
                ATTR_COLOR_TEMP_KELVIN: TARGET_KELVIN,
            },
        ]
