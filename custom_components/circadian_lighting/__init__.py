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

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    VALID_TRANSITION, ATTR_TRANSITION)
from homeassistant.const import (
    CONF_LATITUDE, CONF_LONGITUDE, CONF_ELEVATION,
    SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET)
from homeassistant.util import Throttle
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import track_sunrise, track_sunset, track_time_change
from homeassistant.util.color import (
    color_temperature_to_rgb, color_RGB_to_xy,
    color_xy_to_hs)
from homeassistant.util.dt import utcnow as dt_utcnow, as_local

from datetime import datetime, timedelta

VERSION = '1.0.4'

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'circadian_lighting'
CIRCADIAN_LIGHTING_PLATFORMS = ['sensor', 'switch']
CIRCADIAN_LIGHTING_UPDATE_TOPIC = '{0}_update'.format(DOMAIN)
DATA_CIRCADIAN_LIGHTING = 'data_cl'

CONF_MIN_CT = 'min_colortemp'
DEFAULT_MIN_CT = 2500
CONF_MAX_CT = 'max_colortemp'
DEFAULT_MAX_CT = 5500
CONF_SUNRISE_OFFSET = 'sunrise_offset'
CONF_SUNSET_OFFSET = 'sunset_offset'
CONF_SUNRISE_TIME = 'sunrise_time'
CONF_SUNSET_TIME = 'sunset_time'
CONF_INTERVAL = 'interval'
DEFAULT_INTERVAL = 900

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_MIN_CT, default=DEFAULT_MIN_CT):
            vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
        vol.Optional(CONF_MAX_CT, default=DEFAULT_MAX_CT):
            vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
        vol.Optional(CONF_SUNRISE_OFFSET): cv.time_period_str,
        vol.Optional(CONF_SUNSET_OFFSET): cv.time_period_str,
        vol.Optional(CONF_SUNRISE_TIME): cv.time,
        vol.Optional(CONF_SUNSET_TIME): cv.time,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_ELEVATION): float,
        vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): cv.positive_int,
        vol.Optional(ATTR_TRANSITION, default=DEFAULT_INTERVAL): VALID_TRANSITION
    }),
}, extra=vol.ALLOW_EXTRA)

def setup(hass, config):
    """Set up the Circadian Lighting component."""
    conf = config[DOMAIN]
    min_colortemp = conf.get(CONF_MIN_CT)
    max_colortemp = conf.get(CONF_MAX_CT)
    sunrise_offset = conf.get(CONF_SUNRISE_OFFSET)
    sunset_offset = conf.get(CONF_SUNSET_OFFSET)
    sunrise_time = conf.get(CONF_SUNRISE_TIME)
    sunset_time = conf.get(CONF_SUNSET_TIME)

    latitude = conf.get(CONF_LATITUDE, hass.config.latitude)
    longitude = conf.get(CONF_LONGITUDE, hass.config.longitude)
    elevation = conf.get(CONF_ELEVATION, hass.config.elevation)

    load_platform(hass, 'sensor', DOMAIN, {}, config)

    interval = conf.get(CONF_INTERVAL)
    transition = conf.get(ATTR_TRANSITION)

    cl = CircadianLighting(hass, min_colortemp, max_colortemp,
                    sunrise_offset, sunset_offset, sunrise_time, sunset_time,
                    latitude, longitude, elevation,
                    interval, transition)

    hass.data[DATA_CIRCADIAN_LIGHTING] = cl

    return True

