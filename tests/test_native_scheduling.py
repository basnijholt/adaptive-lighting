"""Independent native requests retain the established adaptation timing policy."""

# pylint: disable=protected-access

import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
    CONF_INTERCEPT,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
)
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import STATE_ON
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError

from .support.async_helpers import DelayBarrier
from .support.native_lights import GROUP, RIGHT, RecordingGroup, RecordingMember
from .support.native_scenarios import (
    prepare_reported_members,
    setup_reported_group,
)


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_split_transition_duration_is_preserved(hass, planner_enabled):
    setup = await setup_reported_group(
        hass,
        **{
            CONF_INTERCEPT: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_SEND_SPLIT_DELAY: 0,
        },
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    setup.switch.manager.native_groups.disabled = not planner_enabled
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": GROUP, "transition": 2.5},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    adaptation = [
        call
        for call in setup.commands
        if "brightness" in call or "color_temp_kelvin" in call
    ]
    assert adaptation, setup.commands
    assert all(call.get("transition") == 1.25 for call in adaptation), setup.commands


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_split_delay_includes_first_axis_transition(
    hass,
    monkeypatch,
    planner_enabled,
):
    setup = await setup_reported_group(
        hass,
        **{
            CONF_INTERCEPT: True,
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_SEND_SPLIT_DELAY: 1234,
        },
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    planner = setup.switch.manager.native_groups
    planner.disabled = not planner_enabled
    barrier = DelayBarrier(
        monkeypatch,
        planner if planner_enabled else setup.switch,
        "_execute_dispatch" if planner_enabled else "_execute_adaptation_calls",
    )
    task = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": GROUP, "transition": 2.5},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(barrier.entered.wait(), 2)
        assert any("brightness" in call for call in setup.commands), setup.commands
        assert not setup.colour_commands, setup.commands
        actual_delay = barrier.delay
    finally:
        barrier.release.set()
        await task
        await hass.async_block_till_done()
    assert actual_delay == 2.484, (actual_delay, setup.commands)
    adaptation = [
        call
        for call in setup.commands
        if "brightness" in call or "color_temp_kelvin" in call
    ]
    assert any("color_temp_kelvin" in call for call in adaptation), setup.commands
    assert all(call.get("transition") == 1.25 for call in adaptation), setup.commands


async def _setup_independent_groups(hass):
    """Install disjoint native targets under one adaptive profile."""
    setup = await setup_reported_group(
        hass,
        **{
            CONF_SEPARATE_TURN_ON_COMMANDS: True,
            CONF_SEND_SPLIT_DELAY: 1234,
        },
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    await setup.switch.async_turn_off()
    second_members = [
        RecordingMember(f"light.native_z_member_{index}", setup.commands)
        for index in range(3)
    ]
    second_group = RecordingGroup(second_members, setup.commands)
    second_group.entity_id = "light.native_z_group"
    second_group._attr_is_on = False
    for member in second_members:
        member._attr_color_temp_kelvin = 4000
    await hass.data[DATA_COMPONENT].async_add_entities([*second_members, second_group])
    setup.switch._configured_lights.append(second_group.entity_id)
    setup.switch._expand_light_groups()
    await setup.switch.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()
    setup.commands.clear()
    return setup, second_group


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_split_group_does_not_delay_independent_group_brightness(
    hass,
    monkeypatch,
    planner_enabled,
):
    setup, second_group = await _setup_independent_groups(hass)
    second_brightness = asyncio.Event()
    original = second_group.async_turn_on

    async def observed(**kwargs):
        await original(**kwargs)
        if "brightness" in kwargs:
            second_brightness.set()

    monkeypatch.setattr(second_group, "async_turn_on", observed)
    planner = setup.switch.manager.native_groups
    planner.disabled = not planner_enabled
    barrier = DelayBarrier(
        monkeypatch,
        planner if planner_enabled else setup.switch,
        "_execute_dispatch" if planner_enabled else "_execute_adaptation_calls",
    )
    task = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": [GROUP, second_group.entity_id]},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(barrier.entered.wait(), 2)
        assert barrier.delay == 1.234
        try:
            await asyncio.wait_for(second_brightness.wait(), 0.5)
            other_group_started = True
        except TimeoutError:
            other_group_started = False
        paused_commands = list(setup.commands)
    finally:
        barrier.release.set()
        await task
        await hass.async_block_till_done()
    assert other_group_started, paused_commands


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_explicit_scene_colour_not_held_by_other_members_adapt_delay(
    hass,
    monkeypatch,
    planner_enabled,
):
    setup = await setup_reported_group(hass, **{CONF_ADAPT_DELAY: 1})
    planner = setup.switch.manager.native_groups
    planner.disabled = not planner_enabled
    barrier = DelayBarrier(
        monkeypatch,
        planner if planner_enabled else setup.switch,
        "_execute_dispatch" if planner_enabled else "_respond_to_off_to_on_event",
    )
    entities = {
        m.entity_id: {"state": STATE_ON, ATTR_BRIGHTNESS: 100} for m in setup.members
    }
    member = setup.members[0]
    entities[member.entity_id][ATTR_COLOR_TEMP_KELVIN] = 3500
    explicit_colour = asyncio.Event()
    original_turn_on = member.async_turn_on

    async def observe_colour(**kwargs):
        await original_turn_on(**kwargs)
        if kwargs.get(ATTR_COLOR_TEMP_KELVIN) == 3500:
            explicit_colour.set()

    monkeypatch.setattr(member, "async_turn_on", observe_colour)
    task = asyncio.create_task(
        hass.services.async_call(
            "scene",
            "apply",
            {"entities": entities},
            blocking=True,
        ),
    )
    try:
        await asyncio.wait_for(barrier.entered.wait(), 2)
        assert barrier.delay == 1
        try:
            await asyncio.wait_for(explicit_colour.wait(), 0.5)
            explicit_completed = True
        except TimeoutError:
            explicit_completed = False
        paused_commands = list(setup.commands)
    finally:
        barrier.release.set()
        await task
        await hass.async_block_till_done()
    assert explicit_completed, paused_commands
    assert member.physical_kelvin == 3500, setup.commands


@pytest.mark.parametrize(
    "failed_axis",
    ["power", ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN],
)
async def test_independent_native_group_error_keeps_other_group(
    hass,
    monkeypatch,
    failed_axis,
):
    """One failed sequence neither cancels a disjoint group nor retries its axis."""
    setup, second_group = await _setup_independent_groups(hass)
    error = HomeAssistantError("first native group unavailable")
    original = setup.group.async_turn_on
    attempts = []

    async def fail_axis(**kwargs):
        attempts.append(dict(kwargs))
        if (failed_axis == "power" and not kwargs) or failed_axis in kwargs:
            raise error
        await original(**kwargs)

    monkeypatch.setattr(setup.group, "async_turn_on", fail_axis)
    with pytest.raises(
        HomeAssistantError,
        match="first native group unavailable",
    ) as exc:
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": [GROUP, second_group.entity_id]},
            blocking=True,
            context=Context(),
        )
    await hass.async_block_till_done()
    assert exc.value is error
    assert (
        sum(
            (not command if failed_axis == "power" else failed_axis in command)
            for command in attempts
        )
        == 1
    )
    assert all(member.physical_kelvin == 4000 for member in setup.members)
    assert all(member.physical_kelvin == 3000 for member in second_group.members)
    assert all(member.brightness == 128 for member in second_group.members)
    assert all(
        call["target"] in (GROUP, second_group.entity_id) for call in setup.commands
    ), setup.commands


@pytest.mark.parametrize("brightness_adaptation", [False, True])
async def test_member_fallback_preserves_single_and_split_axis_transitions(
    hass,
    monkeypatch,
    brightness_adaptation,
):
    """Colour fallback retains split timing and independently compatible brightness."""
    setup = await setup_reported_group(
        hass,
        **{CONF_SEPARATE_TURN_ON_COMMANDS: True, CONF_SEND_SPLIT_DELAY: 0},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=brightness_adaptation,
    )
    original = setup.group.async_turn_on

    async def restrict_group_colour(**kwargs):
        await original(**kwargs)
        setup.group._attr_max_color_temp_kelvin = 2500
        setup.group.async_write_ha_state()

    monkeypatch.setattr(setup.group, "async_turn_on", restrict_group_colour)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": GROUP, "transition": 2.5},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == 3000 for member in setup.members)
    assert setup.commands[0] == {
        "target": GROUP,
        "service": "turn_on",
        "transition": 2.5,
    }
    expected_duration = 1.25 if brightness_adaptation else 2.5
    assert len(setup.commands) == (5 if brightness_adaptation else 4), setup.commands
    brightness_commands = [
        command for command in setup.commands if ATTR_BRIGHTNESS in command
    ]
    if brightness_adaptation:
        assert brightness_commands == [
            {
                "target": GROUP,
                "service": "turn_on",
                ATTR_BRIGHTNESS: 128,
                "transition": expected_duration,
            },
        ]
        assert setup.commands[1] == brightness_commands[0]
        assert all(member.brightness == 128 for member in setup.members)
    else:
        assert not brightness_commands
        assert [member.brightness for member in setup.members] == [80, 110, 26]
    assert len(setup.colour_commands) == 3
    assert {command["target"] for command in setup.colour_commands} == {
        member.entity_id for member in setup.members
    }
    for command in setup.colour_commands:
        assert command["transition"] == expected_duration
        assert ATTR_BRIGHTNESS not in command


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_independent_group_adapts_while_other_original_power_handler_waits(
    hass,
    monkeypatch,
    planner_enabled,
):
    setup, second = await _setup_independent_groups(hass)
    setup.switch.manager.native_groups.disabled = not planner_enabled
    setup.switch._send_split_delay = 0
    entered, release, second_ready = asyncio.Event(), asyncio.Event(), asyncio.Event()
    first_on, second_on = setup.group.async_turn_on, second.async_turn_on

    async def first(**kwargs):
        if not kwargs:
            entered.set()
            await asyncio.wait_for(release.wait(), 5)
        await first_on(**kwargs)

    async def other(**kwargs):
        await second_on(**kwargs)
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            second_ready.set()

    monkeypatch.setattr(setup.group, "async_turn_on", first)
    monkeypatch.setattr(second, "async_turn_on", other)
    task = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": [GROUP, second.entity_id]},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        try:
            await asyncio.wait_for(second_ready.wait(), 0.5)
            other_completed = True
        except TimeoutError:
            other_completed = False
        paused_commands = list(setup.commands)
        paused_colour = [member.physical_kelvin for member in second.members]
    finally:
        release.set()
        await task
        await hass.async_block_till_done()
    assert other_completed, (paused_commands, paused_colour)
    assert all(member.physical_kelvin == 3000 for member in second.members)


@pytest.mark.parametrize("partial_parent", [False, True])
async def test_shared_ancestor_keeps_grouping_and_late_aggregate_coverage(
    hass,
    partial_parent,
):
    """Shared full/partial native ancestors keep one owner for aggregate reports."""
    setup, second = await _setup_independent_groups(hass)
    setup.switch._send_split_delay = 0
    await setup.switch.async_turn_off()
    selected_members = [*setup.members, *second.members]
    extra = RecordingMember("light.native_unselected", setup.commands)
    parent = RecordingGroup(
        [*selected_members, *([extra] if partial_parent else [])],
        setup.commands,
    )
    parent.entity_id = "light.native_parent"
    parent._attr_is_on = False
    await hass.data[DATA_COMPONENT].async_add_entities([extra, parent])
    setup.switch._configured_lights.append(parent.entity_id)
    setup.switch._expand_light_groups()
    await setup.switch.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()
    setup.commands.clear()
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": [GROUP, second.entity_id]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert all(member.physical_kelvin == 3000 for member in selected_members)
    assert all(member.brightness == 128 for member in selected_members)
    assert not extra.is_on
    assert extra.physical_kelvin == 4000
    assert {command["target"] for command in setup.colour_commands} == (
        {GROUP, second.entity_id} if partial_parent else {parent.entity_id}
    ), setup.commands
    before_report = list(setup.commands)
    # A separate aggregate ON report may arrive after the complete service.
    parent.async_set_context(Context())
    parent._attr_is_on = True
    parent.async_write_ha_state()
    await hass.async_block_till_done()
    assert setup.commands == before_report
    assert not extra.is_on


async def test_unsupported_overlapping_native_target_keeps_shared_dispatch_boundary(
    hass,
    monkeypatch,
):
    """An ineligible native target still shares physical members with its peer."""
    setup, second = await _setup_independent_groups(hass)
    setup.switch._send_split_delay = 0
    extra = RecordingMember("light.native_foreign_member", setup.commands)
    overlapping = RecordingGroup([*second.members, extra], setup.commands)
    overlapping.entity_id = "light.native_unowned_overlap"
    overlapping._attr_is_on = False
    await hass.data[DATA_COMPONENT].async_add_entities([extra, overlapping])
    entered, release = asyncio.Event(), asyncio.Event()
    peer_power, peer_colour = asyncio.Event(), asyncio.Event()
    original_overlap, original_peer = overlapping.async_turn_on, second.async_turn_on

    async def hold_overlap(**kwargs):
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
        await original_overlap(**kwargs)

    async def observe_peer(**kwargs):
        await original_peer(**kwargs)
        if not kwargs:
            peer_power.set()
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            peer_colour.set()

    monkeypatch.setattr(overlapping, "async_turn_on", hold_overlap)
    monkeypatch.setattr(second, "async_turn_on", observe_peer)
    task = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": [overlapping.entity_id, second.entity_id]},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(peer_power.wait(), 2)
        try:
            await asyncio.wait_for(peer_colour.wait(), 0.5)
            correction_before_shared_power = True
        except TimeoutError:
            correction_before_shared_power = False
    finally:
        release.set()
        await task
        await hass.async_block_till_done()
    assert not correction_before_shared_power, setup.commands
    assert all(member.physical_kelvin == 3000 for member in second.members)
    assert extra.is_on
    assert extra.physical_kelvin == 4000


@pytest.mark.parametrize("action", ["cancel", "new_colour"])
async def test_parallel_split_dispatch_respects_parent_cancel_and_new_member_intent(
    hass,
    monkeypatch,
    action,
):
    setup, second = await _setup_independent_groups(hass)
    planner = setup.switch.manager.native_groups
    barrier = DelayBarrier(monkeypatch, planner, "_execute_dispatch")
    other_brightness = asyncio.Event()
    original = second.async_turn_on

    async def observe(**kwargs):
        await original(**kwargs)
        if ATTR_BRIGHTNESS in kwargs:
            other_brightness.set()

    monkeypatch.setattr(second, "async_turn_on", observe)
    parent = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": [GROUP, second.entity_id]},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(barrier.entered.wait(), 2)
        assert barrier.delay == 1.234
        await asyncio.wait_for(other_brightness.wait(), 2)
        assert not setup.colour_commands
        if action == "cancel":
            parent.cancel()
            with pytest.raises(asyncio.CancelledError):
                await parent
        else:
            await hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": RIGHT, ATTR_COLOR_TEMP_KELVIN: 4500},
                blocking=True,
                context=Context(),
            )
    finally:
        barrier.release.set()
        await asyncio.gather(parent, return_exceptions=True)
    await hass.async_block_till_done()

    if action == "cancel":
        assert not setup.colour_commands, setup.commands
        assert all(m.physical_kelvin == 4000 for m in [*setup.members, *second.members])
    else:
        assert [m.physical_kelvin for m in setup.members] == [3000, 4500, 3000]
        assert all(m.physical_kelvin == 3000 for m in second.members)
        assert not any(c["target"] == GROUP for c in setup.colour_commands)
    assert all(m.is_on for m in [*setup.members, *second.members])


