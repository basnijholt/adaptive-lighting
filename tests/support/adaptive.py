"""Integration setup and observations at the Home Assistant service boundary."""

from homeassistant.components.adaptive_lighting.const import (
    CONF_INTERCEPT,
    DEFAULT_NAME,
    DOMAIN,
)
from homeassistant.components.adaptive_lighting.switch import (
    AdaptiveSwitch,
    is_our_context,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, EVENT_CALL_SERVICE, SERVICE_TURN_ON
from homeassistant.core import callback

from tests.common import MockConfigEntry


async def setup_switch(hass, extra_data) -> tuple[MockConfigEntry, AdaptiveSwitch]:
    """Create the switch entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_INTERCEPT: False,
            **extra_data,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    switch = hass.data[DOMAIN][entry.entry_id][SWITCH_DOMAIN]
    return entry, switch


def track_adaptive_light_calls(hass, *, ours_only=True):
    """Capture commands emitted by Adaptive Lighting at the HA service boundary."""
    calls = []

    @callback
    def track(event):
        if (
            event.data["domain"] == LIGHT_DOMAIN
            and event.data["service"] == SERVICE_TURN_ON
            and (not ours_only or is_our_context(event.context))
        ):
            calls.append(event.data["service_data"])

    hass.bus.async_listen(EVENT_CALL_SERVICE, track)
    return calls
