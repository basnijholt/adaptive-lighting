"""Reported-mode policy must not disable meaningful external-change detection."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.adaptive_lighting.adaptation_utils import (
    LightControlAttributes,
)
from homeassistant.components.adaptive_lighting.const import (
    CONF_DETECT_COLOR_MODE_CHANGES,
    DOMAIN,
    SERVICE_CHANGE_SWITCH_SETTINGS,
)
from homeassistant.components.adaptive_lighting.switch import (
    AdaptiveLightingManager,
    _attributes_have_changed,
    validate,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
)
from homeassistant.core import Context
from homeassistant.util.color import color_temperature_to_rgb

from .test_switch import setup_lights_and_switch


@pytest.mark.parametrize("kelvin", [2000, 2700, 4000, 6500])
@pytest.mark.parametrize("reverse", [False, True])
def test_equivalent_color_readback(kelvin, reverse):
    """An opt-in policy tolerates CT represented as RGB without disabling detection."""
    old = {ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: kelvin}
    new = {ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: color_temperature_to_rgb(kelvin)}
    if reverse:
        old, new = new, old

    # Existing behavior, including Hue scene mode changes, is the default.
    assert _attributes_have_changed(
        "light.test",
        old.copy(),
        new.copy(),
        Context(),
    ) == (LightControlAttributes.COLOR)
    assert (
        _attributes_have_changed(
            "light.test",
            old.copy(),
            new.copy(),
            Context(),
            detect_color_mode_changes=False,
        )
        == LightControlAttributes.NONE
    )


@pytest.mark.parametrize(
    ("brightness", "rgb", "expected"),
    [
        (128, (255, 0, 0), LightControlAttributes.COLOR),
        (255, color_temperature_to_rgb(4000), LightControlAttributes.BRIGHTNESS),
        (255, (255, 0, 0), LightControlAttributes.ALL),
    ],
)
def test_semantic_policy_still_detects_changes(brightness, rgb, expected):
    """Opting out of mode-only detection must retain per-axis value detection."""
    assert (
        _attributes_have_changed(
            "light.test",
            {ATTR_BRIGHTNESS: 128, ATTR_COLOR_TEMP_KELVIN: 4000},
            {ATTR_BRIGHTNESS: brightness, ATTR_RGB_COLOR: rgb},
            Context(),
            detect_color_mode_changes=False,
        )
        == expected
    )


def test_color_mode_policy_default_and_runtime_settings():
    """Existing configurations stay strict; runtime edits retain explicit false."""
    defaults = validate(None, {})
    assert defaults[CONF_DETECT_COLOR_MODE_CHANGES] is True
    configured = validate(None, {CONF_DETECT_COLOR_MODE_CHANGES: False})
    assert configured[CONF_DETECT_COLOR_MODE_CHANGES] is False
    assert validate(None, {}, configured)[CONF_DETECT_COLOR_MODE_CHANGES] is False


def test_observed_homekit_readback():
    """A timestamp-free observer sample differs only in color representation."""
    old = {ATTR_BRIGHTNESS: 115, ATTR_COLOR_TEMP_KELVIN: 2127}
    new = {ATTR_BRIGHTNESS: 114.75, ATTR_RGB_COLOR: (255, 142, 28)}
    assert _attributes_have_changed(
        "light.test",
        old.copy(),
        new.copy(),
        Context(),
    ) == (LightControlAttributes.COLOR)
    assert (
        _attributes_have_changed(
            "light.test",
            old.copy(),
            new.copy(),
            Context(),
            detect_color_mode_changes=False,
        )
        == LightControlAttributes.NONE
    )


async def test_runtime_service_changes_comparison_policy(hass):
    """Changing settings updates the switch field used by subsequent polls."""
    switch, _ = await setup_lights_and_switch(hass)
    assert switch._detect_color_mode_changes is True
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CHANGE_SWITCH_SETTINGS,
        {"entity_id": switch.entity_id, CONF_DETECT_COLOR_MODE_CHANGES: False},
        blocking=True,
    )
    assert switch._detect_color_mode_changes is False
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CHANGE_SWITCH_SETTINGS,
        {"entity_id": switch.entity_id, "use_defaults": "factory"},
        blocking=True,
    )
    assert switch._detect_color_mode_changes is True


@pytest.mark.parametrize("detect_mode", [True, False])
async def test_manager_uses_color_mode_policy(hass, detect_mode):
    """Exercise the polling path, not just the comparison helper."""
    light = "light.test"
    hass.states.async_set(
        light,
        "on",
        {ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: color_temperature_to_rgb(4000)},
    )
    manager = AdaptiveLightingManager(hass)
    manager.last_service_data[light] = {
        ATTR_BRIGHTNESS: 128,
        ATTR_COLOR_TEMP_KELVIN: 4000,
    }
    switch = Mock(_detect_non_ha_changes=True, _detect_color_mode_changes=detect_mode)
    try:
        with patch(
            "homeassistant.components.adaptive_lighting.switch.async_update_entity",
            new_callable=AsyncMock,
        ):
            changed = await manager.significant_change(switch, light, Context())
        assert changed == (
            LightControlAttributes.COLOR if detect_mode else LightControlAttributes.NONE
        )
    finally:
        manager.disable()
