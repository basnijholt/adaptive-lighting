"""Native-group compatibility behavior at HA and device boundaries."""

# pylint: disable=protected-access
import math
from importlib import import_module

import pytest
from homeassistant.components import light
from homeassistant.components.adaptive_lighting import native_groups
from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    ColorMode,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State

from .support.native_lights import GROUP, TARGET_KELVIN
from .support.native_scenarios import activate_scene, scene_state, setup_scene_group


@pytest.mark.parametrize("service", ["apply", "turn_on"])
@pytest.mark.parametrize("nullable", ["brightness", "effect"])
async def test_null_scene_attributes_preserve_complete_group_colour(
    hass: HomeAssistant,
    service: str,
    nullable: str,
) -> None:
    """Omitted HA scene attributes cannot split an otherwise complete colour request."""
    setup = await setup_scene_group(hass)
    levels = [member.brightness for member in setup.members]

    await activate_scene(
        hass,
        {
            member.entity_id: {**scene_state(3500, 100), nullable: None}
            for member in setup.members
        },
        service=service,
        transition=2,
    )

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert [member.brightness for member in setup.members] == (
        levels if nullable == "brightness" else [100, 100, 100]
    )
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 2,
        },
    ]


@pytest.fixture
def legacy_colour_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """Match HA 2025.9.4's ordered list of attribute names, not pairs."""
    monkeypatch.setattr(
        native_groups,
        "COLOR_GROUP",
        [
            "hs_color",
            "color_temp",
            "color_temp_kelvin",
            "rgb_color",
            "rgbw_color",
            "rgbww_color",
            "xy_color",
        ],
    )


@pytest.fixture
def current_colour_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """Select current paired descriptors independently of the test runtime."""
    monkeypatch.setattr(
        native_groups,
        "COLOR_GROUP",
        [
            ("hs_color", "hs_color"),
            ("color_temp_kelvin", "color_temp_kelvin"),
            ("rgb_color", "rgb_color"),
            ("rgbw_color", "rgbw_color"),
            ("rgbww_color", "rgbww_color"),
            ("xy_color", "xy_color"),
        ],
    )


@pytest.mark.parametrize("service", ["apply", "turn_on"])
@pytest.mark.usefixtures("legacy_colour_group")
async def test_legacy_colour_group_preserves_explicit_scene_ct(
    hass: HomeAssistant,
    service: str,
) -> None:
    """A scene without color_mode preserves CT and groups one colour command."""
    setup = await setup_scene_group(hass)
    levels = dict(
        zip((member.entity_id for member in setup.members), (90, 140, 35), strict=True),
    )

    await activate_scene(
        hass,
        {entity: scene_state(3500, level) for entity, level in levels.items()},
        service=service,
        transition=2,
    )

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert all(
        member.brightness == levels[member.entity_id] for member in setup.members
    )
    assert setup.colour_commands == [
        {
            "target": GROUP,
            "service": "turn_on",
            ATTR_COLOR_TEMP_KELVIN: 3500,
            ATTR_TRANSITION: 2,
        },
    ]


@pytest.mark.parametrize("service", ["apply", "turn_on"])
@pytest.mark.usefixtures("legacy_colour_group")
async def test_legacy_colour_group_accepts_brightness_only_scene(
    hass: HomeAssistant,
    service: str,
) -> None:
    """Missing color_mode and colour attributes never prevent scene dispatch."""
    setup = await setup_scene_group(hass)
    levels = dict(
        zip((member.entity_id for member in setup.members), (90, 140, 35), strict=True),
    )

    await activate_scene(
        hass,
        {
            entity: {"state": STATE_ON, "brightness": level}
            for entity, level in levels.items()
        },
        service=service,
        transition=2,
    )

    assert all(member.is_on for member in setup.members)
    assert all(
        member.brightness == levels[member.entity_id] for member in setup.members
    )
    assert all(member.physical_kelvin == TARGET_KELVIN for member in setup.members)


@pytest.mark.parametrize("service", ["apply", "turn_on"])
async def test_legacy_child_mired_alias_retains_complete_scene_boundary(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    service: str,
) -> None:
    """Old HA's extra normalized mired key cannot split or duplicate colour."""
    setup = await setup_scene_group(hass)
    original_preprocess = light.preprocess_turn_on_alternatives

    def legacy_preprocess(hass: HomeAssistant, params: dict) -> None:
        # Old HA gives the mired alias precedence if preprocessing is repeated,
        # even when the exact Kelvin value is already present alongside it.
        if (mired := params.pop("color_temp", None)) is not None:
            params[ATTR_COLOR_TEMP_KELVIN] = math.floor(1_000_000 / mired)
        original_preprocess(hass, params)
        if (kelvin := params.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            params["color_temp"] = math.floor(1_000_000 / kelvin)

    # HA moved the service schema into a separate module in newer releases.
    # Patch its actual global, before our interceptor receives the child call.
    service_module = (
        import_module(light.async_setup_services.__module__)
        if hasattr(light, "async_setup_services")
        else light
    )
    monkeypatch.setattr(
        service_module,
        "preprocess_turn_on_alternatives",
        legacy_preprocess,
    )
    monkeypatch.setattr(
        native_groups,
        "preprocess_turn_on_alternatives",
        legacy_preprocess,
    )
    levels = dict(
        zip((member.entity_id for member in setup.members), (90, 140, 35), strict=True),
    )

    await activate_scene(
        hass,
        {entity: scene_state(3500, level) for entity, level in levels.items()},
        service=service,
        transition=2,
    )

    assert all(member.is_on for member in setup.members)
    assert all(member.physical_kelvin == 3500 for member in setup.members)
    assert all(
        member.brightness == levels[member.entity_id] for member in setup.members
    )
    colour_calls = [
        call
        for call in setup.commands
        if ATTR_COLOR_TEMP_KELVIN in call or "color_temp" in call
    ]
    assert len(colour_calls) == 1, setup.commands
    assert colour_calls[0]["target"] == GROUP
    assert colour_calls[0][ATTR_COLOR_TEMP_KELVIN] == 3500
    assert colour_calls[0][ATTR_TRANSITION] == 2


@pytest.mark.usefixtures("legacy_colour_group")
def test_legacy_scene_mired_fallback_preserves_explicit_ct() -> None:
    """A saved legacy CT-mode scene converts mireds exactly as old HA did."""
    state = State(
        "light.legacy_ct_scene_member",
        STATE_ON,
        {"color_mode": ColorMode.COLOR_TEMP, "color_temp": 285, "brightness": 90},
    )

    assert native_groups.NativeGroupPlanner._scene_params(state, 2) == {
        "brightness": 90,
        ATTR_COLOR_TEMP_KELVIN: 3508,
        ATTR_TRANSITION: 2,
    }


@pytest.mark.usefixtures("current_colour_group")
def test_current_scene_mired_only_ct_mode_is_invalid() -> None:
    """Current HA descriptors reject CT-mode scenes without their Kelvin field."""
    state = State(
        "light.current_ct_scene_member",
        STATE_ON,
        {"color_mode": ColorMode.COLOR_TEMP, "color_temp": 285, "brightness": 90},
    )

    assert native_groups.NativeGroupPlanner._scene_params(state, 2) is None
