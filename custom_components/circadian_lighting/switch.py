"""
Circadian Lighting Component for Home-Assistant.

This component calculates color temperature and brightness to synchronize
your color changing lights with perceived color temperature of the sky throughout
the day. This gives your environment a more natural feel, with cooler whites during
the midday and warmer tints near twilight and dawn.

In addition, the component sets your lights to a nice warm white at 1% in "Sleep" mode,
which is far brighter than starlight but won't reset your circadian rhythm or break down
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

import astral
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
    CONF_ELEVATION,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_PLATFORM,
    SERVICE_TURN_ON,
    STATE_ON,
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
)
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_sunrise,
    async_track_sunset,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify
from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_kelvin_to_mired,
    color_temperature_to_rgb,
    color_xy_to_hs,
)

_LOGGER = logging.getLogger(__name__)

ICON = "mdi:theme-light-dark"

DOMAIN = "circadian_lighting"
SUN_EVENT_NOON = "solar_noon"
SUN_EVENT_MIDNIGHT = "solar_midnight"

CONF_LIGHTS_BRIGHT = "lights_brightness"
CONF_LIGHTS_CT = "lights_ct"
CONF_LIGHTS_RGB = "lights_rgb"
CONF_LIGHTS_XY = "lights_xy"

CONF_DISABLE_BRIGHTNESS_ADJUST = "disable_brightness_adjust"
CONF_DISABLE_ENTITY = "disable_entity"
CONF_DISABLE_STATE = "disable_state"
CONF_INITIAL_TRANSITION, DEFAULT_INITIAL_TRANSITION = "initial_transition", 1
CONF_INTERVAL, DEFAULT_INTERVAL = "interval", 300
CONF_MAX_BRIGHT, DEFAULT_MAX_BRIGHT = "max_brightness", 100
CONF_MAX_CT, DEFAULT_MAX_CT = "max_colortemp", 5500
CONF_MIN_BRIGHT, DEFAULT_MIN_BRIGHT = "min_brightness", 1
CONF_MIN_CT, DEFAULT_MIN_CT = "min_colortemp", 2500
CONF_ONLY_ONCE = "only_once"
CONF_SLEEP_BRIGHT, DEFAULT_SLEEP_BRIGHT = "sleep_brightness", 1
CONF_SLEEP_CT, DEFAULT_SLEEP_CT = "sleep_colortemp", 1000
CONF_SLEEP_ENTITY = "sleep_entity"
CONF_SLEEP_STATE = "sleep_state"
CONF_SUNRISE_OFFSET = "sunrise_offset"
CONF_SUNRISE_TIME = "sunrise_time"
CONF_SUNSET_OFFSET = "sunset_offset"
CONF_SUNSET_TIME = "sunset_time"
DEFAULT_TRANSITION = 60

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): "circadian_lighting",
        vol.Optional(CONF_NAME, default="Circadian Lighting"): cv.string,
        vol.Optional(CONF_LIGHTS_BRIGHT): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_CT): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_RGB): cv.entity_ids,
        vol.Optional(CONF_LIGHTS_XY): cv.entity_ids,
        vol.Optional(CONF_DISABLE_BRIGHTNESS_ADJUST, default=False): cv.boolean,
        vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
        vol.Optional(CONF_DISABLE_STATE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_ELEVATION): float,
        vol.Optional(
            CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION
        ): VALID_TRANSITION,
        vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): cv.time_period,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_MAX_BRIGHT, default=DEFAULT_MAX_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_MAX_CT, default=DEFAULT_MAX_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_MIN_BRIGHT, default=DEFAULT_MIN_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_MIN_CT, default=DEFAULT_MIN_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_ONLY_ONCE, default=False): cv.boolean,
        vol.Optional(CONF_SLEEP_BRIGHT, default=DEFAULT_SLEEP_BRIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_SLEEP_CT, default=DEFAULT_SLEEP_CT): vol.All(
            vol.Coerce(int), vol.Range(min=1000, max=10000)
        ),
        vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
        vol.Optional(CONF_SLEEP_STATE): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_SUNRISE_OFFSET): cv.time_period_str,
        vol.Optional(CONF_SUNRISE_TIME): cv.time,
        vol.Optional(CONF_SUNSET_OFFSET): cv.time_period_str,
        vol.Optional(CONF_SUNSET_TIME): cv.time,
        vol.Optional(ATTR_TRANSITION, default=DEFAULT_TRANSITION): VALID_TRANSITION,
    }
)


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Circadian Lighting switches."""
    switch = CircadianSwitch(
        hass,
        name=config[CONF_NAME],
        lights_brightness=config.get(CONF_LIGHTS_BRIGHT, []),
        lights_ct=config.get(CONF_LIGHTS_CT, []),
        lights_rgb=config.get(CONF_LIGHTS_RGB, []),
        lights_xy=config.get(CONF_LIGHTS_XY, []),
        disable_brightness_adjust=config[CONF_DISABLE_BRIGHTNESS_ADJUST],
        disable_entity=config.get(CONF_DISABLE_ENTITY),
        disable_state=config.get(CONF_DISABLE_STATE),
        elevation=config.get(CONF_ELEVATION, hass.config.elevation),
        initial_transition=config[CONF_INITIAL_TRANSITION],
        interval=config[CONF_INTERVAL],
        latitude=config.get(CONF_LATITUDE, hass.config.latitude),
        longitude=config.get(CONF_LONGITUDE, hass.config.longitude),
        max_brightness=config[CONF_MAX_BRIGHT],
        max_colortemp=config[CONF_MAX_CT],
        min_brightness=config[CONF_MIN_BRIGHT],
        min_colortemp=config[CONF_MIN_CT],
        only_once=config[CONF_ONLY_ONCE],
        sleep_brightness=config[CONF_SLEEP_BRIGHT],
        sleep_colortemp=config[CONF_SLEEP_CT],
        sleep_entity=config.get(CONF_SLEEP_ENTITY),
        sleep_state=config.get(CONF_SLEEP_STATE),
        sunrise_offset=config.get(CONF_SUNRISE_OFFSET),
        sunrise_time=config.get(CONF_SUNRISE_TIME),
        sunset_offset=config.get(CONF_SUNSET_OFFSET),
        sunset_time=config.get(CONF_SUNSET_TIME),
        transition=config[ATTR_TRANSITION],
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


class CircadianSwitch(SwitchEntity, RestoreEntity):
    """Representation of a Circadian Lighting switch."""

    def __init__(
        self,
        hass,
        name,
        lights_brightness,
        lights_ct,
        lights_rgb,
        lights_xy,
        disable_brightness_adjust,
        disable_entity,
        disable_state,
        elevation,
        initial_transition,
        interval,
        latitude,
        longitude,
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
        """Initialize the Circadian Lighting switch."""
        self.hass = hass
        self._name = name
        self._entity_id = f"switch.circadian_lighting_{slugify(name)}"
        self._state = None
        self._icon = ICON
        self._lights_types = dict(zip(lights_ct, repeat("ct")))
        self._lights_types.update(zip(lights_brightness, repeat("brightness")))
        self._lights_types.update(zip(lights_rgb, repeat("rgb")))
        self._lights_types.update(zip(lights_xy, repeat("xy")))
        self._lights = list(self._lights_types.keys())

        self._disable_brightness_adjust = disable_brightness_adjust
        self._disable_entity = disable_entity
        self._disable_state = disable_state
        self._elevation = elevation
        self._initial_transition = initial_transition
        self._interval = interval
        self._latitude = latitude
        self._longitude = longitude
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

        self._percent = None
        self._brightness = None
        self._colortemp_kelvin = None
        self._colortemp_mired = None
        self._rgb_color = None
        self._xy_color = None
        self._hs_color = None

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

        # XXX FROM __INIT__ \/
        if self._manual_sunrise is not None:
            async_track_time_change(
                self.hass,
                self.update,
                hour=self._manual_sunrise.hour,
                minute=self._manual_sunrise.minute,
                second=self._manual_sunrise.second,
            )
        else:
            async_track_sunrise(self.hass, self.update, self._sunrise_offset)

        if self._manual_sunset is not None:
            async_track_time_change(
                self.hass,
                self.update,
                hour=self._manual_sunset.hour,
                minute=self._manual_sunset.minute,
                second=self._manual_sunset.second,
            )
        else:
            async_track_sunset(self.hass, self.update, self._sunset_offset)

        async_track_time_interval(self.hass, self.update, self._interval)
        # XXX FROM __INIT__ ^

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

    def _replace_time(self, date, key):
        other_date = self._manual_sunrise if key == "sunrise" else self._manual_sunset
        return date.replace(
            hour=other_date.hour,
            minute=other_date.minute,
            second=other_date.second,
            microsecond=other_date.microsecond,
        )

    def get_sunrise_sunset(self, date):
        if self._manual_sunrise is not None and self._manual_sunset is not None:
            sunrise = self._replace_time(date, "sunrise")
            sunset = self._replace_time(date, "sunset")
            solar_noon = sunrise + (sunset - sunrise) / 2
            solar_midnight = sunset + ((sunrise + timedelta(days=1)) - sunset) / 2
        else:
            location = astral.Location()
            location.name = "name"
            location.region = "region"
            location.latitude = self._latitude
            location.longitude = self._longitude
            location.elevation = self._elevation

            if self._manual_sunrise is not None:
                sunrise = self._replace_time(date, "sunrise")
            else:
                sunrise = location.sunrise(date)

            if self._manual_sunset is not None:
                sunset = self._replace_time(date, "sunset")
            else:
                sunset = location.sunset(date)

            solar_noon = location.solar_noon(date)
            solar_midnight = location.solar_midnight(date)

        if self._sunrise_offset is not None:
            sunrise = sunrise + self._sunrise_offset
        if self._sunset_offset is not None:
            sunset = sunset + self._sunset_offset

        datetimes = {
            SUN_EVENT_SUNRISE: sunrise,
            SUN_EVENT_SUNSET: sunset,
            SUN_EVENT_NOON: solar_noon,
            SUN_EVENT_MIDNIGHT: solar_midnight,
        }

        return {
            k: dt.astimezone(dt_util.UTC).timestamp() for k, dt in datetimes.items()
        }

    def _calc_percent(self):
        now = dt_util.utcnow()
        now_ts = now.timestamp()

        today = self.get_sunrise_sunset(now)
        if now_ts < today[SUN_EVENT_SUNRISE]:
            # It's before sunrise (after midnight), because it's before
            # sunrise (and after midnight) sunset must have happend yesterday.
            yesterday = self.get_sunrise_sunset(now - timedelta(days=1))
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
            tomorrow = self.get_sunrise_sunset(now + timedelta(days=1))
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
            k = 100
            # parabola before solar_noon else after solar_noon
            x = (
                today[SUN_EVENT_SUNRISE]
                if now_ts < today[SUN_EVENT_NOON]
                else today[SUN_EVENT_SUNSET]
            )

        # sunset -> sunrise parabola
        elif today[SUN_EVENT_SUNSET] < now_ts < today[SUN_EVENT_SUNRISE]:
            h = today[SUN_EVENT_MIDNIGHT]
            k = -100
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

    async def update(self, _=None):  # from __init__
        """Update Circadian Values."""
        self._percent = self._calc_percent()
        self._brightness = self._calc_brightness()
        self._colortemp_kelvin = self._calc_colortemp_kelvin()
        self._colortemp_mired = color_temperature_kelvin_to_mired(
            self._colortemp_kelvin
        )
        self._rgb_color = color_temperature_to_rgb(self._colortemp_kelvin)
        self._xy_color = color_RGB_to_xy(*self._rgb_color)
        self._hs_color = color_xy_to_hs(*self._xy_color)

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
            percent = self._percent / 100
            return (delta * percent) + self._min_colortemp
        return self._min_colortemp

    def _calc_brightness(self) -> float:
        if self._disable_brightness_adjust:
            return
        if self._is_sleep():
            return self._sleep_brightness
        if self._percent > 0:
            return self._max_brightness
        delta_brightness = self._max_brightness - self._min_brightness
        percent = (100 + self._percent) / 100
        return (delta_brightness * percent) + self._min_brightness

    async def _update_switch(self, lights=None, transition=None, force=False):
        if self._only_once and not force:
            return
        await self.update()
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
            transition = self._transition

        tasks = []
        for light in lights:
            if not is_on(self.hass, light):
                continue

            service_data = {ATTR_ENTITY_ID: light, ATTR_TRANSITION: transition}
            if self._brightness is not None:
                service_data[ATTR_BRIGHTNESS] = int((self._brightness / 100) * 254)

            light_type = self._lights_types[light]
            if light_type == "ct":
                service_data[ATTR_COLOR_TEMP] = int(self._colortemp_mired)
            elif light_type == "rgb":
                r, g, b = self._rgb_color
                service_data[ATTR_RGB_COLOR] = (int(r), int(g), int(b))
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
            await self._force_update_switch(lights=[entity_id])

    async def _state_changed(self, entity_id, from_state, to_state):
        _LOGGER.debug(_difference_between_states(from_state, to_state))
        await self._force_update_switch()
