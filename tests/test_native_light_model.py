"""The shared native-light model obeys power and report contracts without AL."""

# pylint: disable=protected-access
import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
)
from homeassistant.components.light.const import DATA_COMPONENT
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import Context
from homeassistant.setup import async_setup_component

from .support.native_lights import (
    GROUP,
    LEFT,
    OFF_MEMBER,
    RIGHT,
    NativeGroup,
    NativeMember,
    RecordingGroup,
    RecordingMember,
)


@pytest.fixture
async def native_devices(hass):
    """Install real HA light services with no Adaptive Lighting profile."""
    assert await async_setup_component(hass, "light", {})
    commands = []
    members = [
        RecordingMember(entity_id, commands) for entity_id in (LEFT, RIGHT, OFF_MEMBER)
    ]
    group = RecordingGroup(members, commands)
    group._attr_is_on = False
    await hass.data[DATA_COMPONENT].async_add_entities([*members, group])
    return group, members, commands


@pytest.mark.parametrize("initially_lit", [False, True])
@pytest.mark.parametrize(
    ("params", "powers_members"),
    [
        ({}, True),
        ({ATTR_TRANSITION: 2}, True),
        ({ATTR_BRIGHTNESS: 73}, True),
        ({ATTR_BRIGHTNESS: 73, ATTR_TRANSITION: 2}, True),
        ({ATTR_COLOR_TEMP_KELVIN: 3500}, False),
        ({ATTR_COLOR_TEMP_KELVIN: 3500, ATTR_TRANSITION: 2}, False),
    ],
)
async def test_native_model_group_on_distinguishes_power_from_colour(
    hass,
    native_devices,
    initially_lit,
    params,
    powers_members,
):
    """Only power intent wakes OFF members; colour still updates optimistic caches."""
    group, members, commands = native_devices
    group._attr_is_on = members[0]._attr_is_on = initially_lit
    members[0].async_write_ha_state()
    group.async_write_ha_state()
    await hass.async_block_till_done()

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: GROUP, **params},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    expected_power = [initially_lit or powers_members, powers_members, powers_members]
    assert group.is_on == any(expected_power)
    assert hass.states.get(GROUP).state == (
        STATE_ON if any(expected_power) else STATE_OFF
    )
    assert [member.is_on for member in members] == expected_power
    assert [hass.states.get(member.entity_id).state for member in members] == [
        STATE_ON if enabled else STATE_OFF for enabled in expected_power
    ]
    assert [member.brightness for member in members] == [
        params.get(ATTR_BRIGHTNESS, 110),
    ] * 3
    assert [member.physical_kelvin for member in members] == [
        params.get(ATTR_COLOR_TEMP_KELVIN, 4000) if enabled else 4000
        for enabled in expected_power
    ]
    assert [member.color_temp_kelvin for member in members] == [
        params.get(ATTR_COLOR_TEMP_KELVIN, 3000),
    ] * 3
    assert commands == [{"target": GROUP, "service": "turn_on", **params}]
    assert all(not member.attempts for member in members)


@pytest.mark.parametrize("hold_reports", [False, True])
async def test_native_model_group_off_preserves_attributes_and_independent_reports(
    hass,
    native_devices,
    hold_reports,
):
    """OFF is one broadcast, retaining member attributes even while reports lag."""
    group, members, commands = native_devices
    group._attr_is_on = True
    for index, member in enumerate(members):
        member._attr_is_on = index < 2
        member._attr_brightness = 50 + index
        member.physical_kelvin = 4100 + index * 100
        member._attr_color_temp_kelvin = 3100 + index * 100
        member.async_write_ha_state()
    group.async_write_ha_state()
    await hass.async_block_till_done()
    members[0].hold_reports = hold_reports

    await hass.services.async_call(
        "light",
        "turn_off",
        {ATTR_ENTITY_ID: GROUP, ATTR_TRANSITION: 2},
        blocking=True,
        context=Context(),
    )
    await hass.async_block_till_done()

    assert not group.is_on
    assert all(not member.is_on for member in members)
    assert hass.states.get(GROUP).state == STATE_OFF
    assert [hass.states.get(member.entity_id).state for member in members] == [
        STATE_ON if hold_reports else STATE_OFF,
        STATE_OFF,
        STATE_OFF,
    ]
    assert [member.brightness for member in members] == [50, 51, 52]
    assert [member.physical_kelvin for member in members] == [4100, 4200, 4300]
    assert [member.color_temp_kelvin for member in members] == [3100, 3200, 3300]
    assert commands == [
        {"target": GROUP, "service": "turn_off", ATTR_TRANSITION: 2},
    ]
    assert all(not member.attempts for member in members)

    members[0].hold_reports = False
    members[0].async_write_ha_state()
    assert hass.states.get(LEFT).state == STATE_OFF


@pytest.mark.parametrize("device_kind", ["member", "group"])
@pytest.mark.parametrize(
    ("params", "recorded"),
    [
        (
            {ATTR_COLOR_TEMP_KELVIN: 3500, "color_temp": 285},
            {ATTR_COLOR_TEMP_KELVIN: 3500},
        ),
        (
            {ATTR_COLOR_TEMP_KELVIN: 3500, "color_temp": 286},
            {ATTR_COLOR_TEMP_KELVIN: 3500, "color_temp": 286},
        ),
        ({"color_temp": 285}, {"color_temp": 285}),
    ],
    ids=["matching-alias", "contradictory-alias", "alias-only"],
)
async def test_native_model_trace_preserves_distinct_colour_parameters(
    native_devices,
    monkeypatch,
    device_kind,
    params,
    recorded,
):
    """Trace projection preserves raw device input and exposes nonredundant aliases."""
    group, members, commands = native_devices
    group._attr_is_on = True
    for member in members:
        member._attr_is_on = True
    device = members[0] if device_kind == "member" else group
    model = NativeMember if device_kind == "member" else NativeGroup
    original = model.async_turn_on
    received = []

    async def observe_device(self, **kwargs):
        received.append(kwargs)
        await original(self, **kwargs)

    monkeypatch.setattr(model, "async_turn_on", observe_device)
    # Exercise the device boundary directly: HA schemas forbid callers sending
    # both aliases, but older HA supplies both to devices after preprocessing.
    await device.async_turn_on(**params)

    assert received == [params]
    assert commands == [
        {"target": device.entity_id, "service": "turn_on", **recorded},
    ]
    assert members[0].physical_kelvin == params.get(ATTR_COLOR_TEMP_KELVIN, 4000)
