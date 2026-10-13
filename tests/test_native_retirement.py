"""Profile retirement releases computed coverage without discarding other intent."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
    DOMAIN,
)
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_LIGHTS,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context

from .support.adaptive import setup_switch
from .support.async_helpers import DelayBarrier
from .support.native_lights import GROUP, RIGHT, TARGET_KELVIN
from .support.native_scenarios import (
    activate_scene,
    prepare_reported_members,
    setup_reported_group,
)


async def _unload_profile(hass, switch):
    entry = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if hass.data[DOMAIN][entry.entry_id].get("switch") is switch
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def _replacement_profile(hass, target=RIGHT):
    """Keep a distinct brightness/colour profile ready to take over a target."""
    _, replacement = await setup_switch(
        hass,
        {
            CONF_NAME: "replacement",
            CONF_LIGHTS: [target],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_BRIGHTNESS: 100,
            CONF_MAX_BRIGHTNESS: 100,
            CONF_MIN_COLOR_TEMP: 3500,
            CONF_MAX_COLOR_TEMP: 3500,
            CONF_SLEEP_COLOR_TEMP: 3500,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    await replacement.async_turn_off()
    return replacement


async def _release_report(hass, member, freezer):
    """Publish the delayed real activation after the recent-OFF debounce expires."""
    freezer.tick(11)
    member.hold_reports = False
    member.async_set_context(Context())
    member.async_write_ha_state()
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("retirement", "explicit_brightness"),
    [
        ("unload", False),
        ("target_removed", False),
        ("member_removed", False),
        ("unload", True),
    ],
)
async def test_retired_computed_claim_does_not_suppress_replacement(
    hass,
    monkeypatch,
    freezer,
    retirement,
    explicit_brightness,
):
    """Late reports adapt both computed axes, preserving explicit scene brightness."""
    setup = await setup_reported_group(hass, **{CONF_SKIP_REDUNDANT_COMMANDS: False})
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    members = tuple(setup.members)
    left, right, _ = members
    replacement = await _replacement_profile(hass)
    freezer.tick(11)
    for member in members:
        member.hold_reports = True
    setup.switch._adapt_delay = 1
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    scene = {member.entity_id: {"state": STATE_ON} for member in members}
    if explicit_brightness:
        for state in scene.values():
            state[ATTR_BRIGHTNESS] = 150
    activating = asyncio.create_task(activate_scene(hass, scene))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1
        assert right.is_on
        assert right.physical_kelvin == 4000
        assert right.brightness == (150 if explicit_brightness else 110)
        if retirement == "unload":
            await _unload_profile(hass, setup.switch)
        elif retirement == "target_removed":
            setup.switch._configured_lights.clear()
            setup.switch._expand_light_groups()
        else:
            setup.group.members.remove(right)
            setup.group.async_write_ha_state()
            setup.switch._expand_light_groups()
        assert RIGHT not in setup.switch._tracked_lights or retirement == "unload"
        await replacement.async_turn_on()
    finally:
        delay.release.set()
        await activating

    assert right.physical_kelvin == 4000
    assert right.brightness == (150 if explicit_brightness else 110)
    assert hass.states.get(RIGHT).state == STATE_OFF
    setup.commands.clear()
    await _release_report(hass, right, freezer)

    assert (right.physical_kelvin, right.brightness) == (
        3500,
        150 if explicit_brightness else 255,
    ), setup.commands
    assert len(setup.commands) == 1, setup.commands
    assert setup.commands[0]["target"] == RIGHT
    assert setup.commands[0][ATTR_COLOR_TEMP_KELVIN] == 3500
    if explicit_brightness:
        assert ATTR_BRIGHTNESS not in setup.commands[0]
    else:
        assert setup.commands[0][ATTR_BRIGHTNESS] == 255

    if retirement == "member_removed":
        # The old profile retains the other members and their completed claims.
        assert left.physical_kelvin == TARGET_KELVIN
        assert left.brightness == 128
        setup.commands.clear()
        await _release_report(hass, left, freezer)
        assert not setup.commands


async def test_retirement_preserves_other_owners_pending_claim(
    hass,
    monkeypatch,
    freezer,
):
    """Unloading colour ownership retains another owner's pending brightness work."""
    setup = await setup_reported_group(hass, **{CONF_SKIP_REDUNDANT_COMMANDS: False})
    await prepare_reported_members(hass, setup, on=(False, False, False))
    _, brightness_owner = await setup_switch(
        hass,
        {
            CONF_NAME: "remaining_brightness_owner",
            CONF_LIGHTS: [GROUP],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_BRIGHTNESS: 50,
            CONF_MAX_BRIGHTNESS: 50,
            CONF_TAKE_OVER_CONTROL: False,
        },
    )
    await brightness_owner.async_turn_off()
    await brightness_owner.adapt_color_switch.async_turn_off()
    await brightness_owner.async_turn_on(adapt_lights=False)
    freezer.tick(11)
    for member in setup.members:
        member.hold_reports = True
    brightness_owner._adapt_delay = 1
    setup.switch._adapt_delay = 1
    setup.commands.clear()
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    activating = asyncio.create_task(
        activate_scene(
            hass,
            {member.entity_id: {"state": STATE_ON} for member in setup.members},
        ),
    )
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert not any(ATTR_BRIGHTNESS in call for call in setup.commands)
        await _unload_profile(hass, setup.switch)
    finally:
        delay.release.set()
        await activating

    assert all(member.brightness == 128 for member in setup.members)
    assert all(member.physical_kelvin == 4000 for member in setup.members)
    brightness_commands = [call for call in setup.commands if ATTR_BRIGHTNESS in call]
    assert len(brightness_commands) == 1, setup.commands
    assert brightness_commands[0]["target"] == GROUP
    setup.commands.clear()
    # The scene delay has already been exercised. Keep the late report's
    # no-duplicate assertion independent of a new reactive delay under freezer.
    brightness_owner._adapt_delay = 0
    await _release_report(hass, setup.members[1], freezer)
    assert not setup.commands


