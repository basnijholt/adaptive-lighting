"""
Circadian Lighting Switch for Home-Assistant.
"""

import asyncio
import logging
from itertools import repeat

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
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
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_NAME,
    CONF_PLATFORM,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify
from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_kelvin_to_mired,
    color_temperature_to_rgb,
    color_xy_to_hs,
)

from . import CIRCADIAN_LIGHTING_UPDATE_TOPIC, DOMAIN

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
CONF_ONLY_ONCE = "only_once"

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
        vol.Optional(CONF_ONLY_ONCE, default=False): cv.boolean,
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
            only_once=config.get(CONF_ONLY_ONCE),
        )
        add_devices([switch])

        return True
    else:
        return False


def _difference_between_states(from_state, to_state):
    start = "Lights adjusting because "
    if from_state is None and to_state is None:
        return start + "both states None"
    if from_state is None:
        return start + f"from_state: None, to_state: {to_state}"
    if to_state is None:
        return start + f"from_state: {from_state}, to_state: None"

    changed_attrs = ", ".join(
        [
            f"{key}: {val}"
            for key, val in to_state.attributes.items()
            if from_state.attributes.get(key) != val
        ]
    )
    if from_state.state == to_state.state:
        return start + (
            f"{from_state.entity_id} is still {to_state.state} but"
            f" these attributes changes: {changed_attrs}."
        )
    elif changed_attrs != "":
        return start + (
            f"{from_state.entity_id} changed from {from_state.state} to"
            f" {to_state.state} and these attributes changes: {changed_attrs}."
        )
    else:
        return start + (
            f"{from_state.entity_id} changed from {from_state.state} to"
            f" {to_state.state} and no attributes changed."
        )


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
        only_once,
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
        self._only_once = only_once
        self._lights_types = dict(zip(lights_ct, repeat("ct")))
        self._lights_types.update(zip(lights_rgb, repeat("rgb")))
        self._lights_types.update(zip(lights_xy, repeat("xy")))
        self._lights_types.update(zip(lights_brightness, repeat("brightness")))
        self._lights = list(self._lights_types.keys())

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
        # Add callback
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, CIRCADIAN_LIGHTING_UPDATE_TOPIC, self._update_switch
            )
        )

        # Add listeners
        async_track_state_change(
            self.hass, self._lights, self._light_state_changed, to_state="on"
        )
        track_kwargs = dict(hass=self.hass, action=self._state_changed)
        if self._sleep_entity is not None:
            sleep_kwargs = dict(track_kwargs, entity_ids=self._sleep_entity)
            async_track_state_change(**sleep_kwargs, to_state=self._sleep_state)
            async_track_state_change(**sleep_kwargs, from_state=self._sleep_state)

        if self._disable_entity is not None:
            async_track_state_change(
                **track_kwargs,
                entity_ids=self._disable_entity,
                from_state=self._disable_state,
            )

        if self._state is not None:  # If not None, we got an initial value
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

    async def async_turn_on(self, **kwargs):
        """Turn on circadian lighting."""
        self._state = True
        await self._force_update_switch()

    async def async_turn_off(self, **kwargs):
        """Turn off circadian lighting."""
        self._state = False
        self._hs_color = None
        self._brightness = None

    def _is_sleep(self):
        return (
            self._sleep_entity is not None
            and self.hass.states.get(self._sleep_entity).state in self._sleep_state
        )

    def _color_temperature(self):
        return (
            self._circadian_lighting._colortemp
            if not self._is_sleep()
            else self._sleep_colortemp
        )

    def _calc_ct(self):
        return color_temperature_kelvin_to_mired(self._color_temperature())

    def _calc_rgb(self):
        return color_temperature_to_rgb(self._color_temperature())

    def _calc_xy(self):
        return color_RGB_to_xy(*self._calc_rgb())

    def _calc_hs(self):
        return color_xy_to_hs(*self._calc_xy())

    def _calc_brightness(self) -> float:
        if self._disable_brightness_adjust:
            return
        if self._is_sleep():
            return self._sleep_brightness
        if self._circadian_lighting._percent > 0:
            return self._max_brightness
        delta_brightness = self._max_brightness - self._min_brightness
        percent = (100 + self._circadian_lighting._percent) / 100
        return (delta_brightness * percent) + self._min_brightness

    async def _update_switch(self, lights=None, transition=None, force=False):
        if self._only_once and not force:
            return
        self._hs_color = self._calc_hs()
        self._brightness = self._calc_brightness()
        await self._adjust_lights(lights or self._lights, transition)

    async def _force_update_switch(self, lights=None):
        return await self._update_switch(
            lights, transition=self._initial_transition, force=True
        )

    def _is_disabled(self):
        return (
            self._disable_entity is not None
            and self.hass.states.get(self._disable_entity).state in self._disable_state
        )

    def _should_adjust(self):
        if self._state is not True:
            return False
        if self._is_disabled():
            return False
        return True

    async def _adjust_lights(self, lights, transition):
        if not self._should_adjust():
            return

        if transition is None:
            transition = self._circadian_lighting._transition

        tasks = []
        for light in lights:
            if not is_on(self.hass, light):
                continue

            service_data = {ATTR_ENTITY_ID: light, ATTR_TRANSITION: transition}
            if self._brightness is not None:
                service_data[ATTR_BRIGHTNESS] = int((self._brightness / 100) * 254)

            light_type = self._lights_types[light]
            if light_type == "ct":
                service_data[ATTR_COLOR_TEMP] = int(self._calc_ct())
            elif light_type == "rgb":
                r, g, b = self._calc_rgb()
                service_data[ATTR_RGB_COLOR] = (int(r), int(g), int(b))
            elif light_type == "xy":
                service_data[ATTR_XY_COLOR] = self._calc_xy()
                if service_data.get(ATTR_BRIGHTNESS, False):
                    service_data[ATTR_WHITE_VALUE] = service_data[ATTR_BRIGHTNESS]

            _LOGGER.debug(
                "Scheduling 'light.turn_on' with the following 'service_data': %s",
                service_data,
            )
            tasks.append(
                self.hass.services.async_call(
                    LIGHT_DOMAIN, SERVICE_TURN_ON, service_data
                )
            )
        if tasks:
            await asyncio.wait(tasks)

    async def _light_state_changed(self, entity_id, from_state, to_state):
        assert to_state.state == "on"
        if from_state is None or from_state.state != "on":
            _LOGGER.debug(_difference_between_states(from_state, to_state))
            await self._force_update_switch(lights=[entity_id])

    async def _state_changed(self, entity_id, from_state, to_state):
        _LOGGER.debug(_difference_between_states(from_state, to_state))
        await self._force_update_switch()
