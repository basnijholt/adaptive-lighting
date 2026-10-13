"""Native-group targets behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import ATTR_ENTITY_ID, CONF_LIGHTS, STATE_ON
from homeassistant.core import Context
from homeassistant.setup import async_setup_component

from .support.native_lights import (
    GROUP,
    RecordingGroup,
    RecordingMember,
    SceneSetup,
)
from .support.native_scenarios import (
    prepare_reported_members,
    setup_reported_group,
)


@pytest.mark.parametrize("newer_target", ["all", "members", "helper_group"])
@pytest.mark.parametrize("service", ["turn_on", "turn_off"])
async def test_expanded_targets_supersede_pending_adaptive_colour(
    hass,
    monkeypatch,
    newer_target,
    service,
):
    """An accepted newer request cancels colour for its actual light targets."""
    setup = await setup_reported_group(hass)
    # Keep aggregate power stable to isolate supersession of pending colour
    # from the separate reactive path triggered by a new aggregate ON report.
    await prepare_reported_members(hass, setup, on=(True, True, True))
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
    target = {
        "all": "all",
        "members": entities,
        "helper_group": "group.review_all",
    }[newer_target]
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
        await hass.services.async_call(
            "light",
            service,
            {
                ATTR_ENTITY_ID: target,
                **({ATTR_COLOR_TEMP_KELVIN: 5000} if service == "turn_on" else {}),
            },
            blocking=True,
            context=Context(),
        )
    finally:
        release.set()
        await pending
    await hass.async_block_till_done()
    if service == "turn_on":
        assert [member.physical_kelvin for member in setup.members] == [
            5000,
        ] * 3, setup.commands
    else:
        assert all(not member.is_on for member in setup.members), setup.commands


@pytest.mark.parametrize("brightness_adaptation", [False, True])
async def test_native_colour_call_combines_group_and_unrelated_member(
    hass,
    brightness_adaptation,
):
    """Mixed targets retain one original group command and one member command."""
    assert await async_setup_component(hass, "light", {})
    other_commands = []
    other_members = [
        RecordingMember(f"light.other_native_{index}", other_commands)
        for index in range(3)
    ]
    other_group = RecordingGroup(other_members, other_commands)
    other_group.entity_id = "light.other_native_group"
    await hass.data[DATA_COMPONENT].async_add_entities([*other_members, other_group])
    setup = await setup_reported_group(
        hass,
        **{CONF_LIGHTS: [GROUP, other_group.entity_id]},
    )
    await prepare_reported_members(
        hass,
        setup,
        on=(False, False, False),
        brightness_adaptation=brightness_adaptation,
    )
    other_setup = SceneSetup(setup.switch, other_group, other_members, other_commands)
    await prepare_reported_members(
        hass,
        other_setup,
        on=(True, False, False),
        brightness_adaptation=brightness_adaptation,
    )
    setup.commands.clear()
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: [GROUP, other_members[0].entity_id],
            ATTR_COLOR_TEMP_KELVIN: 3500,
        },
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()
    assert setup.commands == [
        {"target": GROUP, "service": "turn_on", ATTR_COLOR_TEMP_KELVIN: 3500},
    ]
    assert other_commands == [
        {
            "target": other_members[0].entity_id,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
        },
    ]
    assert other_members[0].physical_kelvin == 3500
    assert all(not member.is_on for member in setup.members + other_members[1:])
    assert all(
        member.physical_kelvin == 4000 for member in setup.members + other_members[1:]
    )
