"""Native-group profile updates behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_COLOR_TEMP,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SLEEP_COLOR_TEMP,
    DOMAIN,
    SERVICE_CHANGE_SWITCH_SETTINGS,
)
from homeassistant.components.light import ATTR_COLOR_TEMP_KELVIN
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant

from .support.adaptive import track_adaptive_light_calls
from .support.async_helpers import DelayBarrier
from .support.native_lights import GROUP, RIGHT, RecordingGroup, RecordingMember
from .support.native_scenarios import (
    prepare_reported_members,
    setup_native_group,
    setup_reported_group,
    turn_on_member,
)


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_sleep_mode_change_supersedes_pending_adaptive_colour(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    planner_enabled: bool,
):
    """A delayed adaptive colour cannot overwrite the newer sleep temperature."""
    setup = await setup_reported_group(
        hass,
        **{CONF_ADAPT_DELAY: 1, CONF_SLEEP_COLOR_TEMP: 2200},
    )
    await prepare_reported_members(hass, setup, on=(False, False, False))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups if planner_enabled else setup.switch,
        "_execute_dispatch" if planner_enabled else "_respond_to_off_to_on_event",
    )
    replacement_applied = asyncio.Event()
    original_turn_on = setup.group.async_turn_on

    async def observe_replacement(**kwargs):
        await original_turn_on(**kwargs)
        if all(member.physical_kelvin == 2200 for member in setup.members):
            replacement_applied.set()

    monkeypatch.setattr(setup.group, "async_turn_on", observe_replacement)
    older = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: GROUP},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1
        await hass.services.async_call(
            "switch",
            "turn_on",
            {ATTR_ENTITY_ID: setup.switch.sleep_mode_switch.entity_id},
            blocking=True,
        )
        await asyncio.wait_for(replacement_applied.wait(), 2)
        assert all(member.physical_kelvin == 2200 for member in setup.members)
        after_sleep = len(setup.commands)
    finally:
        delay.release.set()
        await older
    await hass.async_block_till_done()

    assert all(
        member.physical_kelvin == 2200 for member in setup.members
    ), setup.commands[after_sleep:]


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_sleep_mode_change_preserves_pending_explicit_colour(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    planner_enabled: bool,
):
    """Changing adaptive settings cannot discard a user's accepted colour request."""
    setup = await setup_reported_group(hass, **{CONF_SLEEP_COLOR_TEMP: 2200})
    await prepare_reported_members(hass, setup, on=(False, False, False))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold_power():
        entered.set()
        await release.wait()

    setup.members[1].before_turn_on = hold_power
    # Isolate pending explicit intent from the separate later ON-report reaction.
    setup.members[1].hold_reports = True
    older = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: RIGHT, ATTR_COLOR_TEMP_KELVIN: 3500},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        reset_completed = asyncio.Event()
        original_reset = setup.switch._reset_lights

        def observe_reset(*args, **kwargs):
            original_reset(*args, **kwargs)
            reset_completed.set()

        monkeypatch.setattr(setup.switch, "_reset_lights", observe_reset)
        await hass.services.async_call(
            "switch",
            "turn_on",
            {ATTR_ENTITY_ID: setup.switch.sleep_mode_switch.entity_id},
            blocking=True,
        )
        await asyncio.wait_for(reset_completed.wait(), 2)
        assert setup.switch.sleep_mode_switch.is_on
    finally:
        release.set()
        await older
    await hass.async_block_till_done()

    assert setup.members[1].is_on
    assert setup.members[1].physical_kelvin == 3500, setup.commands


