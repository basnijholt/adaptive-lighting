"""Native-group services behavior at HA and device boundaries."""

# pylint: disable=protected-access
from homeassistant.components.adaptive_lighting import native_groups
from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
)
from homeassistant.components.scene import DATA_COMPONENT as SCENE_COMPONENT
from homeassistant.components.scene import Scene
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_SERVICE_REGISTERED,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Context, EventOrigin
from homeassistant.setup import async_setup_component

from .support.native_lights import GROUP, command_params
from .support.native_scenarios import (
    activate_scene,
    scene_state,
    setup_native_group,
    setup_scene_group,
)


async def test_native_planning_installs_scene_services_registered_later(
    hass,
    monkeypatch,
):
    """Scenes loaded after Adaptive Lighting still expose complete intent."""
    setup = await setup_native_group(hass)
    assert not hass.services.has_service("scene", "apply")
    calls = []
    original = setup.group.async_turn_on

    async def record_group(**kwargs):
        calls.append(command_params(kwargs))
        await original(**kwargs)

    monkeypatch.setattr(setup.group, "async_turn_on", record_group)
    assert await async_setup_component(hass, "scene", {"scene": []})
    await hass.async_block_till_done()
    members = [setup.left, setup.right, setup.off_member]

    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in members},
        service="turn_on",
        transition=3,
    )

    assert all(member.is_on and member.physical_kelvin == 3500 for member in members)
    assert calls == [{ATTR_COLOR_TEMP_KELVIN: 3500, ATTR_TRANSITION: 3}]
    assert setup.switch.manager.native_groups.active.get() is None


async def test_native_planning_reinstalls_replaced_scene_handler(hass):
    """A later service replacement is wrapped once and retained on unload."""
    setup = await setup_scene_group(hass)
    planner = setup.switch.manager.native_groups
    registered = hass.services.async_services()["scene"]["apply"]
    received = []

    async def replacement(call):
        # This replacement intentionally handles no devices; the planner must
        # still preserve and invoke the actual newly registered handler once.
        received.append((call, planner.active.get()))

    hass.services.async_register(
        "scene",
        "apply",
        replacement,
        registered.schema,
    )
    await hass.async_block_till_done()
    context = Context()
    await hass.services.async_call(
        "scene",
        "apply",
        {"entities": {"switch.unrelated": {"state": STATE_ON}}},
        blocking=True,
        context=context,
    )
    assert len(received) == 1
    assert received[0][0].context is context
    assert received[0][0].data["entities"]["switch.unrelated"].state == STATE_ON
    assert received[0][1] is None
    assert setup.commands == []

    # A request affecting a configured member proves the replacement actually
    # acquired the planner, rather than merely remaining callable unwrapped.
    left = setup.members[0]
    await hass.services.async_call(
        "scene",
        "apply",
        {
            "entities": {
                left.entity_id: {"state": STATE_ON, ATTR_COLOR_TEMP_KELVIN: 3500},
            },
        },
        blocking=True,
    )
    assert len(received) == 2
    assert received[1][1] is not None
    assert received[1][1].execution.closed
    assert not received[1][1].execution.aborted
    assert left.physical_kelvin == 3500
    assert len(setup.colour_commands) == 1

    planner.disable()
    assert hass.services.async_services()["scene"]["apply"].job.target is replacement
    await hass.services.async_call(
        "scene",
        "apply",
        {"entities": {"switch.unrelated": {"state": STATE_OFF}}},
        blocking=True,
    )
    assert len(received) == 3
    assert received[2][1] is None


async def test_native_planning_passes_opaque_integration_scene_through(hass):
    """A vendor scene has no HA state definition and keeps its original call."""
    setup = await setup_scene_group(hass)
    activations = []
    planner = setup.switch.manager.native_groups

    class OpaqueScene(Scene):
        """An integration scene whose intended device state is not exposed."""

        entity_id = "scene.opaque_integration"
        _attr_name = "Opaque integration"

        async def async_activate(self, **kwargs):
            activations.append((kwargs, self._context, planner.active.get()))

    await hass.data[SCENE_COMPONENT].async_add_entities([OpaqueScene()])
    context = Context()
    await hass.services.async_call(
        "scene",
        "turn_on",
        {ATTR_ENTITY_ID: "scene.opaque_integration", ATTR_TRANSITION: 4},
        blocking=True,
        context=context,
    )
    await hass.async_block_till_done()

    assert activations == [({ATTR_TRANSITION: 4}, context, None)]
    assert setup.commands == []
    assert hass.states.get("scene.opaque_integration").state is not None


async def test_native_planning_handles_synchronous_service_registration(
    hass,
    monkeypatch,
):
    """Legacy HA registration events cannot recursively wrap the same handler."""
    bus_type = type(hass.bus)
    original_fire = bus_type.async_fire_internal

    def fire_registration_immediately(
        bus,
        event_type,
        event_data=None,
        origin=EventOrigin.local,
        context=None,
        time_fired=None,
    ):
        # New HA queues nested bus events. Exercise the older synchronous
        # contract on new HA too; old HA already dispatches this way.
        if event_type == EVENT_SERVICE_REGISTERED and hasattr(bus, "_async_dispatch"):
            return bus._async_dispatch(
                event_type,
                event_data,
                origin,
                context,
                time_fired,
            )
        return original_fire(bus, event_type, event_data, origin, context, time_fired)

    monkeypatch.setattr(bus_type, "async_fire_internal", fire_registration_immediately)
    assert await async_setup_component(hass, "scene", {"scene": []})
    originals = {
        service: registered.job.target
        for service, registered in hass.services.async_services()["scene"].items()
        if service in {"apply", "turn_on"}
    }
    setup = await setup_scene_group(hass)

    await activate_scene(
        hass,
        {member.entity_id: scene_state(3500, 100) for member in setup.members},
        transition=2,
    )

    assert all(
        member.is_on and member.physical_kelvin == 3500 for member in setup.members
    )
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 2,
        },
    ]
    setup.switch.manager.native_groups.disable()
    assert {
        service: hass.services.async_services()["scene"][service].job.target
        for service in originals
    } == originals


async def test_native_planning_retries_after_failed_handler_install(
    hass,
    monkeypatch,
):
    """An installation failure cannot block a later legitimate registration."""
    setup = await setup_scene_group(hass)
    planner = setup.switch.manager.native_groups
    registered = hass.services.async_services()["scene"]["apply"]
    original_interceptor = native_groups.setup_service_call_interceptor
    attempts = []
    received = []

    def fail_once(*args, **kwargs):
        attempts.append(args[1:3])
        if len(attempts) == 1:
            message = "test interceptor installation failure"
            raise RuntimeError(message)
        return original_interceptor(*args, **kwargs)

    async def replacement(call):
        received.append(call)

    monkeypatch.setattr(native_groups, "setup_service_call_interceptor", fail_once)
    hass.services.async_register("scene", "apply", replacement, registered.schema)
    await hass.async_block_till_done()
    assert hass.services.async_services()["scene"]["apply"].job.target is replacement

    hass.services.async_register("scene", "apply", replacement, registered.schema)
    await hass.async_block_till_done()
    assert attempts == [("scene", "apply"), ("scene", "apply")]
    assert (
        hass.services.async_services()["scene"]["apply"].job.target is not replacement
    )
    await hass.services.async_call(
        "scene",
        "apply",
        {"entities": {"switch.unrelated": {"state": STATE_ON}}},
        blocking=True,
    )
    assert len(received) == 1

    planner.disable()
    assert hass.services.async_services()["scene"]["apply"].job.target is replacement
