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

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import VALID_TRANSITION
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME

from .const import (
    CONF_DISABLE_BRIGHTNESS_ADJUST,
    CONF_DISABLE_ENTITY,
    CONF_DISABLE_STATE,
    CONF_INITIAL_TRANSITION,
    CONF_INTERVAL,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_ONLY_ONCE,
    CONF_SLEEP_BRIGHTNESS,
    CONF_SLEEP_COLOR_TEMP,
    CONF_SLEEP_ENTITY,
    CONF_SLEEP_STATE,
    CONF_SUNRISE_OFFSET,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_OFFSET,
    CONF_SUNSET_TIME,
    CONF_TRANSITION,
    DEFAULT_DISABLE_BRIGHTNESS_ADJUST,
    DEFAULT_INITIAL_TRANSITION,
    DEFAULT_INTERVAL,
    DEFAULT_LIGHTS,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MAX_COLOR_TEMP,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MIN_COLOR_TEMP,
    DEFAULT_NAME,
    DEFAULT_ONLY_ONCE,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_COLOR_TEMP,
    DEFAULT_SUNRISE_OFFSET,
    DEFAULT_SUNSET_OFFSET,
    DEFAULT_TRANSITION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_LIGHTS, default=DEFAULT_LIGHTS): cv.entity_ids,
                vol.Optional(
                    CONF_DISABLE_BRIGHTNESS_ADJUST,
                    default=DEFAULT_DISABLE_BRIGHTNESS_ADJUST,
                ): cv.boolean,
                vol.Optional(CONF_DISABLE_ENTITY): cv.entity_id,
                vol.Optional(CONF_DISABLE_STATE): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional(
                    CONF_INITIAL_TRANSITION, default=DEFAULT_INITIAL_TRANSITION
                ): VALID_TRANSITION,
                vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): cv.time_period,
                vol.Optional(
                    CONF_MAX_BRIGHTNESS, default=DEFAULT_MAX_BRIGHTNESS
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    CONF_MAX_COLOR_TEMP, default=DEFAULT_MAX_COLOR_TEMP
                ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
                vol.Optional(
                    CONF_MIN_BRIGHTNESS, default=DEFAULT_MIN_BRIGHTNESS
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    CONF_MIN_COLOR_TEMP, default=DEFAULT_MIN_COLOR_TEMP
                ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
                vol.Optional(CONF_ONLY_ONCE, default=DEFAULT_ONLY_ONCE): cv.boolean,
                vol.Optional(
                    CONF_SLEEP_BRIGHTNESS, default=DEFAULT_SLEEP_BRIGHTNESS
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    CONF_SLEEP_COLOR_TEMP, default=DEFAULT_SLEEP_COLOR_TEMP
                ): vol.All(vol.Coerce(int), vol.Range(min=1000, max=10000)),
                vol.Optional(CONF_SLEEP_ENTITY): cv.entity_id,
                vol.Optional(CONF_SLEEP_STATE): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional(
                    CONF_SUNRISE_OFFSET, default=DEFAULT_SUNRISE_OFFSET
                ): cv.time_period,
                vol.Optional(CONF_SUNRISE_TIME): cv.time,
                vol.Optional(
                    CONF_SUNSET_OFFSET, default=DEFAULT_SUNSET_OFFSET
                ): cv.time_period,
                vol.Optional(CONF_SUNSET_TIME): cv.time,
                vol.Optional(
                    CONF_TRANSITION, default=DEFAULT_TRANSITION
                ): VALID_TRANSITION,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Import integration from config."""

    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
    return True


async def async_setup_entry(hass, config_entry):
    """Set up the component."""

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config_entry, "switch")
    )

    return True
