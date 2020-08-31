"""
Circadian Lighting Switch for Home-Assistant.
"""

DEPENDENCIES = ["circadian_lighting", "light"]

import logging
from contextlib import suppress

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE_VALUE,
    ATTR_XY_COLOR,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.light import VALID_TRANSITION, is_on
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.event import track_state_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify
from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_kelvin_to_mired,
    color_temperature_to_rgb,
    color_xy_to_hs,
)

from custom_components.circadian_lighting import (
    CIRCADIAN_LIGHTING_UPDATE_TOPIC,
    DOMAIN,
)

try:
    from homeassistant.components.switch import SwitchEntity
except ImportError:
    from homeassistant.components.switch import SwitchDevice as SwitchEntity


_LOGGER = logging.getLogger(__name__)

ICON = "mdi:theme-light-dark"

CONF_LIGHTS_CT = "lights_ct"
CONF_LIGHTS_RGB = "lights_rgb"
CONF_LIGHTS_XY = "lights_xy"
CONF_LIGHTS_BRIGHT = "lights_brightness"
CONF_DISABLE_BRIGHTNESS_ADJUST = "disable_brightness_adjust"
CONF_MIN_BRIGHT = "min_brightness"
DEFAULT_MIN_BRIGHT = 1
CONF_MAX_BRIGHT = "max_brightness"
DEFAULT_MAX_BRIGHT = 100
CONF_SLEEP_ENTITY = "sleep_entity"
CONF_SLEEP_STATE = "sleep_state"
CONF_SLEEP_CT = "sleep_colortemp"
CONF_SLEEP_BRIGHT = "sleep_brightness"
CONF_DISABLE_ENTITY = "disable_entity"
CONF_DISABLE_STATE = "disable_state"
CONF_INITIAL_TRANSITION = "initial_transition"
DEFAULT_INITIAL_TRANSITION = 1
CONF_ONCE_ONLY = "once_only"

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): "circadian_lighting",
        vol.Optional(CONF_NAME, default="Circadian Lighting"): cv.string,
        vol.Optional(CONF_LIGHTS_CT): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_RGB): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_XY): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_BRIGHT): cv.entity_ids,
        vol.Optional(CONF_DISABLE_BRIGHTNESS_ADJUST, default=False): cv.boolean,
        vol.Optional(CONF_MIN_BRIGHT, default=DEFAULT_MIN_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_MAX_BRIGHT, default=DEFAULT_MAX_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
        vol.Optional(CONF_SLEEP_STATE): cv.string,
        vol.Optional(CONF_SLEEP_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_SLEEP_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
        vol.Optional(CONF_DISABLE_STATE): cv.string,
        vol.Optional(
            CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION
        ): VALID_TRANSITION,
        vol.Optional(CONF_ONCE_ONLY): cv.boolean,
    }
)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Circadian Lighting switches."""
    circadian_lighting = hass.data.get(DOMAIN)
    if circadian_lighting is not None:
        switch = CircadianSwitch(
            hass,
            circadian_lighting,
            name=config.get(CONF_NAME),
            lights_ct=config.get(CONF_LIGHTS_CT, []),
            lights_rgb=config.get(CONF_LIGHTS_RGB, []),
            lights_xy=config.get(CONF_LIGHTS_XY, []),
            lights_brightness=config.get(CONF_LIGHTS_BRIGHT, []),
            disable_brightness_adjust=config.get(CONF_DISABLE_BRIGHTNESS_ADJUST),
            min_brightness=config.get(CONF_MIN_BRIGHT),
            max_brightness=config.get(CONF_MAX_BRIGHT),
            sleep_entity=config.get(CONF_SLEEP_ENTITY),
            sleep_state=config.get(CONF_SLEEP_STATE),
            sleep_colortemp=config.get(CONF_SLEEP_CT),
            sleep_brightness=config.get(CONF_SLEEP_BRIGHT),
            disable_entity=config.get(CONF_DISABLE_ENTITY),
            disable_state=config.get(CONF_DISABLE_STATE),
            initial_transition=config.get(CONF_INITIAL_TRANSITION),
            once_only=config.get(CONF_ONCE_ONLY),
        )
        add_devices([switch])

        return True
    else:
        return False


class CircadianSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Circadian Lighting switch."""

    def __init__(
        self,
        hass,
        circadian_lighting,
        name,
        lights_ct,
        lights_rgb,
        lights_xy,
        lights_brightness,
        disable_brightness_adjust,
        min_brightness,
        max_brightness,
        sleep_entity,
        sleep_state,
        sleep_colortemp,
        sleep_brightness,
        disable_entity,
        disable_state,
        initial_transition,
        once_only,
    ):
        """Initialize the Circadian Lighting switch."""
        self.hass = hass
        self._circadian_lighting = circadian_lighting
        self._name = name
        self._entity_id = f"switch.circadian_lighting_{slugify(name)}"
        self._state = None
        self._icon = ICON
        self._hs_color = None
        self._brightness = None
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
        self._initial_transition = initial_transition
        self._once_only = once_only

        self._lights = lights_ct + lights_rgb + lights_xy + lights_brightness

        # Register callbacks
        dispatcher_connect(hass, CIRCADIAN_LIGHTING_UPDATE_TOPIC, self._update_switch)
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
        return {"hs_color": self._hs_color, "brightness": self._brightness}

    def turn_on(self, **kwargs):
        """Turn on circadian lighting."""
        self._state = True

        # Make initial update
        self._update_switch(self._initial_transition, force=True)

        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off circadian lighting."""
        self._state = False
        self.schedule_update_ha_state()
        self._hs_color = None
        self._brightness = None

    def is_sleep(self):
        is_sleep = (
            self._sleep_entity is not None
            and self.hass.states.get(self._sleep_entity).state == self._sleep_state
        )
        if is_sleep:
            _LOGGER.debug(f"{self._name} in Sleep mode")

        return is_sleep

    @property
    def _color_temperature(self):
        return (
            self._sleep_colortemp
            if self.is_sleep()
            else self._circadian_lighting._colortemp
        )

    def calc_ct(self):
        return color_temperature_kelvin_to_mired(self._color_temperature)

    def calc_rgb(self):
        return color_temperature_to_rgb(self._color_temperature)

    def calc_xy(self):
        return color_RGB_to_xy(*self.calc_rgb())

    def calc_hs(self):
        return color_xy_to_hs(*self.calc_xy())

    def calc_brightness(self):
        if self._disable_brightness_adjust is True:
            return None
        elif self.is_sleep():
            return self._sleep_brightness
        elif self._circadian_lighting._percent > 0:
            return self._max_brightness
        else:
            delta_brightness = self._max_brightness - self._min_brightness
            procent = (100 + self._circadian_lighting._percent) / 100
            return (delta_brightness * procent) + self._min_brightness

    def _update_switch(self, transition=None, force=False):
        if self._once_only and not force:
            return
        self._hs_color = self.calc_hs()
        self._brightness = self.calc_brightness()
        _LOGGER.debug(f"{self._name} Switch Updated")
        self.adjust_lights(self._lights, transition)

    def should_adjust(self):
        if self._state is not True:
            _LOGGER.debug(f"{self._name} off - not adjusting")
            return False
        elif (
            self._disable_entity is not None
            and self.hass.states.get(self._disable_entity).state == self._disable_state
        ):
            _LOGGER.debug(f"{self._name} disabled by {self._disable_entity}")
            return False
        else:
            return True

    def adjust_lights(self, lights, transition=None):
        if not self.should_adjust():
            return

        if transition is None:
            transition = self._circadian_lighting._transition

        for light in lights:
            if not is_on(self.hass, light):
                continue

            service_data = {ATTR_ENTITY_ID: light}
            brightness = self._brightness
            if brightness is not None:
                service_data[ATTR_BRIGHTNESS] = int((brightness / 100) * 254)
            if transition is not None:
                service_data[ATTR_TRANSITION] = transition

            # Set color of array of ct.
            if light in self._lights_ct:
                which = "CT"
                service_data[ATTR_COLOR_TEMP] = int(self.calc_ct())

            # Set color of array of rgb.
            elif light in self._lights_rgb:
                which = "RGB"
                service_data[ATTR_RGB_COLOR] = tuple(map(int, self.calc_rgb()))

            # Set color of array of xy.
            elif light in self._lights_xy:
                which = "XY"
                service_data[ATTR_XY_COLOR] = self.calc_xy()
                if service_data.get(ATTR_BRIGHTNESS, False):
                    service_data[ATTR_WHITE_VALUE] = service_data[ATTR_BRIGHTNESS]

            # Set color of array of brightness.
            elif light in self._lights_brightness:
                which = "Brightness"

            self.hass.services.call(LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
            key_value_strings = [
                f"{k}: {v}" for k, v in service_data.items() if k != ATTR_ENTITY_ID
            ]
            msg = ", ".join(key_value_strings)
            _LOGGER.debug(f"{light} {which} Adjusted - {msg}")

    def light_state_changed(self, entity_id, from_state, to_state):
        with suppress(Exception):
            _LOGGER.debug(f"{entity_id} change from {from_state} to {to_state}")
            if to_state.state == "on" and from_state.state != "on":
                self.adjust_lights([entity_id], self._initial_transition)

    def sleep_state_changed(self, entity_id, from_state, to_state):
        with suppress(Exception):
            _LOGGER.debug(f"{entity_id} change from {from_state} to {to_state}")
            if (
                to_state.state == self._sleep_state
                or from_state.state == self._sleep_state
            ):
                self._update_switch(self._initial_transition, force=True)

    def disable_state_changed(self, entity_id, from_state, to_state):
        with suppress(Exception):
            _LOGGER.debug("{entity_id} change from {from_state} to {to_state}")
            if from_state.state == self._disable_state:
                self._update_switch(self._initial_transition, force=True)
