"""Native-group scene errors behavior at HA and device boundaries."""

# pylint: disable=protected-access
import asyncio

import pytest
from homeassistant.components.adaptive_lighting.const import TURNING_OFF_DELAY
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.components.switch import (
    DATA_COMPONENT as SWITCH_COMPONENT,
)
from homeassistant.components.switch import (
    SwitchEntity,
)
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError

from .support.native_lights import GROUP, RecordingMember
from .support.native_scenarios import (
    prepare_reported_members,
    scene_state,
    setup_reported_group,
    setup_scene_group,
)


@pytest.mark.parametrize("outcome", ["failure", "cancellation"])
async def test_native_scene_original_failure_retires_transaction(hass, outcome):
    """Failure before dispatch cannot flush deferred colour or retain valid claims."""
    setup = await setup_scene_group(hass)
    planner = setup.switch.manager.native_groups
    registered = hass.services.async_services()["scene"]["apply"]
    entered = asyncio.Event()
    transactions = []
    failure = RuntimeError("scene handler failed")

    async def original(_call):
        transactions.append(planner.active.get())
        entered.set()
        if outcome == "failure":
            raise failure
        await asyncio.Event().wait()

    hass.services.async_register("scene", "apply", original, registered.schema)
    await hass.async_block_till_done()
    task = asyncio.create_task(
        hass.services.async_call(
            "scene",
            "apply",
            {
                "entities": {
                    member.entity_id: scene_state(3500, 100) for member in setup.members
                },
            },
            blocking=True,
            context=Context(),
        ),
    )
    await asyncio.wait_for(entered.wait(), 2)
    if outcome == "failure":
        with pytest.raises(RuntimeError, match="scene handler failed") as exc_info:
            await task
        assert exc_info.value is failure
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    await hass.async_block_till_done()

    assert len(transactions) == 1
    assert transactions[0] is not None
    assert transactions[0].execution.aborted
    assert transactions[0].execution.closed
    assert planner.active.get() is None
    assert setup.commands == []
    assert all(member.physical_kelvin == 4000 for member in setup.members)
    for target in [GROUP, *(member.entity_id for member in setup.members)]:
        claim = planner.take_activation_claim(target)
        assert planner.activation_coverage(target, claim) == (False, False, False)


class BrokenSceneSwitch(SwitchEntity):
    """Expose a real non-light scene target that reports an original error."""

    _attr_should_poll = False
    _attr_is_on = False
    _attr_name = "Broken scene review switch"
    entity_id = "switch.broken_scene_review"

    def __init__(self, error, before=None):
        """Retain the original exception and optional dispatch rendezvous."""
        self.error = error
        self.before = before

    async def async_turn_on(self, **kwargs):  # noqa: ARG002
        """Fail without changing the switch state."""
        if self.before is not None:
            await self.before()
        raise self.error


def _desired_members(setup, brightness=None):
    return {
        member.entity_id: {
            "state": STATE_ON,
            ATTR_COLOR_TEMP_KELVIN: 3500,
            **({ATTR_BRIGHTNESS: brightness} if brightness is not None else {}),
        }
        for member in setup.members
    }