class _ReportLock(asyncio.Lock):
    """Observe a report waiting for the recent-OFF lock without bypassing it."""

    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()

    async def acquire(self):
        if self.locked():
            self.waiting.set()
        return await super().acquire()


@pytest.mark.parametrize("explicit_brightness", [False, True])
async def test_retirement_while_report_waits_at_off_lock(
    hass,
    monkeypatch,
    freezer,
    explicit_brightness,
):
    """A report already being handled must release the retired owner's coverage."""
    setup = await setup_reported_group(hass, **{CONF_SKIP_REDUNDANT_COMMANDS: False})
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    right = setup.members[1]
    replacement = await _replacement_profile(hass)
    freezer.tick(11)
    for member in setup.members:
        member.hold_reports = True
    setup.switch._adapt_delay = 1
    manager = setup.switch.manager
    delay = DelayBarrier(monkeypatch, manager.native_groups, "_execute_dispatch")
    scene = {member.entity_id: {"state": STATE_ON} for member in setup.members}
    if explicit_brightness:
        for state in scene.values():
            state[ATTR_BRIGHTNESS] = 150
    lock = manager.turn_off_locks[RIGHT] = _ReportLock()
    await lock.acquire()
    activating = asyncio.create_task(activate_scene(hass, scene))
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert right.is_on
        assert hass.states.get(RIGHT).state == STATE_OFF
        right.hold_reports = False
        right.async_set_context(Context())
        right.async_write_ha_state()
        await asyncio.wait_for(lock.waiting.wait(), 2)
        assert right.physical_kelvin == 4000
        await _unload_profile(hass, setup.switch)
        await replacement.async_turn_on(adapt_lights=False)
    finally:
        lock.release()
        delay.release.set()
        await activating
        await hass.async_block_till_done()

    assert (right.physical_kelvin, right.brightness) == (
        3500,
        150 if explicit_brightness else 255,
    ), setup.commands
    corrections = [
        call for call in setup.commands if call.get(ATTR_COLOR_TEMP_KELVIN) == 3500
    ]
    assert len(corrections) == 1, setup.commands
    assert corrections[0]["target"] == RIGHT
    if explicit_brightness:
        assert ATTR_BRIGHTNESS not in corrections[0]


@pytest.mark.parametrize("newer_request", [False, True])
async def test_replacement_revalidates_claim_after_adapt_delay(
    hass,
    monkeypatch,
    freezer,
    newer_request,
):
    """Settings retirement and newer intent remain authoritative after a wait."""
    setup = await setup_reported_group(hass, **{CONF_SKIP_REDUNDANT_COMMANDS: False})
    await prepare_reported_members(hass, setup, on=(False, False, False))
    right = setup.members[1]
    replacement = await _replacement_profile(hass)
    freezer.tick(11)
    for member in setup.members:
        member.hold_reports = True
    setup.switch._adapt_delay = 1
    dispatch = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    reacting = DelayBarrier(monkeypatch, replacement, "_respond_to_off_to_on_event")
    replacement._adapt_delay = 1
    activating = asyncio.create_task(
        activate_scene(
            hass,
            {member.entity_id: {"state": STATE_ON} for member in setup.members},
        ),
    )
    try:
        await asyncio.wait_for(dispatch.entered.wait(), 2)
        assert right.is_on
        assert hass.states.get(RIGHT).state == STATE_OFF
        setup.switch._adapt_delay = 0
        await replacement.async_turn_on(adapt_lights=False)
        right.hold_reports = False
        right.async_set_context(Context())
        right.async_write_ha_state()
        await asyncio.wait_for(reacting.entered.wait(), 2)
        assert reacting.delay == 1
        assert right.physical_kelvin == 4000
        if newer_request:
            await _set_newer_attributes(hass)
        else:
            await _unload_profile(hass, setup.switch)
    finally:
        dispatch.release.set()
        reacting.release.set()
        await activating
        await hass.async_block_till_done()

    if newer_request:
        assert (right.physical_kelvin, right.brightness) == (4500, 150), setup.commands
        assert not any(
            call.get(ATTR_COLOR_TEMP_KELVIN) == 3500 for call in setup.commands
        )
    else:
        assert (right.physical_kelvin, right.brightness) == (3500, 255), setup.commands
        corrections = [
            call for call in setup.commands if call.get(ATTR_COLOR_TEMP_KELVIN) == 3500
        ]
        assert len(corrections) == 1, setup.commands
        assert corrections[0]["target"] == RIGHT
        assert corrections[0][ATTR_BRIGHTNESS] == 255