async def test_completed_partition_retains_late_report_claim_after_peer_cancel(
    hass,
    monkeypatch,
):
    setup, second = await _setup_independent_groups(hass)
    setup.switch._send_split_delay = 0
    held_member = second.members[0]
    held_member.hold_reports = True
    entered, release, partition_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    first_on = setup.group.async_turn_on
    planner = setup.switch.manager.native_groups
    original_run = planner._run

    async def observe_partition(batch, invoke):
        result = await original_run(batch, invoke)
        if second.entity_id in batch.plan.requests:
            partition_done.set()
        return result

    monkeypatch.setattr(planner, "_run", observe_partition)

    async def first(**kwargs):
        if not kwargs:
            entered.set()
            await asyncio.wait_for(release.wait(), 5)
        await first_on(**kwargs)

    monkeypatch.setattr(setup.group, "async_turn_on", first)
    parent = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": [GROUP, second.entity_id]},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(partition_done.wait(), 2)
        assert held_member.physical_kelvin == 3000
        assert hass.states.is_state(held_member.entity_id, "off")
        parent.cancel()
        with pytest.raises(asyncio.CancelledError):
            await parent
    finally:
        release.set()
        await asyncio.gather(parent, return_exceptions=True)
    await hass.async_block_till_done()
    before_report = list(setup.commands)
    held_member.hold_reports = False
    held_member.async_set_context(Context())
    held_member.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.is_state(held_member.entity_id, "on")
    assert setup.commands == before_report
    assert all(m.physical_kelvin == 3000 for m in second.members)
