"""
Circadian Lighting Sensor for Home-Assistant.
"""

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import CIRCADIAN_LIGHTING_UPDATE_TOPIC, DEFAULT_PROFILE, DOMAIN

ICON = "mdi:theme-light-dark"


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Circadian Lighting sensor."""
    sensors = [CircadianSensor(hass, circadian_lighting) for circadian_lighting in hass.data[DOMAIN].values()]
    add_devices(sensors, True)
    return True


class CircadianSensor(Entity):
    """Representation of a Circadian Lighting sensor."""

    def __init__(self, hass, circadian_lighting):
        """Initialize the Circadian Lighting sensor."""
        self._circadian_lighting = circadian_lighting
        self._name = "Circadian Values"
        self._entity_id = "sensor.circadian_values"
        profile = circadian_lighting._profile
        if profile != DEFAULT_PROFILE:
            self._name += f" {profile}"
            self._entity_id += f"_{profile.lower()}"
        self._unit_of_measurement = "%"
        self._icon = ICON

    @property
    def entity_id(self):
        """Return the entity ID of the sensor."""
        return self._entity_id

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._circadian_lighting._percent

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def hs_color(self):
        return self._circadian_lighting._hs_color

    @property
    def device_state_attributes(self):
        """Return the attributes of the sensor."""
        return {
            "colortemp": self._circadian_lighting._colortemp,
            "rgb_color": self._circadian_lighting._rgb_color,
            "xy_color": self._circadian_lighting._xy_color,
        }

    @property
    def should_poll(self) -> bool:
        """Disable polling."""
        return False

    async def async_added_to_hass(self) -> None:
        """Connect dispatcher to signal from CircadianLighting object."""
        self.async_on_remove(async_dispatcher_connect(self.hass, CIRCADIAN_LIGHTING_UPDATE_TOPIC, self._update_callback))

    @callback
    def _update_callback(self) -> None:
        """Triggers update of properties."""
        self.async_schedule_update_ha_state(force_refresh=False)
