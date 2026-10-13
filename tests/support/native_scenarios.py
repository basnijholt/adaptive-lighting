"""Named native-group scenarios and their public Home Assistant service helpers."""

# pylint: disable=protected-access
from homeassistant.components.adaptive_lighting.const import (
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MANUAL_CONTROL,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_TAKE_OVER_CONTROL,
    CONF_TRANSITION,
    DOMAIN,
    SERVICE_SET_MANUAL_CONTROL,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_LIGHTS,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.core import Context
from homeassistant.setup import async_setup_component

from .adaptive import setup_switch
from .native_lights import (
    ATTR_GROUP_ENTITIES,
    GROUP,
    LEFT,
    OFF_MEMBER,
    RIGHT,
    TARGET_KELVIN,
    NativeGroup,
    NativeMember,
    NativeSetup,
    RecordingGroup,
    RecordingMember,
    SceneSetup,
)


async def _install_group(hass, members, group, *, scene_services=False, **options):
    """Register the modeled devices and a native-target adaptation profile."""
    assert await async_setup_component(hass, "light", {})
    if scene_services:
        assert await async_setup_component(hass, "scene", {"scene": []})
    await hass.data[DATA_COMPONENT].async_add_entities([*members, group])
    return await setup_switch(
        hass,
        {
            CONF_LIGHTS: [GROUP],
            CONF_EXPAND_LIGHT_GROUPS: False,
            CONF_INITIAL_TRANSITION: 0,
            CONF_TRANSITION: 0,
            CONF_MIN_COLOR_TEMP: TARGET_KELVIN,
            CONF_MAX_COLOR_TEMP: TARGET_KELVIN,
            CONF_SLEEP_COLOR_TEMP: TARGET_KELVIN,
            CONF_SKIP_REDUNDANT_COMMANDS: True,
            CONF_TAKE_OVER_CONTROL: False,
            **options,
        },
    )


async def _prepare_members(
    hass,
    switch,
    group,
    members,
    *,
    on,
    physical_kelvin,
    cached_kelvin,
    group_brightness=None,
    brightness_adaptation=False,
):
    """Set independent physical/cache values while reactive adaptation is off."""
    await switch.async_turn_off()
    if brightness_adaptation:
        await switch.adapt_brightness_switch.async_turn_on()
    else:
        await switch.adapt_brightness_switch.async_turn_off()
    for member, enabled, brightness, physical, cached in zip(
        members,
        on,
        (80, 110, 26),
        physical_kelvin,
        cached_kelvin,
        strict=True,
    ):
        member._attr_is_on = enabled
        member._attr_brightness = brightness
        member.physical_kelvin = physical
        member._attr_color_temp_kelvin = cached
        member.async_write_ha_state()
    group._attr_is_on = any(on)
    group._attr_color_temp_kelvin = cached_kelvin[0]
    if group_brightness is not None:
        group._attr_brightness = group_brightness
    group.async_write_ha_state()
    await hass.async_block_till_done()
    await switch.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()


async def setup_native_group(hass, **options):
    """A lit member matches target; OFF members have optimistic, stale caches."""
    left, right, off_member = members = [
        NativeMember(entity_id) for entity_id in (LEFT, RIGHT, OFF_MEMBER)
    ]
    group = NativeGroup(members)
    entry, switch = await _install_group(
        hass,
        members,
        group,
        **{CONF_MIN_BRIGHTNESS: 50, CONF_MAX_BRIGHTNESS: 50, **options},
    )
    await _prepare_members(
        hass,
        switch,
        group,
        members,
        on=(True, False, False),
        physical_kelvin=(TARGET_KELVIN, 4000, 3600),
        cached_kelvin=(TARGET_KELVIN,) * 3,
        group_brightness=80,
    )
    assert switch.lights == [GROUP]
    assert ATTR_ENTITY_ID not in hass.states.get(GROUP).attributes
    assert hass.states.get(GROUP).attributes[ATTR_GROUP_ENTITIES] == [
        LEFT,
        RIGHT,
        OFF_MEMBER,
    ]
    return NativeSetup(entry, switch, group, left, right, off_member)


async def _recorded_group(hass, **options):
    """Install a native group that records commands at each device boundary."""
    commands = []
    members = [
        RecordingMember(entity_id, commands) for entity_id in (LEFT, RIGHT, OFF_MEMBER)
    ]
    group = RecordingGroup(members, commands)
    _, switch = await _install_group(
        hass,
        members,
        group,
        scene_services=True,
        **options,
    )
    return SceneSetup(switch, group, members, commands)


async def setup_scene_group(hass):
    """Mixed power: every physical colour is stale but all caches match target."""
    setup = await _recorded_group(hass)
    await _prepare_members(
        hass,
        setup.switch,
        setup.group,
        setup.members,
        on=(True, False, False),
        physical_kelvin=(4000,) * 3,
        cached_kelvin=(TARGET_KELVIN,) * 3,
    )
    setup.commands.clear()
    return setup


async def setup_reported_group(hass, **config):
    """Mixed power: physical and reported colour agree, away from target."""
    setup = await _recorded_group(
        hass,
        **{CONF_MIN_BRIGHTNESS: 50, CONF_MAX_BRIGHTNESS: 50, **config},
    )
    await prepare_reported_members(hass, setup, on=(True, False, False))
    return setup


async def prepare_reported_members(
    hass,
    setup,
    *,
    on,
    kelvin=4000,
    brightness_adaptation=False,
):
    """Arrange matching physical/cache state without synthetic activation work."""
    await _prepare_members(
        hass,
        setup.switch,
        setup.group,
        setup.members,
        on=on,
        physical_kelvin=(kelvin,) * 3,
        cached_kelvin=(kelvin,) * 3,
        group_brightness=80,
        brightness_adaptation=brightness_adaptation,
    )
    setup.commands.clear()


async def turn_on_member(hass, **kwargs):
    """Use the real light service, including event and entity context handling."""
    await hass.services.async_call(
        "light",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: RIGHT, **kwargs},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()


async def activate_scene(hass, entities, *, service="apply", transition=2):
    """Use real HA scene services, including the stored-scene activation path."""
    context = Context()
    if service == "apply":
        await hass.services.async_call(
            "scene",
            "apply",
            {"entities": entities, ATTR_TRANSITION: transition},
            blocking=True,
            context=context,
        )
    else:
        await hass.services.async_call(
            "scene",
            "create",
            {"scene_id": "native_scene_intent", "entities": entities},
            blocking=True,
        )
        await hass.async_block_till_done()
        await hass.services.async_call(
            "scene",
            "turn_on",
            {
                ATTR_ENTITY_ID: "scene.native_scene_intent",
                ATTR_TRANSITION: transition,
            },
            blocking=True,
            context=context,
        )
    await hass.async_block_till_done()


def scene_state(kelvin, brightness):
    """Keep explicit colour separate from scene-specific power and brightness."""
    return {
        "state": STATE_ON,
        ATTR_COLOR_TEMP_KELVIN: kelvin,
        ATTR_BRIGHTNESS: brightness,
    }


async def prepare_all_off(setup, hass):
    """Avoid manufacturing activation events while setting up manual guards."""
    await setup.switch.async_turn_off()
    for member in setup.members:
        member._attr_is_on = False
        member.physical_kelvin = 4000
        member.async_write_ha_state()
    await hass.async_block_till_done()
    await setup.switch.async_turn_on(adapt_lights=False)
    await hass.async_block_till_done()
    setup.commands.clear()


async def add_subgroup(hass, setup):
    """Add a scene target whose members belong to the configured broad group."""
    subgroup = RecordingGroup(setup.members[1:], setup.commands)
    subgroup.entity_id = "light.review_safety_subset"
    subgroup._attr_is_on = False
    await hass.data[DATA_COMPONENT].async_add_entities([subgroup])
    await hass.async_block_till_done()
    setup.commands.clear()
    return subgroup


async def set_manual(hass, switch, light, attribute):
    """Use the public selective-manual-control service."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        {
            ATTR_ENTITY_ID: switch.entity_id,
            CONF_LIGHTS: [light],
            CONF_MANUAL_CONTROL: attribute,
        },
        blocking=True,
    )
