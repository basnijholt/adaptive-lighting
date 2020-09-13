"""
Adaptive Lighting Component for Home-Assistant.

This component calculates color temperature and brightness to synchronize
your color changing lights with perceived color temperature of the sky throughout
the day. This gives your environment a more natural feel, with cooler whites during
the midday and warmer tints near twilight and dawn.

In addition, the component sets your lights to a nice warm white at 1% in "Sleep" mode,
which is far brighter than starlight but won't reset your adaptive rhythm or break down
too much rhodopsin in your eyes.

Human circadian rhythms are heavily influenced by ambient light levels and
hues. Hormone production, brainwave activity, mood and wakefulness are
just some of the cognitive functions tied to cyclical natural light.
http://en.wikipedia.org/wiki/Zeitgeber

Here's some further reading:

http://www.cambridgeincolour.com/tutorials/sunrise-sunset-calculator.htm
http://en.wikipedia.org/wiki/Color_temperature

Technical notes: I had to make a lot of assumptions when writing this app
*   There are no considerations for weather or altitude, but does use your
    hub's location to calculate the sun position.
*   The component doesn't calculate a true "Blue Hour" -- it just sets the
    lights to 2700K (warm white) until your hub goes into Night mode
"""

import asyncio
import logging
from datetime import timedelta
from itertools import repeat

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
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
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
)
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_time_interval,
)
from homeassistant.helpers.sun import get_astral_location
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify
from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_kelvin_to_mired,
    color_temperature_to_rgb,
    color_xy_to_hs,
)
from .const import (
    ICON,
    DOMAIN,
    SUN_EVENT_NOON,
    SUN_EVENT_MIDNIGHT,
    CONF_LIGHTS_BRIGHTNESS,
    CONF_LIGHTS_MIRED,
    CONF_LIGHTS_RGB,
    CONF_LIGHTS_XY,
    CONF_DISABLE_BRIGHTNESS_ADJUST,
    CONF_DISABLE_ENTITY,
    CONF_DISABLE_STATE,
    CONF_INITIAL_TRANSITION,
    DEFAULT_INITIAL_TRANSITION,
    CONF_INTERVAL,
    DEFAULT_INTERVAL,
    CONF_MAX_BRIGHTNESS,
    DEFAULT_MAX_BRIGHTNESS,
    CONF_MAX_CT,
    DEFAULT_MAX_CT,
    CONF_MIN_BRIGHTNESS,
    DEFAULT_MIN_BRIGHTNESS,
    CONF_MIN_CT,
    DEFAULT_MIN_CT,
    CONF_ONLY_ONCE,
    CONF_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_BRIGHTNESS,
    CONF_SLEEP_CT,
    DEFAULT_SLEEP_CT,
    CONF_SLEEP_ENTITY,
    CONF_SLEEP_STATE,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_TIME,
    CONF_TRANSITION,
    DEFAULT_TRANSITION,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=10)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): DOMAIN,
        vol.Optional(CONF_NAME, default="Adaptive Lighting"): cv.string,
        vol.Optional(CONF_LIGHTS_BRIGHTNESS): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_MIRED): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_RGB): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_XY): cv.entity_ids,
        vol.Optional(CONF_DISABLE_BRIGHTNESS_ADJUST, default=False): cv.boolean,
        vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
        vol.Optional(CONF_DISABLE_STATE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(
            CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION
        ): VALID_TRANSITION,
        vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): cv.time_period,
        vol.Optional(CONF_MAX_BRIGHTNESS, default=DEFAULT_MAX_BRIGHTNESS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_MAX_CT, default=DEFAULT_MAX_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_MIN_BRIGHTNESS, default=DEFAULT_MIN_BRIGHTNESS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_MIN_CT, default=DEFAULT_MIN_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_ONLY_ONCE, default=False): cv.boolean,
        vol.Optional(CONF_SLEEP_BRIGHTNESS, default=DEFAULT_SLEEP_BRIGHTNESS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_SLEEP_CT, default=DEFAULT_SLEEP_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
        vol.Optional(CONF_SLEEP_STATE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_SUNRISE_OFFSET, default=0): cv.time_period,
        vol.Optional(CONF_SUNRISE_TIME): cv.time,
        vol.Optional(CONF_SUNSET_OFFSET, default=0): cv.time_period,
        vol.Optional(CONF_SUNSET_TIME): cv.time,
        vol.Optional(CONF_TRANSITION, default=DEFAULT_TRANSITION): VALID_TRANSITION,
    }
)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Adaptive Lighting switches."""
    switch = AdaptiveSwitch(
        hass,
        name=config[CONF_NAME],
        lights_brightness=config.get(CONF_LIGHTS_BRIGHTNESS, []),
        lights_mired=config.get(CONF_LIGHTS_MIRED, []),
        lights_rgb=config.get(CONF_LIGHTS_RGB, []),
        lights_xy=config.get(CONF_LIGHTS_XY, []),
        disable_brightness_adjust=config[CONF_DISABLE_BRIGHTNESS_ADJUST],
        disable_entity=config.get(CONF_DISABLE_ENTITY),
        disable_state=config.get(CONF_DISABLE_STATE),
        initial_transition=config[CONF_INITIAL_TRANSITION],
        interval=config[CONF_INTERVAL],
        max_brightness=config[CONF_MAX_BRIGHTNESS],
        max_colortemp=config[CONF_MAX_CT],
        min_brightness=config[CONF_MIN_BRIGHTNESS],
        min_colortemp=config[CONF_MIN_CT],
        only_once=config[CONF_ONLY_ONCE],
        sleep_brightness=config[CONF_SLEEP_BRIGHTNESS],
        sleep_colortemp=config[CONF_SLEEP_CT],
        sleep_entity=config.get(CONF_SLEEP_ENTITY),
        sleep_state=config.get(CONF_SLEEP_STATE),
        sunrise_offset=config[CONF_SUNRISE_OFFSET],
        sunrise_time=config.get(CONF_SUNRISE_TIME),
        sunset_offset=config[CONF_SUNSET_OFFSET],
        sunset_time=config.get(CONF_SUNSET_TIME),
        transition=config[CONF_TRANSITION],
    )
    add_devices([switch])


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


class AdaptiveSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Adaptive Lighting switch."""

    def __init__(
        self,
        hass,
        name,
        lights_brightness,
        lights_mired,
        lights_rgb,
        lights_xy,
        disable_brightness_adjust,
        disable_entity,
        disable_state,
        initial_transition,
        interval,
        max_brightness,
        max_colortemp,
        min_brightness,
        min_colortemp,
        only_once,
        sleep_brightness,
        sleep_colortemp,
        sleep_entity,
        sleep_state,
        sunrise_offset,
        sunrise_time,
        sunset_offset,
        sunset_time,
        transition,
    ):
        """Initialize the Adaptive Lighting switch."""
        self.hass = hass
        self._name = name
        self._entity_id = f"switch.adaptive_lighting_{slugify(name)}"
        self._icon = ICON

        # Create lights dict
        self._lights_types = dict(zip(lights_brightness, repeat("brightness")))
        self._lights_types.update(zip(lights_mired, repeat("mired")))
        self._lights_types.update(zip(lights_rgb, repeat("rgb")))
        self._lights_types.update(zip(lights_xy, repeat("xy")))
        self._lights = list(self._lights_types.keys())

        # Set attributes from arguments
        self._disable_brightness_adjust = disable_brightness_adjust
        self._disable_entity = disable_entity
        self._disable_state = disable_state
        self._initial_transition = initial_transition
        self._interval = interval
        self._max_brightness = max_brightness
        self._max_colortemp = max_colortemp
        self._min_brightness = min_brightness
        self._min_colortemp = min_colortemp
        self._only_once = only_once
        self._sleep_brightness = sleep_brightness
        self._sleep_colortemp = sleep_colortemp
        self._sleep_entity = sleep_entity
        self._sleep_state = sleep_state
        self._sunrise_offset = sunrise_offset
        self._sunrise_time = sunrise_time
        self._sunset_offset = sunset_offset
        self._sunset_time = sunset_time
        self._transition = transition

        # Initialize attributes that will be set in self._update_attrs
        self._percent = None
        self._brightness = None
        self._colortemp_kelvin = None
        self._colortemp_mired = None
        self._rgb_color = None
        self._xy_color = None
        self._hs_color = None

        # Set and unset tracker in async_turn_on and async_turn_off
        self.unsub_tracker = None

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
        """Return true if adaptive lighting is on."""
        return self.unsub_tracker is not None

    async def async_added_to_hass(self):
        """Call when entity about to be added to hass."""
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

        last_state = await self.async_get_last_state()
        if last_state and last_state.state == STATE_ON:
            await self.async_turn_on()

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return the attributes of the switch."""
        attrs = {
            "percent": self._percent,
            "brightness": self._brightness,
            "colortemp_kelvin": self._colortemp_kelvin,
            "colortemp_mired": self._colortemp_mired,
            "rgb_color": self._rgb_color,
            "xy_color": self._xy_color,
            "hs_color": self._hs_color,
        }
        if not self.is_on:
            return {key: None for key in attrs.keys()}
        return attrs

    async def async_turn_on(self, **kwargs):
        """Turn on adaptive lighting."""
        await self._update_lights(transition=self._initial_transition, force=True)
        self.unsub_tracker = async_track_time_interval(
            self.hass, self._async_update_at_interval, self._interval
        )

    async def async_turn_off(self, **kwargs):
        """Turn off adaptive lighting."""
        if self.is_on:
            self.unsub_tracker()
            self.unsub_tracker = None

    async def _update_attrs(self):
        """Update Adaptive Values."""
        # Setting all values because this method takes <0.5ms to execute.
        self._percent = self._calc_percent()
        self._brightness = self._calc_brightness()
        self._colortemp_kelvin = self._calc_colortemp_kelvin()
        self._colortemp_mired = color_temperature_kelvin_to_mired(
            self._colortemp_kelvin
        )
        self._rgb_color = color_temperature_to_rgb(self._colortemp_kelvin)
        self._xy_color = color_RGB_to_xy(*self._rgb_color)
        self._hs_color = color_xy_to_hs(*self._xy_color)
        self.async_write_ha_state()
        _LOGGER.debug("'_update_attrs' called for %s", self._name)

    async def _async_update_at_interval(self, now=None):
        await self._update_lights(force=False)

    async def _update_lights(self, lights=None, transition=None, force=False):
        await self._update_attrs()
        if self._only_once and not force:
            return
        await self._adjust_lights(lights or self._lights, transition)

    def _get_sun_events(self, date):
        def _replace_time(date, key):
            other_date = getattr(self, f"_{key}_time")
            return date.replace(
                hour=other_date.hour,
                minute=other_date.minute,
                second=other_date.second,
                microsecond=other_date.microsecond,
            )

        location = get_astral_location(self.hass)
        sunrise = (
            location.sunrise(date, local=False)
            if self._sunrise_time is None
            else _replace_time(date, "sunrise")
        ) + self._sunrise_offset
        sunset = (
            location.sunset(date, local=False)
            if self._sunset_time is None
            else _replace_time(date, "sunset")
        ) + self._sunset_offset

        if self._sunrise_time is None and self._sunset_time is None:
            solar_noon = location.solar_noon(date, local=False)
            solar_midnight = location.solar_midnight(date, local=False)
        else:
            solar_noon = sunrise + (sunset - sunrise) / 2
            solar_midnight = sunset + ((sunrise + timedelta(days=1)) - sunset) / 2

        return {
            SUN_EVENT_SUNRISE: sunrise.timestamp(),
            SUN_EVENT_SUNSET: sunset.timestamp(),
            SUN_EVENT_NOON: solar_noon.timestamp(),
            SUN_EVENT_MIDNIGHT: solar_midnight.timestamp(),
        }

    def _calc_percent(self):
        now = dt_util.utcnow()
        now_ts = now.timestamp()

        today = self._get_sun_events(now)
        if now_ts < today[SUN_EVENT_SUNRISE]:
            # It's before sunrise (after midnight), because it's before
            # sunrise (and after midnight) sunset must have happend yesterday.
            yesterday = self._get_sun_events(now - timedelta(days=1))
            if (
                today[SUN_EVENT_MIDNIGHT] > today[SUN_EVENT_SUNSET]
                and yesterday[SUN_EVENT_MIDNIGHT] > yesterday[SUN_EVENT_SUNSET]
            ):
                # Solar midnight is after sunset so use yesterdays's time
                today[SUN_EVENT_MIDNIGHT] = yesterday[SUN_EVENT_MIDNIGHT]
            today[SUN_EVENT_SUNSET] = yesterday[SUN_EVENT_SUNSET]
        elif now_ts > today[SUN_EVENT_SUNSET]:
            # It's after sunset (before midnight), because it's after sunset
            # (and before midnight) sunrise should happen tomorrow.
            tomorrow = self._get_sun_events(now + timedelta(days=1))
            if (
                today[SUN_EVENT_MIDNIGHT] < today[SUN_EVENT_SUNRISE]
                and tomorrow[SUN_EVENT_MIDNIGHT] < tomorrow[SUN_EVENT_SUNRISE]
            ):
                # Solar midnight is before sunrise so use tomorrow's time
                today[SUN_EVENT_MIDNIGHT] = tomorrow[SUN_EVENT_MIDNIGHT]
            today[SUN_EVENT_SUNRISE] = tomorrow[SUN_EVENT_SUNRISE]

        # Figure out where we are in time so we know which half of the
        # parabola to calculate. We're generating a different
        # sunset-sunrise parabola for before and after solar midnight.
        # because it might not be half way between sunrise and sunset.
        # We're also generating a different parabola for sunrise-sunset.

        # sunrise -> sunset parabola
        if today[SUN_EVENT_SUNRISE] < now_ts < today[SUN_EVENT_SUNSET]:
            h = today[SUN_EVENT_NOON]
            k = 1
            # parabola before solar_noon else after solar_noon
            x = (
                today[SUN_EVENT_SUNRISE]
                if now_ts < today[SUN_EVENT_NOON]
                else today[SUN_EVENT_SUNSET]
            )

        # sunset -> sunrise parabola
        elif today[SUN_EVENT_SUNSET] < now_ts < today[SUN_EVENT_SUNRISE]:
            h = today[SUN_EVENT_MIDNIGHT]
            k = -1
            # parabola before solar_midnight else after solar_midnight
            x = (
                today[SUN_EVENT_SUNSET]
                if now_ts < today[SUN_EVENT_MIDNIGHT]
                else today[SUN_EVENT_SUNRISE]
            )

        y = 0
        a = (y - k) / (h - x) ** 2
        percentage = a * (now_ts - h) ** 2 + k
        return percentage

    def _is_sleep(self):
        return (
            self._sleep_entity is not None
            and self.hass.states.get(self._sleep_entity).state in self._sleep_state
        )

    def _calc_colortemp_kelvin(self):
        if self._is_sleep():
            return self._sleep_colortemp
        if self._percent > 0:
            delta = self._max_colortemp - self._min_colortemp
            return (delta * self._percent) + self._min_colortemp
        return self._min_colortemp

    def _calc_brightness(self) -> float:
        if self._disable_brightness_adjust:
            return
        if self._is_sleep():
            return self._sleep_brightness
        if self._percent > 0:
            return self._max_brightness
        delta_brightness = self._max_brightness - self._min_brightness
        percent = 1 + self._percent
        return (delta_brightness * percent) + self._min_brightness

    def _is_disabled(self):
        return (
            self._disable_entity is not None
            and self.hass.states.get(self._disable_entity).state in self._disable_state
        )

    def _should_adjust(self):
        if not self.is_on:
            return False
        if self._is_disabled():
            return False
        return True

    async def _adjust_lights(self, lights, transition):
        if not self._should_adjust():
            return

        if transition is None:
            transition = self._transition

        tasks = []
        for light in lights:
            if not is_on(self.hass, light):
                continue

            service_data = {ATTR_ENTITY_ID: light, ATTR_TRANSITION: transition}
            if self._brightness is not None:
                service_data[ATTR_BRIGHTNESS] = int((self._brightness / 100) * 254)

            light_type = self._lights_types[light]
            if light_type == "mired":
                service_data[ATTR_COLOR_TEMP] = self._colortemp_mired
            elif light_type == "rgb":
                service_data[ATTR_RGB_COLOR] = self._rgb_color
            elif light_type == "xy":
                service_data[ATTR_XY_COLOR] = self._xy_color
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
            await self._update_lights(
                lights=[entity_id], transition=self._initial_transition, force=True
            )

    async def _state_changed(self, entity_id, from_state, to_state):
        _LOGGER.debug(_difference_between_states(from_state, to_state))
        await self._update_lights(transition=self._initial_transition, force=True)
