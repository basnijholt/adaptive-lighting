"""
Circadian Lighting Switch for Home-Assistant.
"""

import logging

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
    log,
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
CONF_MIN_BRIGHT, DEFAULT_MIN_BRIGHT = "min_brightness", 1
CONF_MAX_BRIGHT, DEFAULT_MAX_BRIGHT = "max_brightness", 100
CONF_SLEEP_ENTITY = "sleep_entity"
CONF_SLEEP_STATE = "sleep_state"
CONF_SLEEP_CT, DEFAULT_SLEEP_CT = "sleep_colortemp", 1000
CONF_SLEEP_BRIGHT, DEFAULT_SLEEP_BRIGHT = "sleep_brightness", 1
CONF_DISABLE_ENTITY = "disable_entity"
CONF_DISABLE_STATE = "disable_state"
CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
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
        vol.Optional(CONF_SLEEP_STATE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_SLEEP_CT, default=DEFAULT_SLEEP_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_SLEEP_BRIGHT, default=DEFAULT_SLEEP_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
        vol.Optional(CONF_DISABLE_STATE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(
            CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION
        ): VALID_TRANSITION,
        vol.Optional(CONF_ONCE_ONLY, default=False): cv.boolean,
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

        self._lights_types = {}
        for light in lights_ct:
            self._lights_types[light] = "ct"
        for light in lights_rgb:
            self._lights_types[light] = "rgb"
        for light in lights_xy:
            self._lights_types[light] = "xy"
        for light in lights_brightness:
            self._lights_types[light] = "brightness"
        self._lights = list(self._lights_types.keys())

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
        self._update_switch(transition=self._initial_transition, force=True)
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off circadian lighting."""
        self._state = False
        self.schedule_update_ha_state()
        self._hs_color = None
        self._brightness = None

    @log(with_return=True, logger=_LOGGER)
    def is_sleep(self):
        return (
            self._sleep_entity is not None
            and self.hass.states.get(self._sleep_entity).state in self._sleep_state
        )

    def _color_temperature(self):
        return (
            self._circadian_lighting._colortemp
            if not self.is_sleep()
            else self._sleep_colortemp
        )

    def calc_ct(self):
        return color_temperature_kelvin_to_mired(self._color_temperature())

    def calc_rgb(self):
        return color_temperature_to_rgb(self._color_temperature())

    def calc_xy(self):
        return color_RGB_to_xy(*self.calc_rgb())

    def calc_hs(self):
        return color_xy_to_hs(*self.calc_xy())

    def calc_brightness(self):
        if self._disable_brightness_adjust is True:
            return None
        if self.is_sleep():
            return self._sleep_brightness
        if self._circadian_lighting._percent > 0:
            return self._max_brightness
        delta_brightness = self._max_brightness - self._min_brightness
        procent = (100 + self._circadian_lighting._percent) / 100
        return (delta_brightness * procent) + self._min_brightness

    @log(logger=_LOGGER)
    def _update_switch(self, lights=None, transition=None, force=False):
        if self._once_only and not force:
            return
        self._hs_color = self.calc_hs()
        self._brightness = self.calc_brightness()
        self._adjust_lights(lights or self._lights, transition)

    @log(with_return=True, logger=_LOGGER)
    def _is_disabled(self):
        return (
            self._disable_entity is not None
            and self.hass.states.get(self._disable_entity).state in self._disable_state
        )

    @log(with_return=True, logger=_LOGGER)
    def _should_adjust(self):
        if self._state is not True:
            return False
        if self._is_disabled():
            return False
        return True

    def _adjust_lights(self, lights, transition=None):
        if not self._should_adjust():
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

            light_type = self._lights_types[light]
            if light_type == "ct":
                service_data[ATTR_COLOR_TEMP] = int(self.calc_ct())
            elif light_type == "rgb":
                service_data[ATTR_RGB_COLOR] = tuple(map(int, self.calc_rgb()))
            elif light_type == "xy":
                service_data[ATTR_XY_COLOR] = self.calc_xy()
                if service_data.get(ATTR_BRIGHTNESS, False):
                    service_data[ATTR_WHITE_VALUE] = service_data[ATTR_BRIGHTNESS]

            self.hass.services.call(LIGHT_DOMAIN, SERVICE_TURN_ON, service_data)
            _LOGGER.debug(f"{light} {light_type} Adjusted - {service_data}")

    @log(with_return=True, logger=_LOGGER)
    def light_state_changed(self, entity_id, from_state, to_state):
        if to_state.state == "on" and from_state.state != "on":
            self._update_switch([entity_id], self._initial_transition, force=True)

    @log(with_return=True, logger=_LOGGER)
    def sleep_state_changed(self, entity_id, from_state, to_state):
        if to_state.state in self._sleep_state or from_state.state in self._sleep_state:
            self._update_switch(transition=self._initial_transition, force=True)

    @log(with_return=True, logger=_LOGGER)
    def disable_state_changed(self, entity_id, from_state, to_state):
        if from_state.state in self._disable_state:
            self._update_switch(transition=self._initial_transition, force=True)
