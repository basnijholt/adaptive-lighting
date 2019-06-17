"""
Circadian Lighting Sensor for Home-Assistant.
"""

DEPENDENCIES = ['circadian_lighting']

import logging

from custom_components.circadian_lighting import DOMAIN, CIRCADIAN_LIGHTING_UPDATE_TOPIC, DATA_CIRCADIAN_LIGHTING

from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.entity import Entity

import datetime

_LOGGER = logging.getLogger(__name__)

ICON = 'mdi:theme-light-dark'

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Circadian Lighting sensor."""
    cl = hass.data.get(DATA_CIRCADIAN_LIGHTING)
    if cl:
        cs = CircadianSensor(hass, cl)
        add_devices([cs])

        def update(call=None):
            """Update component."""
            cl._update()
        service_name = "values_update"
        hass.services.register(DOMAIN, service_name, update)
        return True
    else:
        return False

class CircadianSensor(Entity):
    """Representation of a Circadian Lighting sensor."""

    def __init__(self, hass, cl):
        """Initialize the Circadian Lighting sensor."""
        self._cl = cl
        self._name = 'Circadian Values'
        self._entity_id = 'sensor.circadian_values'
        self._state = self._cl.data['percent']
        self._unit_of_measurement = '%'
        self._icon = ICON
        self._hs_color = self._cl.data['hs_color']
        self._attributes = {}
        self._attributes['colortemp'] = self._cl.data['colortemp']
        self._attributes['rgb_color'] = self._cl.data['rgb_color']
        self._attributes['xy_color'] = self._cl.data['xy_color']

        """Register callbacks."""
        dispatcher_connect(hass, CIRCADIAN_LIGHTING_UPDATE_TOPIC, self.update_sensor)

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
        return self._state

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
        return self._hs_color

    @property
    def device_state_attributes(self):
        """Return the attributes of the sensor."""
        return self._attributes

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        self._cl.update()

    def update_sensor(self):
        if self._cl.data is not None:
            self._state = self._cl.data['percent']
            self._hs_color = self._cl.data['hs_color']
            self._attributes['colortemp'] = self._cl.data['colortemp']
            self._attributes['rgb_color'] = self._cl.data['rgb_color']
            self._attributes['xy_color'] = self._cl.data['xy_color']
            _LOGGER.debug("Circadian Lighting Sensor Updated")