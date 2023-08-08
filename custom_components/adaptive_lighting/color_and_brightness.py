"""Switch for the Adaptive Lighting integration."""
from __future__ import annotations

import bisect
import colorsys
import datetime
import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, Literal, cast

from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_to_rgb,
    color_xy_to_hs,
)

if TYPE_CHECKING:
    import astral

# Same as homeassistant.const.SUN_EVENT_SUNRISE and homeassistant.const.SUN_EVENT_SUNSET
# We re-define them here to not depend on homeassistant in this file.
SUN_EVENT_SUNRISE = "sunrise"
SUN_EVENT_SUNSET = "sunset"

SUN_EVENT_NOON = "solar_noon"
SUN_EVENT_MIDNIGHT = "solar_midnight"

_ORDER = (SUN_EVENT_SUNRISE, SUN_EVENT_NOON, SUN_EVENT_SUNSET, SUN_EVENT_MIDNIGHT)
_ALLOWED_ORDERS = {_ORDER[i:] + _ORDER[:i] for i in range(len(_ORDER))}

UTC = datetime.timezone.utc
utcnow: partial[datetime.datetime] = partial(datetime.datetime.now, UTC)
utcnow.__doc__ = "Get now in UTC time."

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SunEvents:
    """Track the state of the sun and associated light settings."""

    name: str
    astral_location: astral.Location
    sunrise_time: datetime.time | None
    min_sunrise_time: datetime.time | None
    max_sunrise_time: datetime.time | None
    sunset_time: datetime.time | None
    min_sunset_time: datetime.time | None
    max_sunset_time: datetime.time | None
    sunrise_offset: datetime.timedelta = datetime.timedelta()
    sunset_offset: datetime.timedelta = datetime.timedelta()
    timezone: datetime.tzinfo = UTC

    def sunrise(self, dt: datetime.date) -> datetime.datetime:
        """Return the (adjusted) sunrise time for the given datetime."""
        sunrise = (
            self.astral_location.sunrise(dt, local=False)
            if self.sunrise_time is None
            else self._replace_time(dt, self.sunrise_time)
        ) + self.sunrise_offset
        if self.min_sunrise_time is not None:
            min_sunrise = self._replace_time(dt, self.min_sunrise_time)
            if min_sunrise > sunrise:
                sunrise = min_sunrise
        if self.max_sunrise_time is not None:
            max_sunrise = self._replace_time(dt, self.max_sunrise_time)
            if max_sunrise < sunrise:
                sunrise = max_sunrise
        return sunrise

    def sunset(self, dt: datetime.date) -> datetime.datetime:
        """Return the (adjusted) sunset time for the given datetime."""
        sunset = (
            self.astral_location.sunset(dt, local=False)
            if self.sunset_time is None
            else self._replace_time(dt, self.sunset_time)
        ) + self.sunset_offset
        if self.min_sunset_time is not None:
            min_sunset = self._replace_time(dt, self.min_sunset_time)
            if min_sunset > sunset:
                sunset = min_sunset
        if self.max_sunset_time is not None:
            max_sunset = self._replace_time(dt, self.max_sunset_time)
            if max_sunset < sunset:
                sunset = max_sunset
        return sunset

    def _replace_time(
        self,
        dt: datetime.date,
        time: datetime.time,
    ) -> datetime.datetime:
        date_time = datetime.datetime.combine(dt, time)
        dt_with_tz = date_time.replace(tzinfo=self.timezone)
        return dt_with_tz.astimezone(UTC)

    def noon_and_midnight(
        self,
        dt: datetime.datetime,
        sunset: datetime.datetime | None = None,
        sunrise: datetime.datetime | None = None,
    ) -> tuple[datetime.datetime, datetime.datetime]:
        """Return the (adjusted) noon and midnight times for the given datetime."""
        if (
            self.sunrise_time is None
            and self.sunset_time is None
            and self.min_sunrise_time is None
            and self.max_sunrise_time is None
            and self.min_sunset_time is None
            and self.max_sunset_time is None
        ):
            solar_noon = self.astral_location.noon(dt, local=False)
            solar_midnight = self.astral_location.midnight(dt, local=False)
            return solar_noon, solar_midnight

        if sunset is None:
            sunset = self.sunset(dt)
        if sunrise is None:
            sunrise = self.sunrise(dt)

        middle = abs(sunset - sunrise) / 2
        if sunset > sunrise:
            noon = sunrise + middle
            midnight = noon + timedelta(hours=12) * (1 if noon.hour < 12 else -1)
        else:
            midnight = sunset + middle
            noon = midnight + timedelta(hours=12) * (1 if midnight.hour < 12 else -1)
        return noon, midnight

    def sun_events(self, dt: datetime.datetime) -> list[tuple[str, float]]:
        """Get the four sun event's timestamps at 'dt'."""
        sunrise = self.sunrise(dt)
        sunset = self.sunset(dt)
        solar_noon, solar_midnight = self.noon_and_midnight(dt, sunset, sunrise)
        events = [
            (SUN_EVENT_SUNRISE, sunrise.timestamp()),
            (SUN_EVENT_SUNSET, sunset.timestamp()),
            (SUN_EVENT_NOON, solar_noon.timestamp()),
            (SUN_EVENT_MIDNIGHT, solar_midnight.timestamp()),
        ]
        self._validate_sun_event_order(events)
        return events

    def _validate_sun_event_order(self, events: list[tuple[str, float]]) -> None:
        """Check if the sun events are in the expected order."""
        events = sorted(events, key=lambda x: x[1])
        events_names, _ = zip(*events, strict=True)
        if events_names not in _ALLOWED_ORDERS:
            msg = (
                f"{self.name}: The sun events {events_names} are not in the expected"
                " order. The Adaptive Lighting integration will not work!"
                " This might happen if your sunrise/sunset offset is too large or"
                " your manually set sunrise/sunset time is past/before noon/midnight."
            )
            _LOGGER.error(msg)
            raise ValueError(msg)

    def prev_and_next_events(self, dt: datetime.datetime) -> list[tuple[str, float]]:
        """Get the previous and next sun event."""
        events = [
            event
            for days in [-1, 0, 1]
            for event in self.sun_events(dt + timedelta(days=days))
        ]
        events = sorted(events, key=lambda x: x[1])
        i_now = bisect.bisect([ts for _, ts in events], dt.timestamp())
        return events[i_now - 1 : i_now + 1]

    def sun_position(self, dt: datetime.datetime) -> float:
        """Calculate the position of the sun, between [-1, 1]."""
        target_ts = dt.timestamp()
        (_, prev_ts), (next_event, next_ts) = self.prev_and_next_events(dt)
        h, x = (
            (prev_ts, next_ts)
            if next_event in (SUN_EVENT_SUNSET, SUN_EVENT_SUNRISE)
            else (next_ts, prev_ts)
        )
        # k = -1 between sunset and sunrise (sun below horizon)
        # k = 1 between sunrise and sunset (sun above horizon)
        k = 1 if next_event in (SUN_EVENT_SUNSET, SUN_EVENT_NOON) else -1
        return k * (1 - ((target_ts - h) / (h - x)) ** 2)

    def closest_event(self, dt: datetime.datetime) -> tuple[str, float]:
        """Get the closest sunset or sunrise event."""
        (prev_event, prev_ts), (next_event, next_ts) = self.prev_and_next_events(dt)
        if prev_event == SUN_EVENT_SUNRISE or next_event == SUN_EVENT_SUNRISE:
            ts_event = prev_ts if prev_event == SUN_EVENT_SUNRISE else next_ts
            return SUN_EVENT_SUNRISE, ts_event
        if prev_event == SUN_EVENT_SUNSET or next_event == SUN_EVENT_SUNSET:
            ts_event = prev_ts if prev_event == SUN_EVENT_SUNSET else next_ts
            return SUN_EVENT_SUNSET, ts_event
        msg = "No sunrise or sunset event found."
        raise ValueError(msg)


