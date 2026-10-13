"""Native-group lifecycle behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_ADAPT_DELAY,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.components.light import (
    reproduce_state as light_reproduce_state,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.components.scene import DATA_COMPONENT as SCENE_COMPONENT
from homeassistant.components.scene import Scene
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_CALL_SERVICE,
    EVENT_STATE_CHANGED,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context, HomeAssistant, State

from .support.async_helpers import DelayBarrier
from .support.native_lights import (
    GROUP,
    LEFT,
    RIGHT,
    TARGET_KELVIN,
    RecordingGroup,
    RecordingMember,
)
from .support.native_scenarios import (
    activate_scene,
    add_subgroup,
    prepare_all_off,
    prepare_reported_members,
    scene_state,
    setup_reported_group,
    setup_scene_group,
)


@pytest.mark.parametrize("new_intent", ["off", "colour"])
async def test_newer_member_intent_invalidates_pending_scene_group(hass, new_intent):
    """A newer individual request cannot be overwritten by an older scene batch."""
    setup = await setup_scene_group(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause_power_dispatch():
        entered.set()
        await release.wait()

    setup.members[2].before_turn_on = pause_power_dispatch
    pending_scene = asyncio.create_task(
        activate_scene(
            hass,
            {
                member.entity_id: scene_state(TARGET_KELVIN, 100)
                for member in setup.members
            },
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert setup.members[1].is_on
        if new_intent == "off":
            await hass.services.async_call(
                "light",
                "turn_off",
                {ATTR_ENTITY_ID: RIGHT},
                blocking=True,
                context=Context(),
            )
        else:
            await hass.services.async_call(
                "light",
                "turn_on",
                {ATTR_ENTITY_ID: RIGHT, ATTR_COLOR_TEMP_KELVIN: 4500},
                blocking=True,
                context=Context(),
            )
        after_new_intent = len(setup.commands)
    finally:
        release.set()
        await pending_scene

    assert setup.members[0].physical_kelvin == TARGET_KELVIN
    assert setup.members[2].physical_kelvin == TARGET_KELVIN
    if new_intent == "off":
        assert not setup.members[1].is_on
    else:
        assert setup.members[1].is_on
        assert setup.members[1].physical_kelvin == 4500
    # Even a CT-only broadcast would adjust a member with a newer colour
    # request. A safety assertion therefore counts the commands, not just OFF
    # physical behaviour of the simulated Zigbee devices.
    assert not any(
        ATTR_COLOR_TEMP_KELVIN in call and call["target"] in {GROUP, RIGHT}
        for call in setup.commands[after_new_intent:]
    ), setup.commands


async def test_new_off_then_on_invalidates_prior_scene_coverage(hass):
    """Previous scene coverage cannot suppress a later, distinct activation."""
    setup = await setup_scene_group(hass)
    right = setup.members[1]
    right.hold_reports = True
    await activate_scene(
        hass,
        {member.entity_id: scene_state(TARGET_KELVIN, 100) for member in setup.members},
    )
    assert hass.states.get(RIGHT).state == STATE_OFF
    assert right.is_on
    assert right.physical_kelvin == TARGET_KELVIN

    # HA still thinks the member is OFF, so there is no state transition for
    # this service. Its explicit OFF intent must nevertheless retire coverage.
    await hass.services.async_call(
        "light",
        "turn_off",
        {ATTR_ENTITY_ID: RIGHT},
        blocking=True,
        context=Context(),
    )
    assert not right.is_on
    right.hold_reports = False
    right.physical_kelvin = 4000
    right.async_write_ha_state()
    await hass.async_block_till_done()
    setup.commands.clear()

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: RIGHT},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert right.is_on
    assert right.physical_kelvin == TARGET_KELVIN
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == RIGHT
    assert not any(call["target"] == GROUP for call in setup.commands)


async def test_newer_scene_colour_wins_when_older_scene_finishes_last(hass):
    """An older operation cannot broadcast its colour after a newer whole scene."""
    setup = await setup_scene_group(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause_old_power_dispatch():
        entered.set()
        await release.wait()

    setup.members[2].before_turn_on = pause_old_power_dispatch
    older_scene = asyncio.create_task(
        activate_scene(
            hass,
            {
                member.entity_id: scene_state(TARGET_KELVIN, 100)
                for member in setup.members
            },
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        # The newer request supplies colour only. The older command already in
        # flight may finish power/brightness, but its deferred colour must not
        # overwrite any member covered by this newer complete operation.
        await asyncio.wait_for(
            hass.services.async_call(
                "scene",
                "apply",
                {
                    "entities": {
                        member.entity_id: {
                            "state": STATE_ON,
                            ATTR_COLOR_TEMP_KELVIN: 4500,
                        }
                        for member in setup.members
                    },
                },
                blocking=True,
                context=Context(),
            ),
            2,
        )
        assert all(member.physical_kelvin == 4500 for member in setup.members)
        after_new_scene = len(setup.commands)
    finally:
        release.set()
        await older_scene

    assert all(member.physical_kelvin == 4500 for member in setup.members)
    assert not any(
        ATTR_COLOR_TEMP_KELVIN in call for call in setup.commands[after_new_scene:]
    ), setup.commands


async def test_group_flush_revalidates_members_after_another_awaited_group_send(
    hass,
    monkeypatch,
):
    """Newer member intent between broadcasts invalidates the next group's plan."""
    setup = await setup_scene_group(hass)
    second_members = [
        RecordingMember(f"light.native_z_member_{index}", setup.commands)
        for index in range(3)
    ]
    for member in second_members:
        member._attr_is_on = True
    second_group = RecordingGroup(second_members, setup.commands)
    second_group.entity_id = "light.native_z_group"
    await hass.data[DATA_COMPONENT].async_add_entities([*second_members, second_group])
    setup.switch._configured_lights.append(second_group.entity_id)
    setup.switch._expand_light_groups()
    await hass.async_block_till_done()
    setup.commands.clear()
    original_group_turn_on = setup.group.async_turn_on
    newer_request_sent = False

    async def first_group_turn_on(**kwargs):
        nonlocal newer_request_sent
        if ATTR_COLOR_TEMP_KELVIN in kwargs and not newer_request_sent:
            newer_request_sent = True
            await hass.services.async_call(
                "light",
                "turn_on",
                {
                    ATTR_ENTITY_ID: second_members[0].entity_id,
                    ATTR_COLOR_TEMP_KELVIN: 4500,
                },
                blocking=True,
                context=Context(),
            )
        await original_group_turn_on(**kwargs)

    monkeypatch.setattr(setup.group, "async_turn_on", first_group_turn_on)
    await activate_scene(
        hass,
        {
            member.entity_id: scene_state(3500, 100)
            for member in [*setup.members, *second_members]
        },
    )

    assert newer_request_sent
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert second_members[0].physical_kelvin == 4500
    assert all(member.physical_kelvin == 3500 for member in second_members[1:])
    assert not any(
        call["target"] == second_group.entity_id for call in setup.colour_commands
    ), setup.commands