class CircadianLighting(object):
    """Calculate universal Circadian values."""

    def __init__(self, hass, min_colortemp, max_colortemp,
                    sunrise_offset, sunset_offset, sunrise_time, sunset_time,
                    latitude, longitude, elevation,
                    interval, transition):
        self.hass = hass
        self.data = {}
        self.data['min_colortemp'] = min_colortemp
        self.data['max_colortemp'] = max_colortemp
        self.data['sunrise_offset'] = sunrise_offset
        self.data['sunset_offset'] = sunset_offset
        self.data['sunrise_time'] = sunrise_time
        self.data['sunset_time'] = sunset_time
        self.data['latitude'] = latitude
        self.data['longitude'] = longitude
        self.data['elevation'] = elevation
        self.data['interval'] = interval
        self.data['transition'] = transition
        self.data['percent'] = self.calc_percent()
        self.data['colortemp'] = self.calc_colortemp()
        self.data['rgb_color'] = self.calc_rgb()
        self.data['xy_color'] = self.calc_xy()
        self.data['hs_color'] = self.calc_hs()

        self.update = Throttle(timedelta(seconds=interval))(self._update)

        if self.data['sunrise_time'] is not None:
            track_time_change(self.hass, self._update, hour=int(self.data['sunrise_time'].strftime("%H")), minute=int(self.data['sunrise_time'].strftime("%M")), second=int(self.data['sunrise_time'].strftime("%S")))
        else:
            track_sunrise(self.hass, self._update, self.data['sunrise_offset'])
        if self.data['sunset_time'] is not None:
            track_time_change(self.hass, self._update, hour=int(self.data['sunset_time'].strftime("%H")), minute=int(self.data['sunset_time'].strftime("%M")), second=int(self.data['sunset_time'].strftime("%S")))
        else:
            track_sunset(self.hass, self._update, self.data['sunset_offset'])

    def get_sunrise_sunset(self, date = None):
        if self.data['sunrise_time'] is not None and self.data['sunset_time'] is not None:
            if date is None:
                utcdate = dt_utcnow()
                date = as_local(utcdate)
            sunrise = date.replace(hour=int(self.data['sunrise_time'].strftime("%H")), minute=int(self.data['sunrise_time'].strftime("%M")), second=int(self.data['sunrise_time'].strftime("%S")), microsecond=int(self.data['sunrise_time'].strftime("%f")))
            sunset = date.replace(hour=int(self.data['sunset_time'].strftime("%H")), minute=int(self.data['sunset_time'].strftime("%M")), second=int(self.data['sunset_time'].strftime("%S")), microsecond=int(self.data['sunset_time'].strftime("%f")))
            solar_noon = sunrise + (sunset - sunrise)/2
            solar_midnight = sunset + ((sunrise + timedelta(days=1)) - sunset)/2
        else:
            import astral
            location = astral.Location()
            location.name = 'name'
            location.region = 'region'
            location.latitude = self.data['latitude']
            location.longitude = self.data['longitude']
            location.elevation = self.data['elevation']
            _LOGGER.debug("Astral location: " + str(location))
            if self.data['sunrise_time'] is not None:
                if date is None:
                    utcdate = dt_utcnow()
                    date = as_local(utcdate)
                sunrise = date.replace(hour=int(self.data['sunrise_time'].strftime("%H")), minute=int(self.data['sunrise_time'].strftime("%M")), second=int(self.data['sunrise_time'].strftime("%S")), microsecond=int(self.data['sunrise_time'].strftime("%f")))
            else:
                sunrise = location.sunrise(date)
            if self.data['sunset_time'] is not None:
                if date is None:
                    utcdate = dt_utcnow()
                    date = as_local(utcdate)
                sunset = date.replace(hour=int(self.data['sunset_time'].strftime("%H")), minute=int(self.data['sunset_time'].strftime("%M")), second=int(self.data['sunset_time'].strftime("%S")), microsecond=int(self.data['sunset_time'].strftime("%f")))
            else:
                sunset = location.sunset(date)
            solar_noon = location.solar_noon(date)
            solar_midnight = location.solar_midnight(date)
        if self.data['sunrise_offset'] is not None:
            sunrise = sunrise + self.data['sunrise_offset']
        if self.data['sunset_offset'] is not None:
            sunset = sunset + self.data['sunset_offset']
        return {
            SUN_EVENT_SUNRISE: sunrise,
            SUN_EVENT_SUNSET: sunset,
            'solar_noon': solar_noon,
            'solar_midnight': solar_midnight
        }

    def calc_percent(self):
        utcnow = dt_utcnow()
        now = as_local(utcnow)
        today_sun_times = self.get_sunrise_sunset(now)

        now_seconds = now.timestamp()
        today_sunrise_seconds = today_sun_times[SUN_EVENT_SUNRISE].timestamp()
        today_sunset_seconds = today_sun_times[SUN_EVENT_SUNSET].timestamp()
        today_solar_noon_seconds = today_sun_times['solar_noon'].timestamp()
        today_solar_midnight_seconds = today_sun_times['solar_midnight'].timestamp()

        _LOGGER.debug("now: " + str(now) + "\n\n today_sun_times: " + str(today_sun_times))

        if now < today_sun_times[SUN_EVENT_SUNRISE]:
            yesterday_sun_times = self.get_sunrise_sunset(now - timedelta(days=1))
            yesterday_sunrise_seconds = yesterday_sun_times[SUN_EVENT_SUNRISE].timestamp()
            yesterday_sunset_seconds = yesterday_sun_times[SUN_EVENT_SUNSET].timestamp()
            yesterday_solar_midnight_seconds = yesterday_sun_times['solar_midnight'].timestamp()

            _LOGGER.debug("yesterday_sun_times: " + str(yesterday_sun_times))

            x1 = yesterday_sunset_seconds
            y1 = 0

            if today_sun_times['solar_midnight'] > yesterday_sun_times[SUN_EVENT_SUNSET] and today_sun_times['solar_midnight'] < today_sun_times[SUN_EVENT_SUNRISE]:
                x2 = today_solar_midnight_seconds
            else:
                x2 = yesterday_solar_midnight_seconds
            y2 = -100

            x3 = today_sunrise_seconds
            y3 = 0
        elif now > today_sun_times[SUN_EVENT_SUNSET]:
            tomorrow_sun_times = self.get_sunrise_sunset(now + timedelta(days=1))
            tomorrow_sunrise_seconds = tomorrow_sun_times[SUN_EVENT_SUNRISE].timestamp()
            tomorrow_sunset_seconds = tomorrow_sun_times[SUN_EVENT_SUNSET].timestamp()
            tomorrow_solar_midnight_seconds = tomorrow_sun_times['solar_midnight'].timestamp()

            x1 = today_sunset_seconds
            y1 = 0

            if today_sun_times['solar_midnight'] > today_sun_times[SUN_EVENT_SUNSET] and today_sun_times['solar_midnight'] < tomorrow_sun_times[SUN_EVENT_SUNRISE]:
                x2 = today_solar_midnight_seconds
            else:
                x2 = tomorrow_solar_midnight_seconds
            y2 = -100

            x3 = tomorrow_sunrise_seconds
            y3 = 0
        else:
            x1 = today_sunrise_seconds
            y1 = 0
            x2 = today_solar_noon_seconds
            y2 = 100
            x3 = today_sunset_seconds
            y3 = 0

        _LOGGER.debug("x1: " + str(x1) + "\n\n y1: " + str(y1) + "\n\n x2: " + str(x2) + "\n\n y2: " + str(y2))

        # Generate color temperature parabola from points
        a1 = -x1**2+x2**2
        b1 = -x1+x2
        d1 = -y1+y2
        a2 = -x2**2+x3**2
        b2 = -x2+x3
        d2 = -y2+y3
        bm = -(b2/b1)
        a3 = bm*a1+a2
        d3 = bm*d1+d2
        a = d3/a3
        b = (d1-a1*a)/b1
        c = y1-a*x1**2-b*x1
        percentage = a*now_seconds**2+b*now_seconds+c

        _LOGGER.debug("percentage: " + str(percentage))

        return percentage

    def calc_colortemp(self):
        if self.data['percent'] > 0:
            return ((self.data['max_colortemp'] - self.data['min_colortemp']) * (self.data['percent'] / 100)) + self.data['min_colortemp']
        else:
            return self.data['min_colortemp']

    def calc_rgb(self):
        return color_temperature_to_rgb(self.data['colortemp'])

    def calc_xy(self):
        rgb = self.calc_rgb()
        iR = rgb[0]
        iG = rgb[1]
        iB = rgb[2]

        return color_RGB_to_xy(iR, iG, iB)

    def calc_hs(self):
        xy = self.calc_xy()
        vX = xy[0]
        vY = xy[1]

        return color_xy_to_hs(vX, vY)

    def _update(self, *args, **kwargs):
        """Update Circadian Values."""
        self.data['percent'] = self.calc_percent()
        self.data['colortemp'] = self.calc_colortemp()
        self.data['rgb_color'] = self.calc_rgb()
        self.data['xy_color'] = self.calc_xy()
        self.data['hs_color'] = self.calc_hs()
        dispatcher_send(self.hass, CIRCADIAN_LIGHTING_UPDATE_TOPIC)
        _LOGGER.debug("Circadian Lighting Component Updated")