@pytest.mark.parametrize("planner_enabled", [False, True])
@pytest.mark.parametrize("failure_kind", ["light_off", "switch"])
async def test_healthy_scene_colour_survives_unrelated_failure(
    hass,
    monkeypatch,
    planner_enabled,
    failure_kind,
):
    """Ordinary scene errors preserve independent healthy colour and identity."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(True, True, True))
    setup.switch.manager.native_groups.disabled = not planner_enabled
    error = HomeAssistantError("unrelated scene device unreachable")
    if failure_kind == "light_off":
        other = RecordingMember("light.other_scene_review", setup.commands)
        other._attr_is_on = True
        await hass.data[DATA_COMPONENT].async_add_entities([other])

        async def broken(**kwargs):
            raise error

        monkeypatch.setattr(other, "async_turn_off", broken)
        other_state = STATE_OFF
    else:
        other = BrokenSceneSwitch(error)
        await hass.data[SWITCH_COMPONENT].async_add_entities([other])
        other_state = STATE_ON
    with pytest.raises(
        HomeAssistantError,
        match="unrelated scene device unreachable",
    ) as exc_info:
        await hass.services.async_call(
            "scene",
            "apply",
            {
                "entities": {
                    **_desired_members(setup),
                    other.entity_id: {"state": other_state},
                },
            },
            blocking=True,
            context=Context(),
        )
    assert exc_info.value is error
    await hass.async_block_till_done()
    assert [member.physical_kelvin for member in setup.members] == [
        3500,
    ] * 3, setup.commands


@pytest.mark.parametrize("cancel", [False, True])
async def test_partial_scene_error_settles_power_before_colour_or_cancellation(
    hass,
    monkeypatch,
    cancel,
):
    """Parent errors wait for accepted power; cancellation never flushes colour."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    entered, release, failed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    error = HomeAssistantError("unrelated scene device unreachable")

    async def hold_power():
        entered.set()
        await release.wait()

    async def fail_after_power_starts():
        await asyncio.wait_for(entered.wait(), 2)

    setup.members[0].before_turn_on = hold_power
    other = BrokenSceneSwitch(error, fail_after_power_starts)
    await hass.data[SWITCH_COMPONENT].async_add_entities([other])
    planner = setup.switch.manager.native_groups
    original_flush = planner._flush
    original_run = planner._run
    flush_states = []

    async def observe_flush(batch):
        flush_states.append([member.is_on for member in setup.members])
        await original_flush(batch)

    async def observe_invocation_error(batch, invoke):
        async def observed_invoke():
            try:
                return await invoke()
            except Exception:
                # Setting the event does not yield: _run receives the exception
                # before this test resumes and inspects the held power task.
                failed.set()
                raise

        return await original_run(batch, observed_invoke)

    monkeypatch.setattr(planner, "_flush", observe_flush)
    monkeypatch.setattr(planner, "_run", observe_invocation_error)
    task = asyncio.create_task(
        hass.services.async_call(
            "scene",
            "apply",
            {
                "entities": {
                    **_desired_members(setup, 100),
                    other.entity_id: {"state": STATE_ON},
                },
            },
            blocking=True,
            context=Context(),
        ),
    )
    try:
        await asyncio.wait_for(failed.wait(), 2)
        assert not task.done()
        assert not flush_states
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        release.set()
        if cancel:
            await asyncio.gather(task, return_exceptions=True)
        else:
            with pytest.raises(HomeAssistantError) as exc_info:
                await task
            assert exc_info.value is error
    await hass.async_block_till_done()
    if cancel:
        assert not flush_states
        assert not any(
            call.get(ATTR_COLOR_TEMP_KELVIN) == 3500 for call in setup.commands
        )
    else:
        assert flush_states == [[True, True, True]]
        assert [member.physical_kelvin for member in setup.members] == [
            3500,
        ] * 3, setup.commands


async def test_partial_scene_error_preserves_successful_late_report_coverage(
    hass,
    freezer,
):
    """An unrelated error does not turn a late successful ON report into new work."""
    setup = await setup_reported_group(hass)
    await prepare_reported_members(hass, setup, on=(False, False, False))
    member = setup.members[0]
    member.hold_reports = True
    error = HomeAssistantError("unrelated scene device unreachable")
    other = BrokenSceneSwitch(error)
    await hass.data[SWITCH_COMPONENT].async_add_entities([other])
    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            "scene",
            "apply",
            {
                "entities": {
                    **_desired_members(setup, 100),
                    other.entity_id: {"state": STATE_ON},
                },
            },
            blocking=True,
            context=Context(),
        )
    assert exc_info.value is error
    await hass.async_block_till_done()
    assert member.physical_kelvin == 3500
    assert hass.states.is_state(member.entity_id, STATE_OFF)
    commands = list(setup.commands)
    # The delayed report arrives after the recent-OFF polling guard. Advance the
    # clock so the test exercises retained scene coverage without real sleeps.
    freezer.tick(TURNING_OFF_DELAY + 1)
    member.hold_reports = False
    member.async_set_context(Context())
    member.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.is_state(member.entity_id, STATE_ON)
    assert setup.commands == commands