async def test_native_group_coverage_does_not_require_individual_turn_on_events(
    hass,
    caplog,
):
    """Group-originated reports work with takeover and bare-only adaptation."""
    setup = await setup_scene_group(hass)
    await prepare_all_off(setup, hass)
    setup.switch._take_over_control = True
    setup.switch._adapt_only_on_bare_turn_on = True
    setup.switch._detect_non_ha_changes = False

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    assert all(
        setup.switch.manager.get_manual_control_attributes(member.entity_id).has_none()
        for member in setup.members
    )
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == GROUP
    assert not [
        record
        for record in caplog.records
        if record.exc_info and isinstance(record.exc_info[1], KeyError)
    ]


async def test_group_off_invalidates_pending_scene_after_profile_is_disabled(
    hass,
):
    """A later group OFF remains authoritative after its adaptive profile stops."""
    setup = await setup_scene_group(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause_power_dispatch():
        entered.set()
        await release.wait()

    setup.members[2].before_turn_on = pause_power_dispatch
    pending_scene = asyncio.create_task(
        activate_scene(
            hass,
            {
                member.entity_id: scene_state(TARGET_KELVIN, 100)
                for member in setup.members
            },
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert setup.members[0].is_on
        assert setup.members[1].is_on
        await setup.switch.async_turn_off()
        # The group OFF command is immediate; its individual MQTT reports lag.
        # Retained HA member states therefore cannot substitute for respecting
        # the newer group request, even after the profile is disabled.
        setup.members[0].hold_reports = True
        setup.members[1].hold_reports = True
        await hass.services.async_call(
            "light",
            "turn_off",
            {ATTR_ENTITY_ID: GROUP},
            blocking=True,
            context=Context(),
        )
        assert not setup.members[0].is_on
        assert not setup.members[1].is_on
        after_group_off = len(setup.commands)
    finally:
        release.set()
        await pending_scene

    assert not setup.members[0].is_on
    assert not setup.members[1].is_on
    assert not any(
        ATTR_COLOR_TEMP_KELVIN in call and call["target"] in {GROUP, LEFT, RIGHT}
        for call in setup.commands[after_group_off:]
    ), setup.commands


async def test_disabling_profile_during_group_flush_cancels_remaining_automatic_colour(
    hass,
    monkeypatch,
):
    """Automatic fallback must recheck profile guards after an awaited group send."""
    setup = await setup_scene_group(hass)
    second_members = [
        RecordingMember(f"light.native_z_member_{index}", setup.commands)
        for index in range(3)
    ]
    second_group = RecordingGroup(second_members, setup.commands)
    second_group.entity_id = "light.native_z_group"
    await hass.data[DATA_COMPONENT].async_add_entities([*second_members, second_group])
    setup.switch._configured_lights.append(second_group.entity_id)
    setup.switch._expand_light_groups()
    await prepare_all_off(setup, hass)
    original_group_turn_on = setup.group.async_turn_on
    disabled_during_colour_send = False

    async def first_group_turn_on(**kwargs):
        nonlocal disabled_during_colour_send
        if ATTR_COLOR_TEMP_KELVIN in kwargs and not disabled_during_colour_send:
            disabled_during_colour_send = True
            await setup.switch.async_turn_off()
        await original_group_turn_on(**kwargs)

    monkeypatch.setattr(setup.group, "async_turn_on", first_group_turn_on)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: [GROUP, second_group.entity_id]},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert disabled_during_colour_send
    assert not setup.switch.is_on
    assert all(member.is_on for member in [*setup.members, *second_members])
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)
    assert all(member.physical_kelvin == 4000 for member in second_members)
    remaining_targets = {
        second_group.entity_id,
        *(member.entity_id for member in second_members),
    }
    assert not any(
        call["target"] in remaining_targets for call in setup.colour_commands
    ), setup.commands


@pytest.mark.parametrize("planner_enabled", [False, True])
async def test_undispatched_split_power_respects_newer_off(
    hass: HomeAssistant,
    planner_enabled: bool,
):
    """A newer OFF cannot be undone by another target's delayed split request."""
    setup = await setup_scene_group(hass)
    setup.switch.manager.native_groups.disabled = not planner_enabled
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold_left():
        entered.set()
        await release.wait()

    setup.members[0].before_turn_on = hold_left
    older = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {
                ATTR_ENTITY_ID: [LEFT, RIGHT],
                ATTR_COLOR_TEMP_KELVIN: 3500,
                ATTR_BRIGHTNESS: 100,
            },
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await hass.services.async_call(
            "light",
            "turn_off",
            {ATTR_ENTITY_ID: RIGHT},
            blocking=True,
            context=Context(),
        )
        after_off = len(setup.commands)
        assert not setup.members[1].is_on
    finally:
        release.set()
        await older
    await hass.async_block_till_done()

    assert not setup.members[1].is_on, setup.commands[after_off:]
    assert not any(
        call["target"] == RIGHT and call["service"] == "turn_on"
        for call in setup.commands[after_off:]
    ), setup.commands[after_off:]


async def test_derived_group_membership_growth_does_not_broaden_pending_repair(
    hass,
    monkeypatch,
):
    """A newly joined sibling is outside the original complete activation intent."""
    setup = await setup_reported_group(hass, **{CONF_ADAPT_DELAY: 1})
    subgroup = await add_subgroup(hass, setup)
    delay = DelayBarrier(
        monkeypatch,
        setup.switch.manager.native_groups,
        "_execute_dispatch",
    )
    turning_on = hass.async_create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: subgroup.entity_id},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(delay.entered.wait(), 2)
        assert delay.delay == 1
        subgroup.members.append(setup.members[0])
        subgroup.async_write_ha_state()
    finally:
        delay.release.set()
        await turning_on
    await hass.async_block_till_done()

    assert setup.members[0].physical_kelvin == 4000
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members[1:])
    assert not any(
        call["target"] in (GROUP, subgroup.entity_id) for call in setup.colour_commands
    ), setup.commands


