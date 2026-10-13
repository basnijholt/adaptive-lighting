"""Native-group permissions behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized

from .support.native_lights import GROUP, LEFT, RIGHT
from .support.native_scenarios import (
    activate_scene,
    prepare_reported_members,
    scene_state,
    setup_reported_group,
    setup_scene_group,
)


@pytest.mark.parametrize("newer_target", ["all", "helper_group"])
async def test_expanded_targets_preserve_implicit_and_explicit_permissions(
    hass,
    hass_read_only_user,
    monkeypatch,
    newer_target,
):
    """All filters denied entities; an explicit helper group rejects all targets."""
    setup = await setup_reported_group(hass)
    # Keep aggregate power stable to isolate supersession of pending colour
    # from the separate reactive path triggered by a new aggregate ON report.
    await prepare_reported_members(hass, setup, on=(True, True, True))
    hass_read_only_user.mock_policy({"entities": {"entity_ids": {LEFT: True}}})
    planner = setup.switch.manager.native_groups
    entered, release = asyncio.Event(), asyncio.Event()
    original_flush = planner._flush
    first = True

    async def held_flush(batch):
        nonlocal first
        if first:
            first = False
            entered.set()
            await release.wait()
        await original_flush(batch)

    monkeypatch.setattr(planner, "_flush", held_flush)
    entities = [member.entity_id for member in setup.members]
    hass.states.async_set("group.review_all", STATE_ON, {ATTR_ENTITY_ID: entities})
    pending = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: entities},
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        data = {
            ATTR_ENTITY_ID: "all" if newer_target == "all" else "group.review_all",
            ATTR_COLOR_TEMP_KELVIN: 5000,
        }
        if newer_target == "all":
            await hass.services.async_call(
                "light",
                "turn_on",
                data,
                blocking=True,
                context=Context(user_id=hass_read_only_user.id),
            )
        else:
            with pytest.raises(Unauthorized):
                await hass.services.async_call(
                    "light",
                    "turn_on",
                    data,
                    blocking=True,
                    context=Context(user_id=hass_read_only_user.id),
                )
    finally:
        release.set()
        await pending
    await hass.async_block_till_done()
    expected = [5000, 3000, 3000] if newer_target == "all" else [3000] * 3
    assert [
        member.physical_kelvin for member in setup.members
    ] == expected, setup.commands


@pytest.mark.parametrize("service", ["turn_on", "turn_off"])
async def test_rejected_light_request_does_not_cancel_authorized_pending_scene(
    hass,
    hass_read_only_user,
    service,
):
    """A caller without control permission cannot invalidate accepted colour work."""
    setup = await setup_scene_group(hass)
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
        commands_before_denied_call = list(setup.commands)
        params = {ATTR_ENTITY_ID: RIGHT}
        if service == "turn_on":
            params[ATTR_COLOR_TEMP_KELVIN] = 4500
        with pytest.raises(Unauthorized):
            await hass.services.async_call(
                "light",
                service,
                params,
                blocking=True,
                context=Context(user_id=hass_read_only_user.id),
            )
        assert setup.commands == commands_before_denied_call
    finally:
        release.set()
        await older_scene

    assert [member.physical_kelvin for member in setup.members] == [3500] * 3
    assert all(member.is_on for member in setup.members)


async def test_native_member_colour_requires_control_permission(
    hass,
    hass_read_only_user,
):
    """Skipping an already-ON power call cannot bypass HA entity authorization."""
    setup = await setup_reported_group(hass)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: LEFT, ATTR_COLOR_TEMP_KELVIN: 3500},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    await hass.async_block_till_done()
    assert setup.commands == []
    assert [member.physical_kelvin for member in setup.members] == [4000] * 3


async def test_native_colour_rejects_mixed_authorized_and_unauthorized_targets(
    hass,
    hass_read_only_user,
):
    """An allowed member cannot grant control of another explicitly named member."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    hass_read_only_user.mock_policy({"entities": {"entity_ids": {LEFT: True}}})
    assert hass_read_only_user.permissions.check_entity(LEFT, "control")
    assert not hass_read_only_user.permissions.check_entity(RIGHT, "control")
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "light",
            "turn_on",
            {ATTR_ENTITY_ID: [LEFT, RIGHT], ATTR_COLOR_TEMP_KELVIN: 3500},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    await hass.async_block_till_done()
    assert setup.commands == []
    assert [member.physical_kelvin for member in setup.members] == [4000] * 3


async def test_native_member_colour_allows_authorized_subset(hass, hass_read_only_user):
    """A non-admin allowed to control one member can still change that member."""
    setup = await setup_reported_group(hass)
    hass_read_only_user.mock_policy({"entities": {"entity_ids": {LEFT: True}}})
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LEFT, ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
        context=Context(user_id=hass_read_only_user.id),
    )
    await hass.async_block_till_done()
    assert setup.members[0].physical_kelvin == 3500
    assert len(setup.colour_commands) == 1
    assert setup.colour_commands[0]["target"] == LEFT
    assert not any(member.is_on for member in setup.members[1:])


@pytest.mark.parametrize("group_authorized", [False, True])
async def test_native_colour_allows_members_without_requiring_group_permission(
    hass,
    hass_read_only_user,
    group_authorized,
):
    """Group optimization must retain the user's actual entity permissions."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    member_ids = [member.entity_id for member in setup.members]
    hass_read_only_user.mock_policy(
        {
            "entities": {
                "entity_ids": {
                    **dict.fromkeys(member_ids, True),
                    GROUP: group_authorized,
                },
            },
        },
    )
    assert all(
        hass_read_only_user.permissions.check_entity(member, "control")
        for member in member_ids
    )
    assert (
        hass_read_only_user.permissions.check_entity(GROUP, "control")
        is group_authorized
    )
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: member_ids, ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
        context=Context(user_id=hass_read_only_user.id),
    )
    await hass.async_block_till_done()
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    expected_targets = {GROUP} if group_authorized else set(member_ids)
    assert {call["target"] for call in setup.colour_commands} == expected_targets
    assert len(setup.colour_commands) == len(expected_targets)