async def _set_newer_attributes(hass):
    """Submit new explicit intent without draining the intentionally waiting task."""
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: RIGHT,
            ATTR_COLOR_TEMP_KELVIN: 4500,
            ATTR_BRIGHTNESS: 150,
        },
        blocking=True,
        context=Context(),
    )


async def test_newer_request_supersedes_report_waiting_at_off_lock(
    hass,
    monkeypatch,
    freezer,
):
    """A newer explicit command wins before the old report reaches the profile."""
    setup = await setup_reported_group(hass, **{CONF_SKIP_REDUNDANT_COMMANDS: False})
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    right = setup.members[1]
    manager = setup.switch.manager
    freezer.tick(11)
    for member in setup.members:
        member.hold_reports = True
    setup.switch._adapt_delay = 1
    dispatch = DelayBarrier(monkeypatch, manager.native_groups, "_execute_dispatch")
    lock = manager.turn_off_locks[RIGHT] = _ReportLock()
    await lock.acquire()
    activating = asyncio.create_task(
        activate_scene(
            hass,
            {member.entity_id: {"state": STATE_ON} for member in setup.members},
        ),
    )
    try:
        await asyncio.wait_for(dispatch.entered.wait(), 2)
        assert right.is_on
        assert hass.states.get(RIGHT).state == STATE_OFF
        right.hold_reports = False
        right.async_set_context(Context())
        right.async_write_ha_state()
        await asyncio.wait_for(lock.waiting.wait(), 2)
        setup.switch._adapt_delay = 0
        await _set_newer_attributes(hass)
        before_release = len(setup.commands)
    finally:
        lock.release()
        dispatch.release.set()
        await activating
        await hass.async_block_till_done()

    assert (right.physical_kelvin, right.brightness) == (4500, 150), setup.commands
    assert not any(
        call["target"] == RIGHT for call in setup.commands[before_release:]
    ), setup.commands[before_release:]


async def test_retired_group_report_respects_newer_member_request(
    hass,
    monkeypatch,
    freezer,
):
    """A waiting group report must not overwrite newer intent for one member."""
    setup = await setup_reported_group(hass, **{CONF_SKIP_REDUNDANT_COMMANDS: False})
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=True,
    )
    replacement = await _replacement_profile(hass, GROUP)
    manager = setup.switch.manager
    right = setup.members[1]
    freezer.tick(11)
    for member in setup.members:
        member.hold_reports = True
    # Model a native group whose own state report is delayed independently.
    original_write = setup.group.async_write_ha_state
    monkeypatch.setattr(setup.group, "async_write_ha_state", lambda: None)
    setup.switch._adapt_delay = 1
    dispatch = DelayBarrier(monkeypatch, manager.native_groups, "_execute_dispatch")
    lock = manager.turn_off_locks[GROUP] = _ReportLock()
    await lock.acquire()
    activating = asyncio.create_task(activate_scene(hass, {GROUP: {"state": STATE_ON}}))
    try:
        await asyncio.wait_for(dispatch.entered.wait(), 2)
        assert right.is_on
        assert hass.states.get(GROUP).state == STATE_OFF
        setup.group.async_set_context(Context())
        original_write()
        await asyncio.wait_for(lock.waiting.wait(), 2)
        await _set_newer_attributes(hass)
        assert (right.physical_kelvin, right.brightness) == (4500, 150)
        await _unload_profile(hass, setup.switch)
        await replacement.async_turn_on(adapt_lights=False)
        after_newer = len(setup.commands)
    finally:
        lock.release()
        dispatch.release.set()
        await activating
        await hass.async_block_till_done()

    assert (right.physical_kelvin, right.brightness) == (
        4500,
        150,
    ), setup.commands[after_newer:]
    assert not setup.commands[after_newer:]