@dataclass(frozen=True)
class SunLightSettings:
    """Track the state of the sun and associated light settings."""

    name: str
    astral_location: astral.Location
    adapt_until_sleep: bool
    max_brightness: int
    max_color_temp: int
    min_brightness: int
    min_color_temp: int
    sleep_brightness: int
    sleep_rgb_or_color_temp: Literal["color_temp", "rgb_color"]
    sleep_color_temp: int
    sleep_rgb_color: tuple[int, int, int]
    sunrise_time: datetime.time | None
    min_sunrise_time: datetime.time | None
    max_sunrise_time: datetime.time | None
    sunset_time: datetime.time | None
    min_sunset_time: datetime.time | None
    max_sunset_time: datetime.time | None
    brightness_mode_time_dark: datetime.timedelta
    brightness_mode_time_light: datetime.timedelta
    brightness_mode: Literal["default", "linear", "tanh"] = "default"
    sunrise_offset: datetime.timedelta = datetime.timedelta()
    sunset_offset: datetime.timedelta = datetime.timedelta()
    timezone: datetime.tzinfo = UTC

    @cached_property
    def sun(self) -> SunEvents:
        """Return the SunEvents object."""
        return SunEvents(
            name=self.name,
            astral_location=self.astral_location,
            sunrise_time=self.sunrise_time,
            sunrise_offset=self.sunrise_offset,
            min_sunrise_time=self.min_sunrise_time,
            max_sunrise_time=self.max_sunrise_time,
            sunset_time=self.sunset_time,
            sunset_offset=self.sunset_offset,
            min_sunset_time=self.min_sunset_time,
            max_sunset_time=self.max_sunset_time,
            timezone=self.timezone,
        )

    def _brightness_pct_default(self, dt: datetime.datetime) -> float:
        """Calculate the brightness percentage using the default method."""
        sun_position = self.sun.sun_position(dt)
        if sun_position > 0:
            return self.max_brightness
        delta_brightness = self.max_brightness - self.min_brightness
        return (delta_brightness * (1 + sun_position)) + self.min_brightness

    def _brightness_pct_tanh(self, dt: datetime.datetime) -> float:
        event, ts_event = self.sun.closest_event(dt)
        dark = self.brightness_mode_time_dark.total_seconds()
        light = self.brightness_mode_time_light.total_seconds()
        if event == SUN_EVENT_SUNRISE:
            brightness = scaled_tanh(
                dt.timestamp() - ts_event,
                x1=-dark,
                x2=+light,
                y1=0.05,  # be at 5% of range at x1
                y2=0.95,  # be at 95% of range at x2
                y_min=self.min_brightness,
                y_max=self.max_brightness,
            )
        elif event == SUN_EVENT_SUNSET:
            brightness = scaled_tanh(
                dt.timestamp() - ts_event,
                x1=-light,  # shifted timestamp for the start of sunset
                x2=+dark,  # shifted timestamp for the end of sunset
                y1=0.95,  # be at 95% of range at the start of sunset
                y2=0.05,  # be at 5% of range at the end of sunset
                y_min=self.min_brightness,
                y_max=self.max_brightness,
            )
        return clamp(brightness, self.min_brightness, self.max_brightness)

    def _brightness_pct_linear(self, dt: datetime.datetime) -> float:
        event, ts_event = self.sun.closest_event(dt)
        # at ts_event - dt_start, brightness == start_brightness
        # at ts_event + dt_end, brightness == end_brightness
        dark = self.brightness_mode_time_dark.total_seconds()
        light = self.brightness_mode_time_light.total_seconds()
        if event == SUN_EVENT_SUNRISE:
            brightness = lerp(
                dt.timestamp() - ts_event,
                x1=-dark,
                x2=+light,
                y1=self.min_brightness,
                y2=self.max_brightness,
            )
        elif event == SUN_EVENT_SUNSET:
            brightness = lerp(
                dt.timestamp() - ts_event,
                x1=-light,
                x2=+dark,
                y1=self.max_brightness,
                y2=self.min_brightness,
            )
        return clamp(brightness, self.min_brightness, self.max_brightness)

    def brightness_pct(self, dt: datetime.datetime, is_sleep: bool) -> float:
        """Calculate the brightness in %."""
        if is_sleep:
            return self.sleep_brightness
        assert self.brightness_mode in ("default", "linear", "tanh")
        if self.brightness_mode == "default":
            return self._brightness_pct_default(dt)
        if self.brightness_mode == "linear":
            return self._brightness_pct_linear(dt)
        if self.brightness_mode == "tanh":
            return self._brightness_pct_tanh(dt)
        return None

    def color_temp_kelvin(self, sun_position: float) -> int:
        """Calculate the color temperature in Kelvin."""
        if sun_position > 0:
            delta = self.max_color_temp - self.min_color_temp
            ct = (delta * sun_position) + self.min_color_temp
            return 5 * round(ct / 5)  # round to nearest 5
        if sun_position == 0 or not self.adapt_until_sleep:
            return self.min_color_temp
        if self.adapt_until_sleep and sun_position < 0:
            delta = abs(self.min_color_temp - self.sleep_color_temp)
            ct = (delta * abs(1 + sun_position)) + self.sleep_color_temp
            return 5 * round(ct / 5)  # round to nearest 5
        msg = "Should not happen"
        raise ValueError(msg)

    def brightness_and_color(
        self,
        dt: datetime.datetime,
        is_sleep: bool,
    ) -> dict[str, Any]:
        """Calculate the brightness and color."""
        sun_position = self.sun.sun_position(dt)
        rgb_color: tuple[float, float, float]
        # Variable `force_rgb_color` is needed for RGB color after sunset (if enabled)
        force_rgb_color = False
        brightness_pct = self.brightness_pct(dt, is_sleep)
        if is_sleep:
            color_temp_kelvin = self.sleep_color_temp
            rgb_color = self.sleep_rgb_color
        elif (
            self.sleep_rgb_or_color_temp == "rgb_color"
            and self.adapt_until_sleep
            and sun_position < 0
        ):
            # Feature requested in
            # https://github.com/basnijholt/adaptive-lighting/issues/624
            # This will result in a perceptible jump in color at sunset and sunrise
            # because the `color_temperature_to_rgb` function is not 100% accurate.
            min_color_rgb = color_temperature_to_rgb(self.min_color_temp)
            rgb_color = lerp_color_hsv(
                min_color_rgb,
                self.sleep_rgb_color,
                sun_position,
            )
            color_temp_kelvin = self.color_temp_kelvin(sun_position)
            force_rgb_color = True
        else:
            color_temp_kelvin = self.color_temp_kelvin(sun_position)
            rgb_color = color_temperature_to_rgb(color_temp_kelvin)
        # backwards compatibility for versions < 1.3.1 - see #403
        color_temp_mired: float = math.floor(1000000 / color_temp_kelvin)
        xy_color: tuple[float, float] = color_RGB_to_xy(*rgb_color)
        hs_color: tuple[float, float] = color_xy_to_hs(*xy_color)
        return {
            "brightness_pct": brightness_pct,
            "color_temp_kelvin": color_temp_kelvin,
            "color_temp_mired": color_temp_mired,
            "rgb_color": rgb_color,
            "xy_color": xy_color,
            "hs_color": hs_color,
            "sun_position": sun_position,
            "force_rgb_color": force_rgb_color,
        }

    def get_settings(
        self,
        is_sleep,
        transition,
    ) -> dict[str, float | int | tuple[float, float] | tuple[float, float, float]]:
        """Get all light settings.

        Calculating all values takes <0.5ms.
        """
        dt = utcnow() + timedelta(seconds=transition or 0)
        return self.brightness_and_color(dt, is_sleep)


