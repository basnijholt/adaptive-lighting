"""
Circadian Lighting Switch for Home-Assistant.
"""

DEPENDENCIES = ['circadian_lighting', 'light']

import logging

from custom_components.circadian_lighting import DOMAIN, CIRCADIAN_LIGHTING_UPDATE_TOPIC, DATA_CIRCADIAN_LIGHTING

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.event import track_state_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.light import (
    is_on, ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_RGB_COLOR, ATTR_TRANSITION,
    ATTR_WHITE_VALUE, ATTR_XY_COLOR, DOMAIN as LIGHT_DOMAIN)
from homeassistant.components.switch import SwitchDevice
from homeassistant.const import (
    ATTR_ENTITY_ID, CONF_NAME, CONF_PLATFORM, STATE_ON,
    SERVICE_TURN_ON)
from homeassistant.util import slugify
from homeassistant.util.color import (
    color_RGB_to_xy, color_temperature_kelvin_to_mired,
    color_temperature_to_rgb, color_xy_to_hs)

_LOGGER = logging.getLogger(__name__)

ICON = 'mdi:theme-light-dark'

CONF_LIGHTS_CT = 'lights_ct'
CONF_LIGHTS_RGB = 'lights_rgb'
CONF_LIGHTS_XY = 'lights_xy'
CONF_LIGHTS_BRIGHT = 'lights_brightness'
CONF_DISABLE_BRIGHTNESS_ADJUST = 'disable_brightness_adjust'
CONF_MIN_BRIGHT = 'min_brightness'
DEFAULT_MIN_BRIGHT = 1
CONF_MAX_BRIGHT = 'max_brightness'
DEFAULT_MAX_BRIGHT = 100
CONF_SLEEP_ENTITY = 'sleep_entity'
CONF_SLEEP_STATE = 'sleep_state'
CONF_SLEEP_CT = 'sleep_colortemp'
CONF_SLEEP_BRIGHT = 'sleep_brightness'
CONF_DISABLE_ENTITY = 'disable_entity'
CONF_DISABLE_STATE = 'disable_state'
DEFAULT_INITIAL_TRANSITION = 1

PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM): 'circadian_lighting',
    vol.Optional(CONF_NAME, default="Circadian Lighting"): cv.string,
    vol.Optional(CONF_LIGHTS_CT): cv.entity_ids,
    vol.Optional(CONF_LIGHTS_RGB): cv.entity_ids,
    vol.Optional(CONF_LIGHTS_XY): cv.entity_ids,
    vol.Optional(CONF_LIGHTS_BRIGHT): cv.entity_ids,
    vol.Optional(CONF_DISABLE_BRIGHTNESS_ADJUST, default=False): cv.boolean,
    vol.Optional(CONF_MIN_BRIGHT, default=DEFAULT_MIN_BRIGHT):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_MAX_BRIGHT, default=DEFAULT_MAX_BRIGHT):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
    vol.Optional(CONF_SLEEP_STATE): cv.string,
    vol.Optional(CONF_SLEEP_CT):
        vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
    vol.Optional(CONF_SLEEP_BRIGHT):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
    vol.Optional(CONF_DISABLE_STATE): cv.string
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Circadian Lighting switches."""
    cl = hass.data.get(DATA_CIRCADIAN_LIGHTING)
    if cl:
        lights_ct = config.get(CONF_LIGHTS_CT)
        lights_rgb = config.get(CONF_LIGHTS_RGB)
        lights_xy = config.get(CONF_LIGHTS_XY)
        lights_brightness = config.get(CONF_LIGHTS_BRIGHT)
        disable_brightness_adjust = config.get(CONF_DISABLE_BRIGHTNESS_ADJUST)
        name = config.get(CONF_NAME)
        min_brightness = config.get(CONF_MIN_BRIGHT)
        max_brightness = config.get(CONF_MAX_BRIGHT)
        sleep_entity = config.get(CONF_SLEEP_ENTITY)
        sleep_state = config.get(CONF_SLEEP_STATE)
        sleep_colortemp = config.get(CONF_SLEEP_CT)
        sleep_brightness = config.get(CONF_SLEEP_BRIGHT)
        disable_entity = config.get(CONF_DISABLE_ENTITY)
        disable_state = config.get(CONF_DISABLE_STATE)
        cs = CircadianSwitch(hass, cl, name, lights_ct, lights_rgb, lights_xy, lights_brightness,
                                disable_brightness_adjust, min_brightness, max_brightness,
                                sleep_entity, sleep_state, sleep_colortemp, sleep_brightness,
                                disable_entity, disable_state)
        add_devices([cs])

        def update(call=None):
            """Update lights."""
            cs.update_switch()
        return True
    else:
        return False


class CircadianSwitch(SwitchDevice, RestoreEntity):
    """Representation of a Circadian Lighting switch."""

    def __init__(self, hass, cl, name, lights_ct, lights_rgb, lights_xy, lights_brightness,
                    disable_brightness_adjust, min_brightness, max_brightness,
                    sleep_entity, sleep_state, sleep_colortemp, sleep_brightness,
                    disable_entity, disable_state):
        """Initialize the Circadian Lighting switch."""
        self.hass = hass
        self._cl = cl
        self._name = name
        self._entity_id = "switch." + slugify("{} {}".format('circadian_lighting', name))
        self._state = None
        self._icon = ICON
        self._hs_color = None
        self._lights_ct = lights_ct
        self._lights_rgb = lights_rgb
        self._lights_xy = lights_xy
        self._lights_brightness = lights_brightness
        self._disable_brightness_adjust = disable_brightness_adjust
        self._min_brightness = min_brightness
        self._max_brightness = max_brightness
        self._sleep_entity = sleep_entity
        self._sleep_state = sleep_state
        self._sleep_colortemp = sleep_colortemp
        self._sleep_brightness = sleep_brightness
        self._disable_entity = disable_entity
        self._disable_state = disable_state
        self._attributes = {}
        self._attributes['hs_color'] = self._hs_color
        self._attributes['brightness'] = None

        self._lights = []
        if lights_ct != None:
            self._lights += lights_ct
        if lights_rgb != None:
            self._lights += lights_rgb
        if lights_xy != None:
            self._lights += lights_xy
        if lights_brightness != None:
            self._lights += lights_brightness

        """Register callbacks."""
        dispatcher_connect(hass, CIRCADIAN_LIGHTING_UPDATE_TOPIC, self.update_switch)
        track_state_change(hass, self._lights, self.light_state_changed)
        if self._sleep_entity is not None:
            track_state_change(hass, self._sleep_entity, self.sleep_state_changed)
        if self._disable_entity is not None:
            track_state_change(hass, self._disable_entity, self.disable_state_changed)

    @property
    def entity_id(self):
        """Return the entity ID of the switch."""
        return self._entity_id

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def is_on(self):
        """Return true if circadian lighting is on."""
        return self._state

    async def async_added_to_hass(self):
        """Call when entity about to be added to hass."""
        # If not None, we got an initial value.
        await super().async_added_to_hass()
        if self._state is not None:
            return

        state = await self.async_get_last_state()
        self._state = state and state.state == STATE_ON

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def hs_color(self):
        return self._hs_color

    @property
    def device_state_attributes(self):
        """Return the attributes of the switch."""
        return self._attributes

    def turn_on(self, **kwargs):
        """Turn on circadian lighting."""
        self._state = True

        # Make initial update
        self.update_switch(DEFAULT_INITIAL_TRANSITION)

        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off circadian lighting."""
        self._state = False
        self.schedule_update_ha_state()
        self._hs_color = None
        self._attributes['hs_color'] = self._hs_color
        self._attributes['brightness'] = None

    def is_sleep(self):
        return self._sleep_entity is not None and self.hass.states.get(self._sleep_entity).state == self._sleep_state

    def calc_ct(self):
        if self.is_sleep():
            _LOGGER.debug(self._name + " in Sleep mode")
            return color_temperature_kelvin_to_mired(self._sleep_colortemp)
        else:
            return color_temperature_kelvin_to_mired(self._cl.data['colortemp'])

    def calc_rgb(self):
        if self.is_sleep():
            _LOGGER.debug(self._name + " in Sleep mode")
            return color_temperature_to_rgb(self._sleep_colortemp)
        else:
            return color_temperature_to_rgb(self._cl.data['colortemp'])

    def calc_xy(self):
        return color_RGB_to_xy(*self.calc_rgb())

    def calc_hs(self):
        return color_xy_to_hs(*self.calc_xy())

    def calc_brightness(self):
        if self._disable_brightness_adjust is True:
            return None
        else:
            if self.is_sleep():
                _LOGGER.debug(self._name + " in Sleep mode")
                return self._sleep_brightness
            else:
                if self._cl.data['percent'] > 0:
                    return self._max_brightness
                else:
                    return ((self._max_brightness - self._min_brightness) * ((100+self._cl.data['percent']) / 100)) + self._min_brightness

    def update_switch(self, transition=None):
        if self._cl.data is not None:
            self._hs_color = self.calc_hs()
            self._attributes['hs_color'] = self._hs_color
            self._attributes['brightness'] = self.calc_brightness()
            _LOGGER.debug(self._name + " Switch Updated")

        self.adjust_lights(self._lights, transition)

    def should_adjust(self):
        if self._state is not True:
            _LOGGER.debug(self._name + " off - not adjusting")
            return False
        elif self._cl.data is None:
            _LOGGER.debug(self._name + " could not retrieve Circadian Lighting data")
            return False
        elif self._disable_entity is not None and self.hass.states.get(self._disable_entity).state == self._disable_state:
            _LOGGER.debug(self._name + " disabled by " + str(self._disable_entity))
            return False
        else:
            return True

    def adjust_lights(self, lights, transition=None):
        if self.should_adjust():
            if transition == None:
                transition = self._cl.data['transition']

            brightness = int((self._attributes['brightness'] / 100) * 254) if self._attributes['brightness'] is not None else None
            mired = int(self.calc_ct()) if self._lights_ct is not None else None
            rgb = tuple(map(int, self.calc_rgb())) if self._lights_rgb is not None else None
            xy = self.calc_xy() if self._lights_xy is not None else None

            for light in lights:
                """Set color of array of ct light if on."""
                if self._lights_ct is not None and light in self._lights_ct and is_on(self.hass, light):
                    service_data = {ATTR_ENTITY_ID: light}
                    if mired is not None:
                        service_data[ATTR_COLOR_TEMP] = mired
                    if brightness is not None:
                        service_data[ATTR_BRIGHTNESS] = brightness
                    if transition is not None:
                        service_data[ATTR_TRANSITION] = transition
                    self.hass.services.call(
                        LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
                    _LOGGER.debug(light + " CT Adjusted - color_temp: " + str(mired) + ", brightness: " + str(brightness) + ", transition: " + str(transition))

                """Set color of array of rgb light if on."""
                if self._lights_rgb is not None and light in self._lights_rgb and is_on(self.hass, light):
                    service_data = {ATTR_ENTITY_ID: light}
                    if rgb is not None:
                        service_data[ATTR_RGB_COLOR] = rgb
                    if brightness is not None:
                        service_data[ATTR_BRIGHTNESS] = brightness
                    if transition is not None:
                        service_data[ATTR_TRANSITION] = transition
                    self.hass.services.call(
                        LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
                    _LOGGER.debug(light + " RGB Adjusted - rgb_color: " + str(rgb) + ", brightness: " + str(brightness) + ", transition: " + str(transition))

                """Set color of array of xy light if on."""
                if self._lights_xy is not None and light in self._lights_xy and is_on(self.hass, light):
                    service_data = {ATTR_ENTITY_ID: light}
                    if xy is not None:
                        service_data[ATTR_XY_COLOR] = xy
                    if brightness is not None:
                        service_data[ATTR_BRIGHTNESS] = brightness
                        service_data[ATTR_WHITE_VALUE] = brightness
                    if transition is not None:
                        service_data[ATTR_TRANSITION] = transition
                    self.hass.services.call(
                        LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
                    _LOGGER.debug(light + " XY Adjusted - xy_color: " + str(xy) + ", brightness: " + str(brightness) + ", transition: " + str(transition) + ", white_value: " + str(brightness))

                """Set color of array of brightness light if on."""
                if self._lights_brightness is not None and light in self._lights_brightness and is_on(self.hass, light):
                    service_data = {ATTR_ENTITY_ID: light}
                    if brightness is not None:
                        service_data[ATTR_BRIGHTNESS] = brightness
                    if transition is not None:
                        service_data[ATTR_TRANSITION] = transition
                    self.hass.services.call(
                        LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
                    _LOGGER.debug(light + " Brightness Adjusted - brightness: " + str(brightness) + ", transition: " + str(transition))

    def light_state_changed(self, entity_id, from_state, to_state):
        try:
            _LOGGER.debug(entity_id + " change from " + str(from_state) + " to " + str(to_state))
            if to_state.state == 'on' and from_state.state != 'on':
                self.adjust_lights([entity_id], DEFAULT_INITIAL_TRANSITION)
        except:
            pass

    def sleep_state_changed(self, entity_id, from_state, to_state):
        try:
            _LOGGER.debug(entity_id + " change from " + str(from_state) + " to " + str(to_state))
            if to_state.state == self._sleep_state or from_state.state == self._sleep_state:
                self.update_switch(DEFAULT_INITIAL_TRANSITION)
        except:
            pass
    
    def disable_state_changed(self, entity_id, from_state, to_state):
        try:
            _LOGGER.debug(entity_id + " change from " + str(from_state) + " to " + str(to_state))
            if from_state.state == self._disable_state:
                self.update_switch(DEFAULT_INITIAL_TRANSITION)
        except:
            pass