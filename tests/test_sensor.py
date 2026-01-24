"""Tests for Adaptive Lighting sensors."""

from homeassistant.components.adaptive_lighting.const import (
    CONF_ENABLE_DIAGNOSTIC_SENSORS,
    CONF_LIGHTS,
    DEFAULT_NAME,
    DOMAIN,
    STATUS_INACTIVE,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.setup import async_setup_component
from homeassistant.util import slugify

from tests.common import MockConfigEntry

ENTITY_LIGHT_1 = "light.light_1"
ENTITY_LIGHT_2 = "light.light_2"


async def _setup_lights(hass: HomeAssistant) -> None:
    template_lights = {
        "light_1": {
            "unique_id": "light_1",
            "friendly_name": "light_1",
            "turn_on": None,
            "turn_off": None,
            "set_level": None,
            "set_temperature": None,
            "set_color": None,
        },
        "light_2": {
            "unique_id": "light_2",
            "friendly_name": "light_2",
            "turn_on": None,
            "turn_off": None,
            "set_level": None,
            "set_temperature": None,
            "set_color": None,
        },
    }
    await async_setup_component(
        hass,
        LIGHT_DOMAIN,
        {LIGHT_DOMAIN: [{"platform": "template", "lights": template_lights}]},
    )
    await hass.async_block_till_done()


async def test_diagnostic_status_sensors_created(hass: HomeAssistant) -> None:
    """Test that status sensors are created as diagnostics when enabled."""
    await _setup_lights(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_LIGHTS: [ENTITY_LIGHT_1, ENTITY_LIGHT_2],
            CONF_ENABLE_DIAGNOSTIC_SENSORS: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ent_reg = entity_registry.async_get(hass)
    entries = [
        reg_entry
        for reg_entry in entity_registry.async_entries_for_config_entry(
            ent_reg,
            entry.entry_id,
        )
        if reg_entry.domain == "sensor" and reg_entry.platform == DOMAIN
    ]
    assert len(entries) == 2

    for light in (ENTITY_LIGHT_1, ENTITY_LIGHT_2):
        unique_id = f"{DOMAIN}_status_{slugify(light)}"
        reg_entry = next(entry for entry in entries if entry.unique_id == unique_id)
        assert reg_entry.entity_category is EntityCategory.DIAGNOSTIC
        state = hass.states.get(reg_entry.entity_id)
        assert state is not None
        assert state.state == STATUS_INACTIVE