@pytest.mark.parametrize("retire", ["profile_off", "colour_off", "member_removed"])
async def test_newer_colour_invalidates_old_scene_after_target_is_retired(hass, retire):
    """Deferred explicit colour cannot overwrite a newer unmanaged light request."""
    setup = await setup_scene_group(hass)
    right = setup.members[1]
    entered, release = asyncio.Event(), asyncio.Event()

    async def pause_power_dispatch():
        entered.set()
        await release.wait()

    setup.members[2].before_turn_on = pause_power_dispatch
    older_scene = asyncio.create_task(
        activate_scene(
            hass,
            {member.entity_id: scene_state(3500, 100) for member in setup.members},
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if retire == "profile_off":
            await setup.switch.async_turn_off()
        elif retire == "colour_off":
            await setup.switch.adapt_color_switch.async_turn_off()
        else:
            setup.group.members.remove(right)
            setup.group.async_write_ha_state()
            setup.switch._expand_light_groups()
        await hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: RIGHT, ATTR_COLOR_TEMP_KELVIN: 4500},
            blocking=True,
            context=Context(),
        )
        assert right.physical_kelvin == 4500
        after_newer_colour = len(setup.commands)
    finally:
        release.set()
        await older_scene

    assert right.physical_kelvin == 4500, setup.commands
    assert not any(
        call["target"] == RIGHT and ATTR_COLOR_TEMP_KELVIN in call
        for call in setup.commands[after_newer_colour:]
    ), setup.commands


