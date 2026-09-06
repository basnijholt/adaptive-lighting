"""Diagnostics support for Adaptive Lighting."""

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .adaptation_utils import LightControlAttributes
from .const import (
    ADAPT_BRIGHTNESS_SWITCH,
    ADAPT_COLOR_SWITCH,
    ATTR_ADAPTIVE_LIGHTING_MANAGER,
    DOMAIN,
    SLEEP_MODE_SWITCH,
)
from .switch import AdaptiveLightingManager, AdaptiveSwitch

_REPORTABLE_LIGHT_STATES = {
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
}
_TARGET_ATTRIBUTES = (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
)


def _last_adaptation_values(
    manager: AdaptiveLightingManager,
    light: str,
) -> dict[str, Any] | None:
    """Return latest retained value for each allowlisted adaptation attribute.

    Values may come from different commands because the manager merges partial
    service data per attribute.
    """
    service_data = manager.last_service_data.get(light)
    if service_data is None:
        return None
    target = {
        attribute: (
            list(service_data[attribute])
            if attribute == ATTR_RGB_COLOR
            else service_data[attribute]
        )
        for attribute in _TARGET_ATTRIBUTES
        if attribute in service_data
    }
    return target or None


def _autoreset_seconds(
    manager: AdaptiveLightingManager,
    light: str,
) -> float | None:
    """Return remaining time for a running global manual-control reset."""
    timer = manager.auto_reset_manual_control_timers.get(light)
    if timer is None or not timer.is_running():
        return None
    remaining = timer.remaining_time()
    return round(remaining, 3) if remaining > 0 else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return an allowlisted, on-demand snapshot for one config entry."""
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return {"loaded": False}
    entry_data = domain_data.get(config_entry.entry_id)
    manager = domain_data.get(ATTR_ADAPTIVE_LIGHTING_MANAGER)
    if not isinstance(entry_data, dict) or not isinstance(
        manager,
        AdaptiveLightingManager,
    ):
        return {"loaded": False}
    switch = entry_data.get(SWITCH_DOMAIN)
    if not isinstance(switch, AdaptiveSwitch):
        return {"loaded": False}

    lights: dict[str, Any] = {}
    for index, light in enumerate(sorted(switch.lights), start=1):
        state = hass.states.get(light)
        state_value = "missing"
        if state is not None:
            state_value = (
                state.state
                if state.state in _REPORTABLE_LIGHT_STATES
                else STATE_UNKNOWN
            )
        manual_control = manager.get_manual_control_attributes(light)
        lights[f"light_{index}"] = {
            "state": state_value,
            "global_manager_manual_control": {
                "brightness": bool(
                    manual_control & LightControlAttributes.BRIGHTNESS,
                ),
                "color": bool(manual_control & LightControlAttributes.COLOR),
            },
            "global_manager_autoreset_seconds": _autoreset_seconds(manager, light),
            "global_manager_last_adaptation_values": _last_adaptation_values(
                manager,
                light,
            ),
        }

    return {
        "loaded": True,
        "profile_switches": {
            "profile": switch.is_on,
            "adapt_brightness": entry_data[ADAPT_BRIGHTNESS_SWITCH].is_on,
            "adapt_color": entry_data[ADAPT_COLOR_SWITCH].is_on,
            "sleep_mode": entry_data[SLEEP_MODE_SWITCH].is_on,
        },
        "manager_fact_scope": "global_shared_across_profiles",
        "lights": lights,
    }