def find_a_b(x1: float, x2: float, y1: float, y2: float) -> tuple[float, float]:
    """Compute the values of 'a' and 'b' for a scaled and shifted tanh function.

    Given two points (x1, y1) and (x2, y2), this function calculates the coefficients 'a' and 'b'
    for a tanh function of the form y = 0.5 * (tanh(a * (x - b)) + 1) that passes through these points.

    The derivation is as follows:

    1. Start with the equation of the tanh function:
       y = 0.5 * (tanh(a * (x - b)) + 1)

    2. Rearrange the equation to isolate tanh:
       tanh(a * (x - b)) = 2*y - 1

    3. Take the inverse tanh (or artanh) on both sides to solve for 'a' and 'b':
       a * (x - b) = artanh(2*y - 1)

    4. Plug in the points (x1, y1) and (x2, y2) to get two equations.
       Using these, we can solve for 'a' and 'b' as:
       a = (artanh(2*y2 - 1) - artanh(2*y1 - 1)) / (x2 - x1)
       b = x1 - (artanh(2*y1 - 1) / a)

    Parameters
    ----------
    x1
        x-coordinate of the first point.
    x2
        x-coordinate of the second point.
    y1
        y-coordinate of the first point (should be between 0 and 1).
    y2
        y-coordinate of the second point (should be between 0 and 1).

    Returns
    -------
    a
        Coefficient 'a' for the tanh function.
    b
        Coefficient 'b' for the tanh function.

    Notes
    -----
    The values of y1 and y2 should lie between 0 and 1, inclusive.
    """
    a = (math.atanh(2 * y2 - 1) - math.atanh(2 * y1 - 1)) / (x2 - x1)
    b = x1 - (math.atanh(2 * y1 - 1) / a)
    return a, b