async def test_group_colour_for_off_member_does_not_cover_later_external_activation(
    hass,
    freezer,
):
    """An ignored colour-only broadcast cannot explain a future physical turn-on."""
    setup = await setup_scene_group(hass)
    right = setup.members[1]
    assert not right.is_on
    assert right.physical_kelvin == 4000
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP, ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert not right.is_on
    assert right.physical_kelvin == 4000
    setup.commands.clear()

    # A bound Zigbee remote later activates the bulb without an HA service call.
    # Fresh context and elapsed time rule out HA's recent-OFF artifact guard.
    freezer.tick(60)
    right.async_set_context(Context())
    right._attr_is_on = True
    right.async_write_ha_state()
    await hass.async_block_till_done()

    assert right.physical_kelvin == TARGET_KELVIN, setup.commands
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == RIGHT


async def test_group_colour_for_off_member_does_not_cover_later_ha_activation(hass):
    """An explicit newer member activation is corrected independently of the group."""
    setup = await setup_scene_group(hass)
    right = setup.members[1]
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP, ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert not right.is_on
    assert right.physical_kelvin == 4000
    setup.commands.clear()

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: RIGHT},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert right.physical_kelvin == TARGET_KELVIN, setup.commands
    assert len(setup.colour_commands) == 1, setup.commands
    assert setup.colour_commands[0]["target"] == RIGHT


async def test_real_group_power_command_keeps_coverage_for_delayed_member_report(
    hass,
    freezer,
):
    """An actual group power command still covers a genuinely delayed ON report."""
    setup = await setup_scene_group(hass)
    await prepare_all_off(setup, hass)
    right = setup.members[1]
    right.hold_reports = True

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert right.is_on
    assert right.physical_kelvin == TARGET_KELVIN
    assert hass.states.get(RIGHT).state == STATE_OFF
    assert len(setup.colour_commands) == 1
    assert setup.colour_commands[0]["target"] == GROUP
    commands_before_report = list(setup.commands)

    freezer.tick(60)
    right.hold_reports = False
    right.async_set_context(Context())
    right.async_write_ha_state()
    await hass.async_block_till_done()

    assert hass.states.get(RIGHT).state == STATE_ON
    assert right.physical_kelvin == TARGET_KELVIN
    assert setup.commands == commands_before_report