async def change_temperature(hass, switch):
    """Set a different daytime target through the public settings service."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CHANGE_SWITCH_SETTINGS,
        {
            ATTR_ENTITY_ID: switch.entity_id,
            CONF_MIN_COLOR_TEMP: 2200,
            CONF_MAX_COLOR_TEMP: 2200,
        },
        blocking=True,
    )


@pytest.mark.parametrize("explicit_member", [False, True])
async def test_public_settings_change_cancels_old_reactive_member_split(
    hass,
    monkeypatch,
    explicit_member,
):
    """Observed native members retire old split commands like direct targets."""
    setup = await setup_native_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: True, CONF_SEND_SPLIT_DELAY: 1234},
    )
    if explicit_member:
        setup.switch._configured_lights.append(RIGHT)
        setup.switch._expand_light_groups()
    await setup.switch.adapt_brightness_switch.async_turn_on()
    delay = DelayBarrier(monkeypatch, setup.switch, "_execute_adaptation_calls")
    calls = track_adaptive_light_calls(hass)
    turning_on = hass.async_create_task(turn_on_member(hass))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1.234
        await change_temperature(hass, setup.switch)
        assert setup.right.physical_kelvin == 2200, calls
        after_update = len(calls)
    finally:
        delay.release.set()
        await turning_on
    await hass.async_block_till_done()

    assert setup.right.physical_kelvin == 2200, calls
    assert not any(
        call.get(ATTR_COLOR_TEMP_KELVIN) == 3000 for call in calls[after_update:]
    ), calls


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_public_settings_change_retires_delayed_native_colour(
    hass,
    monkeypatch,
    planner_enabled,
):
    """An old computed colour cannot restore settings replaced while it waited."""
    setup = await setup_reported_group(hass, **{CONF_ADAPT_DELAY: 1})
    await prepare_reported_members(hass, setup, on=(False, False, False))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups if planner_enabled else setup.switch,
        "_execute_dispatch" if planner_enabled else "_respond_to_off_to_on_event",
    )
    older = hass.async_create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: GROUP},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1
        await change_temperature(hass, setup.switch)
        assert all(member.physical_kelvin == 2200 for member in setup.members)
        after_update = len(setup.commands)
    finally:
        delay.release.set()
        await older
    await hass.async_block_till_done()

    assert all(
        member.physical_kelvin == 2200 for member in setup.members
    ), setup.commands[after_update:]


@pytest.mark.parametrize("change", ["sleep", "settings"])
async def test_second_group_rechecks_profile_after_first_group_dispatch(
    hass,
    monkeypatch,
    change,
):
    """Recheck computed intent after a previous broadcast awaited newer settings."""
    setup = await setup_reported_group(hass, **{CONF_SLEEP_COLOR_TEMP: 2200})
    await prepare_reported_members(hass, setup, on=(False, False, False))
    second_members = [
        RecordingMember(f"light.native_z_member_{index}", setup.commands)
        for index in range(3)
    ]
    second_group = RecordingGroup(second_members, setup.commands)
    second_group.entity_id = "light.native_z_group"
    await hass.data[DATA_COMPONENT].async_add_entities([*second_members, second_group])
    setup.switch._configured_lights.append(second_group.entity_id)
    setup.switch._expand_light_groups()
    await hass.async_block_till_done()
    setup.commands.clear()
    original_first = setup.group.async_turn_on
    original_second = second_group.async_turn_on
    changed = False
    second_power_ready = asyncio.Event()
    replacement_applied = asyncio.Event()

    async def second_turn_on(**kwargs):
        await original_second(**kwargs)
        if kwargs.get(ATTR_COLOR_TEMP_KELVIN) == 2200:
            replacement_applied.set()
        elif ATTR_COLOR_TEMP_KELVIN not in kwargs:
            # Independent groups may progress concurrently. Hold this original
            # power call after the bulbs turn ON, before its old colour can run.
            second_power_ready.set()
            await asyncio.wait_for(replacement_applied.wait(), 2)

    async def first_turn_on(**kwargs):
        nonlocal changed
        await original_first(**kwargs)
        if ATTR_COLOR_TEMP_KELVIN in kwargs and not changed:
            changed = True
            await asyncio.wait_for(second_power_ready.wait(), 2)
            if change == "settings":
                await change_temperature(hass, setup.switch)
            else:
                await hass.services.async_call(
                    "switch",
                    "turn_on",
                    {ATTR_ENTITY_ID: setup.switch.sleep_mode_switch.entity_id},
                    blocking=True,
                )
            await asyncio.wait_for(replacement_applied.wait(), 2)

    monkeypatch.setattr(setup.group, "async_turn_on", first_turn_on)
    monkeypatch.setattr(second_group, "async_turn_on", second_turn_on)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [GROUP, second_group.entity_id]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert changed
    assert all(
        member.physical_kelvin == 2200 for member in [*setup.members, *second_members]
    ), setup.commands
    assert [
        call[ATTR_COLOR_TEMP_KELVIN]
        for call in setup.colour_commands
        if call["target"] == second_group.entity_id
    ] == [2200], setup.commands