def scaled_tanh(
    x: float,
    x1: float,
    x2: float,
    y1: float = 0.05,
    y2: float = 0.95,
    y_min: float = 0.0,
    y_max: float = 100.0,
) -> float:
    """Apply a scaled and shifted tanh function to a given input.

    This function represents a transformation of the tanh function that scales and shifts
    the output to lie between y_min and y_max. For values of 'x' close to 'x1' and 'x2'
    (used to calculate 'a' and 'b'), the output of this function will be close to 'y_min'
    and 'y_max', respectively.

    The equation of the function is as follows:
    y = y_min + (y_max - y_min) * 0.5 * (tanh(a * (x - b)) + 1)

    Parameters
    ----------
    x
        The input to the function.
    x1
        x-coordinate of the first point.
    x2
        x-coordinate of the second point.
    y1
        y-coordinate of the first point (should be between 0 and 1). Defaults to 0.05.
    y2
        y-coordinate of the second point (should be between 0 and 1). Defaults to 0.95.
    y_min
        The minimum value of the output range. Defaults to 0.
    y_max
        The maximum value of the output range. Defaults to 100.

    Returns
    -------
        float: The output of the function, which lies in the range [y_min, y_max].
    """
    a, b = find_a_b(x1, x2, y1, y2)
    return y_min + (y_max - y_min) * 0.5 * (math.tanh(a * (x - b)) + 1)


def lerp_color_hsv(
    rgb1: tuple[float, float, float],
    rgb2: tuple[float, float, float],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors in HSV color space."""
    t = abs(t)
    assert 0 <= t <= 1

    # Convert RGB to HSV
    hsv1 = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb1])
    hsv2 = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb2])

    # Linear interpolation in HSV space
    hsv = (
        hsv1[0] + t * (hsv2[0] - hsv1[0]),
        hsv1[1] + t * (hsv2[1] - hsv1[1]),
        hsv1[2] + t * (hsv2[2] - hsv1[2]),
    )

    # Convert back to RGB
    rgb = tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(*hsv))
    assert all(0 <= x <= 255 for x in rgb), f"Invalid RGB color: {rgb}"
    return cast(tuple[int, int, int], rgb)


def lerp(x, x1, x2, y1, y2):
    """Linearly interpolate between two values."""
    return y1 + (x - x1) * (y2 - y1) / (x2 - x1)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(value, maximum))