@pytest.mark.parametrize("trigger", [EVENT_STATE_CHANGED, EVENT_CALL_SERVICE])
@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("reuse_context", [False, True])
async def test_event_triggered_request_finishes_before_originating_scene_cancel(
    hass,
    planner_enabled,
    reuse_context,
    trigger,
):
    """An event-triggered service is independent even with the scene's Context."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    entered, release = asyncio.Event(), asyncio.Event()
    action_done = asyncio.Event()
    completed_colours = []
    scene_context = Context()
    action_started = False

    async def hold_left():
        entered.set()
        await release.wait()

    setup.members[0].before_turn_on = hold_left

    async def state_triggered_action(event):
        nonlocal action_started
        if action_started:
            return
        if trigger == EVENT_STATE_CHANGED:
            if (
                event.data[ATTR_ENTITY_ID] != RIGHT
                or event.data["old_state"].state != STATE_OFF
                or event.data["new_state"].state != STATE_ON
            ):
                return
        elif (
            event.data["domain"] != "light"
            or event.data["service"] != "turn_on"
            or event.data["service_data"].get(ATTR_ENTITY_ID) != RIGHT
        ):
            return
        action_started = True
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                ATTR_ENTITY_ID: RIGHT,
                ATTR_BRIGHTNESS: 100,
                ATTR_COLOR_TEMP_KELVIN: 3000,
            },
            blocking=True,
            context=event.context if reuse_context else Context(),
        )
        completed_colours.append(setup.members[1].physical_kelvin)
        action_done.set()

    remove_listener = hass.bus.async_listen(trigger, state_triggered_action)
    older_scene = asyncio.create_task(
        hass.services.async_call(
            "scene",
            "apply",
            {
                "entities": {
                    member.entity_id: scene_state(3000, 100) for member in setup.members
                },
            },
            blocking=True,
            context=scene_context,
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(action_done.wait(), 2)
        older_scene.cancel()
        with pytest.raises(asyncio.CancelledError):
            await older_scene
    finally:
        remove_listener()
        release.set()
        await asyncio.gather(older_scene, return_exceptions=True)
    await hass.async_block_till_done()

    assert completed_colours == [3000], setup.commands
    assert setup.members[1].physical_kelvin == 3000, setup.commands
    assert not any(call["target"] == GROUP for call in setup.colour_commands)


async def test_scene_state_triggered_request_does_not_wait_for_scene_flush(
    hass,
    monkeypatch,
):
    """A stored scene's final state event also starts an independent operation."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    scene = "scene.native_boundary"
    await hass.services.async_call(
        "scene",
        "create",
        {
            "scene_id": "native_boundary",
            "entities": {
                member.entity_id: scene_state(3000, 100) for member in setup.members
            },
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    entered, release, action_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    planner = setup.switch.manager.native_groups
    original_flush = planner._flush
    completed_colours = []

    async def hold_scene_flush(batch):
        if len(batch.plan.requests) == len(setup.members):
            entered.set()
            await release.wait()
        await original_flush(batch)

    monkeypatch.setattr(planner, "_flush", hold_scene_flush)

    async def scene_state_action(event):
        if event.data[ATTR_ENTITY_ID] != scene:
            return
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                ATTR_ENTITY_ID: RIGHT,
                ATTR_BRIGHTNESS: 100,
                ATTR_COLOR_TEMP_KELVIN: 3000,
            },
            blocking=True,
            context=event.context,
        )
        completed_colours.append(setup.members[1].physical_kelvin)
        action_done.set()

    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, scene_state_action)
    older_scene = asyncio.create_task(
        hass.services.async_call(
            "scene",
            "turn_on",
            {ATTR_ENTITY_ID: scene},
            blocking=True,
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(action_done.wait(), 2)
        older_scene.cancel()
        with pytest.raises(asyncio.CancelledError):
            await older_scene
    finally:
        remove_listener()
        release.set()
        await asyncio.gather(older_scene, return_exceptions=True)
    await hass.async_block_till_done()

    assert completed_colours == [3000], setup.commands
    assert setup.members[1].physical_kelvin == 3000, setup.commands
    assert not any(call["target"] == GROUP for call in setup.colour_commands)


@pytest.mark.parametrize("worker_identity_available", [False, True])
@pytest.mark.parametrize("service", ["apply", "turn_on"])
async def test_scene_worker_identity_is_an_optional_grouping_optimization(
    hass,
    monkeypatch,
    worker_identity_available,
    service,
):
    """An unfamiliar HA worker keeps correct colour through individual dispatch."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    if not worker_identity_available:
        original_worker = light_reproduce_state._async_reproduce_state

        class UnidentifiedWorker:
            """Preserve HA reproduction but expose no coroutine code identity."""

            def __call__(self, *args, **kwargs):
                return original_worker(*args, **kwargs)

        monkeypatch.setattr(
            light_reproduce_state,
            "_async_reproduce_state",
            UnidentifiedWorker(),
        )

    await activate_scene(
        hass,
        {member.entity_id: scene_state(3000, 100) for member in setup.members},
        service=service,
    )

    assert all(member.physical_kelvin == 3000 for member in setup.members)
    assert all(member.is_on and member.brightness == 100 for member in setup.members)
    assert sorted(command["target"] for command in setup.colour_commands) == (
        [GROUP]
        if worker_identity_available
        else sorted(member.entity_id for member in setup.members)
    ), setup.commands
    assert setup.switch.manager.native_groups.active.get() is None


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("reuse_context", [False, True])
async def test_independent_opaque_scene_cannot_join_older_scene(
    hass,
    planner_enabled,
    reuse_context,
):
    """An opaque scene owns its reproduction even when it inherits a scene context."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    entered, release, action_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    completed_colours = []
    action_started = False

    class OpaqueScene(Scene):
        """An integration scene with no readable scene_config for advance planning."""

        entity_id = "scene.opaque_independent"
        _attr_name = "Opaque independent"

        async def async_activate(self, **_kwargs):
            await light_reproduce_state.async_reproduce_states(
                hass,
                [
                    State(
                        LEFT,
                        STATE_ON,
                        {ATTR_BRIGHTNESS: 100, ATTR_COLOR_TEMP_KELVIN: 3000},
                    ),
                ],
                context=self._context,
            )

    await hass.data[SCENE_COMPONENT].async_add_entities([OpaqueScene()])

    async def hold_left():
        entered.set()
        await release.wait()

    setup.members[0].before_turn_on = hold_left

    async def triggered_scene(event):
        nonlocal action_started
        if (
            action_started
            or event.data[ATTR_ENTITY_ID] != RIGHT
            or event.data["old_state"].state != STATE_OFF
            or event.data["new_state"].state != STATE_ON
        ):
            return
        action_started = True
        await hass.services.async_call(
            "scene",
            "turn_on",
            {ATTR_ENTITY_ID: "scene.opaque_independent"},
            blocking=True,
            context=event.context if reuse_context else Context(),
        )
        completed_colours.append(setup.members[0].physical_kelvin)
        action_done.set()

    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, triggered_scene)
    older_scene = asyncio.create_task(
        hass.services.async_call(
            "scene",
            "apply",
            {
                "entities": {
                    member.entity_id: scene_state(3000, 100) for member in setup.members
                },
            },
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(action_done.wait(), 2)
        older_scene.cancel()
        with pytest.raises(asyncio.CancelledError):
            await older_scene
    finally:
        remove_listener()
        release.set()
        await asyncio.gather(older_scene, return_exceptions=True)
    await hass.async_block_till_done()

    assert completed_colours == [3000], setup.commands
    assert setup.members[0].physical_kelvin == 3000, setup.commands
    assert not any(call["target"] == GROUP for call in setup.colour_commands)
