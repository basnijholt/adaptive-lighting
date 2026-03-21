"""Switch for the Adaptive Lighting integration."""

from __future__ import annotations

import bisect
import colorsys
import datetime
import logging
import math
from dataclasses import dataclass
from datetime import UTC, timedelta
from enum import Enum
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, Literal, cast

from homeassistant.util.color import (
    color_RGB_to_xy,
    color_temperature_to_rgb,
    color_xy_to_hs,
)

if TYPE_CHECKING:
    import astral.location


class SunEvent(str, Enum):
    """A set of sun events that happen during a day."""

    # Same as homeassistant.const.SUN_EVENT_SUNRISE and homeassistant.const.SUN_EVENT_SUNSET
    # We re-define them here to not depend on homeassistant in this file.
    SUNRISE = "sunrise"
    SUNSET = "sunset"
    NOON = "solar_noon"
    MIDNIGHT = "solar_midnight"


_ORDER = (SunEvent.SUNRISE, SunEvent.NOON, SunEvent.SUNSET, SunEvent.MIDNIGHT)
_ALLOWED_ORDERS = {_ORDER[i:] + _ORDER[:i] for i in range(len(_ORDER))}

utcnow: partial[datetime.datetime] = partial(datetime.datetime.now, UTC)
utcnow.__doc__ = "Get now in UTC time."

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SunEvents:
    """Track the state of the sun and associated light settings."""

    name: str
    astral_location: astral.location.Location
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
            sunrise = max(min_sunrise, sunrise)
        if self.max_sunrise_time is not None:
            max_sunrise = self._replace_time(dt, self.max_sunrise_time)
            sunrise = min(max_sunrise, sunrise)
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
            sunset = max(min_sunset, sunset)
        if self.max_sunset_time is not None:
            max_sunset = self._replace_time(dt, self.max_sunset_time)
            sunset = min(max_sunset, sunset)
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

    def sun_events(self, dt: datetime.datetime) -> list[tuple[SunEvent, float]]:
        """Get the four sun event's timestamps at 'dt'."""
        sunrise = self.sunrise(dt)
        sunset = self.sunset(dt)
        solar_noon, solar_midnight = self.noon_and_midnight(dt, sunset, sunrise)
        events: list[tuple[SunEvent, float]] = [
            (SunEvent.SUNRISE, sunrise.timestamp()),
            (SunEvent.SUNSET, sunset.timestamp()),
            (SunEvent.NOON, solar_noon.timestamp()),
            (SunEvent.MIDNIGHT, solar_midnight.timestamp()),
        ]
        self._validate_sun_event_order(events)
        return events

    def _validate_sun_event_order(self, events: list[tuple[SunEvent, float]]) -> None:
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

    def prev_and_next_events(
        self,
        dt: datetime.datetime,
    ) -> list[tuple[SunEvent, float]]:
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
            if next_event in (SunEvent.SUNSET, SunEvent.SUNRISE)
            else (next_ts, prev_ts)
        )
        # k = -1 between sunset and sunrise (sun below horizon)
        # k = 1 between sunrise and sunset (sun above horizon)
        k = 1 if next_event in (SunEvent.SUNSET, SunEvent.NOON) else -1
        return k * (1 - ((target_ts - h) / (h - x)) ** 2)

    def closest_event(
        self,
        dt: datetime.datetime,
    ) -> tuple[Literal[SunEvent.SUNRISE, SunEvent.SUNSET], float]:
        """Get the closest sunset or sunrise event."""
        (prev_event, prev_ts), (next_event, next_ts) = self.prev_and_next_events(dt)
        if SunEvent.SUNRISE in (prev_event, next_event):
            ts_event = prev_ts if prev_event == SunEvent.SUNRISE else next_ts
            return SunEvent.SUNRISE, ts_event
        if SunEvent.SUNSET in (prev_event, next_event):
            ts_event = prev_ts if prev_event == SunEvent.SUNSET else next_ts
            return SunEvent.SUNSET, ts_event
        msg = "No sunrise or sunset event found."
        raise ValueError(msg)


@dataclass(frozen=True)
class SunLightSettings:
    """Track the state of the sun and associated light settings."""

    name: str
    astral_location: astral.location.Location
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
    lux_sensor: str | None = None
    lux_min: int = 0
    lux_max: int = 10000
    lux_smoothing_samples: int = 5
    lux_smoothing_window: int = 300
    lux_brightness_reduction_factor: float = 0.5
    weather_entity: str | None = None
    bad_weather: list[str] | None = None
    weather_brightness_reduction_factor: float = 0.5

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
        if event == SunEvent.SUNRISE:
            brightness = scaled_tanh(
                dt.timestamp() - ts_event,
                x1=-dark,
                x2=+light,
                y1=0.05,  # be at 5% of range at x1
                y2=0.95,  # be at 95% of range at x2
                y_min=self.min_brightness,
                y_max=self.max_brightness,
            )
        elif event == SunEvent.SUNSET:
            brightness = scaled_tanh(
                dt.timestamp() - ts_event,
                x1=-light,  # shifted timestamp for the start of sunset
                x2=+dark,  # shifted timestamp for the end of sunset
                y1=0.95,  # be at 95% of range at the start of sunset
                y2=0.05,  # be at 5% of range at the end of sunset
                y_min=self.min_brightness,
                y_max=self.max_brightness,
            )
        else:
            msg = "Unsupported sun event"
            raise ValueError(msg)
        return clamp(brightness, self.min_brightness, self.max_brightness)

    def _brightness_pct_linear(self, dt: datetime.datetime) -> float:
        event, ts_event = self.sun.closest_event(dt)
        # at ts_event - dt_start, brightness == start_brightness
        # at ts_event + dt_end, brightness == end_brightness
        dark = self.brightness_mode_time_dark.total_seconds()
        light = self.brightness_mode_time_light.total_seconds()
        if event == SunEvent.SUNRISE:
            brightness = lerp(
                dt.timestamp() - ts_event,
                x1=-dark,
                x2=+light,
                y1=self.min_brightness,
                y2=self.max_brightness,
            )
        elif event == SunEvent.SUNSET:
            brightness = lerp(
                dt.timestamp() - ts_event,
                x1=-light,
                x2=+dark,
                y1=self.max_brightness,
                y2=self.min_brightness,
            )
        else:
            msg = "Unsupported sun event"
            raise ValueError(msg)
        return clamp(brightness, self.min_brightness, self.max_brightness)

    def _expected_brightness_factor(self, sun_position: float) -> float:
        """Calculate expected brightness factor for clear-sky conditions.

        This represents what brightness we expect at a given sun position
        under normal clear-sky conditions. Used as baseline for compensation.

        Args:
            sun_position: Sun position between [-1, 1]

        Returns:
            Expected brightness factor between 0 and 1

        """
        # When sun is above horizon (sun_position > 0), expect full brightness
        # When sun is below horizon, expect reduced brightness
        if sun_position > 0:
            return sun_position
        return 0.0

    def _calculate_sun_influence_weight(self, sun_position: float) -> float:
        """Calculate how much the sun is above the horizon.

        This weight determines when compensation should be applied.
        Near sunrise/sunset, we reduce compensation influence to avoid
        misinterpreting natural dusk/dawn as weather changes.

        Args:
            sun_position: Sun position between [-1, 1]

        Returns:
            Weight between 0 and 1, where:
            - 1.0 means sun is well above horizon (full compensation)
            - 0.0 means sun is at/below horizon (no compensation)

        """
        # Sun below horizon: no compensation
        if sun_position <= 0:
            return 0.0

        # Gradually increase influence as sun rises with a threshold to avoid compensation during early dawn/dusk
        threshold = 0.3
        if sun_position >= threshold:
            return 1.0
        return sun_position / threshold

    def _calculate_lux_compensation_factor(
        self,
        lux_value: float | None,
        sun_position: float,
    ) -> float:
        """Calculate brightness compensation factor based on illumination sensor.

        Compares actual lux reading against expected brightness for current sun position.
        Only applies compensation when sun is sufficiently above horizon.

        Args:
            lux_value: Current lux value from sensor (None if unavailable)
            sun_position: Sun position between [-1, 1]

        Returns:
            Compensation factor between 0 and 1, where:
            - 1.0 means no compensation (conditions as expected)
            - <1.0 means reduce brightness (darker than expected)
            - >1.0 is clamped to 1.0 (we don't increase beyond baseline)

        """
        # If no lux sensor configured or no value available; no compensation
        if not self.lux_sensor or lux_value is None:
            return 1.0

        sun_weight = self._calculate_sun_influence_weight(sun_position)
        # If sun is below horizon: no compensation
        if sun_weight == 0.0:
            return 1.0

        # Calculate expected lux for current sun position under clear sky and map to lux range [lux_min, lux_max]
        expected_factor = self._expected_brightness_factor(sun_position)
        # No expected brightness: no compensation
        if expected_factor <= 0:
            return 1.0

        expected_lux = self.lux_min + (self.lux_max - self.lux_min) * expected_factor

        lux_clamped = clamp(lux_value, self.lux_min, self.lux_max)

        # Calculate ratio of actual to expected lux
        if expected_lux > 0:
            lux_ratio = lux_clamped / expected_lux
        else:
            lux_ratio = 1.0

        # Convert ratio to compensation factor
        if lux_ratio >= 1.0:
            compensation = 1.0
        else:
            # Scale the reduction by the configured reduction factor from (1 - lux_brightness_reduction_factor) to 1.0
            compensation = (
                1.0 - (1.0 - lux_ratio) * self.lux_brightness_reduction_factor
            )

        # Apply sun influence weight to blend between no compensation and full compensation
        final_compensation = 1.0 - sun_weight * (1.0 - compensation)

        return final_compensation

    def _calculate_weather_compensation_factor(
        self,
        weather_state: str | None,
        sun_position: float,
    ) -> float:
        """Calculate brightness compensation factor based on weather conditions.

        Only applies compensation when sun is sufficiently above horizon,
        as weather doesn't affect brightness during night.

        Args:
            weather_state: Current weather state (None if unavailable)
            sun_position: Sun position between [-1, 1]

        Returns:
            Compensation factor between 0 and 1, where:
            - 1.0 means no compensation (good weather or not applicable)
            - <1.0 means reduce brightness (bad weather)

        """
        # If no weather entity configured or no state available: no compensation
        if not self.weather_entity or not weather_state or not self.bad_weather:
            return 1.0

        # Get sun influence weight - dont compensate if sun is low/below horizon
        sun_weight = self._calculate_sun_influence_weight(sun_position)
        if sun_weight == 0.0:
            return 1.0

        # Check if current weather is considered bad weather
        is_bad_weather = weather_state.lower() in [w.lower() for w in self.bad_weather]

        if not is_bad_weather:
            return 1.0

        # Apply weather reduction, scaled by sun influence
        compensation = 1.0 - self.weather_brightness_reduction_factor
        final_compensation = 1.0 - sun_weight * (1.0 - compensation)

        return final_compensation

    def _combine_compensation_factors(
        self,
        lux_compensation: float,
        weather_compensation: float,
        sun_position: float,
    ) -> float:
        """Combine lux and weather compensation factors intelligently.

        If both sources available: blend them based on sun position
        - During high sun: prefer lux sensor (more accurate)
        - During low sun: prefer weather (sensor less reliable)
        If only one source available: use that source
        If neither available: return 1.0 (no compensation)

        Args:
            lux_compensation: Compensation factor from lux sensor (1.0 if unavailable)
            weather_compensation: Compensation factor from weather (1.0 if unavailable)
            sun_position: Sun position between [-1, 1]

        Returns:
            Combined compensation factor between 0 and 1

        """
        has_lux = lux_compensation < 1.0
        has_weather = weather_compensation < 1.0

        # No compensation from either source
        if not has_lux and not has_weather:
            return 1.0

        # Only lux compensation available
        if has_lux and not has_weather:
            return lux_compensation

        # Only weather compensation available
        if has_weather and not has_lux:
            return weather_compensation

        # Both available: blend based on sun position
        sun_weight = self._calculate_sun_influence_weight(sun_position)

        # When sun is high (weight=1.0): 80% lux, 20% weather
        # When sun is low (weight=0.3): 50% lux, 50% weather
        lux_weight = 0.5 + 0.3 * sun_weight
        weather_weight = 1.0 - lux_weight

        combined = (lux_compensation * lux_weight) + (
            weather_compensation * weather_weight
        )

        return combined

    def brightness_pct(
        self,
        dt: datetime.datetime,
        is_sleep: bool,
        lux_value: float | None = None,
        weather_state: str | None = None,
    ) -> float | None:
        """Calculate the brightness in %."""
        if is_sleep:
            return self.sleep_brightness
        assert self.brightness_mode in ("default", "linear", "tanh")
        sun_position = self.sun.sun_position(dt)
        if self.brightness_mode == "default":
            brightness = self._brightness_pct_default(dt)
        elif self.brightness_mode == "linear":
            brightness = self._brightness_pct_linear(dt)
        elif self.brightness_mode == "tanh":
            brightness = self._brightness_pct_tanh(dt)
        else:
            return None

        # Calculate compensation factors based on lux and weather
        lux_compensation = self._calculate_lux_compensation_factor(
            lux_value, sun_position
        )
        weather_compensation = self._calculate_weather_compensation_factor(
            weather_state, sun_position
        )

        # Combine compensation factors intelligently
        combined_compensation = self._combine_compensation_factors(
            lux_compensation,
            weather_compensation,
            sun_position,
        )

        # Apply combined compensation to base brightness
        compensated_brightness = brightness * combined_compensation

        # Ensure brightness stays within bounds
        return clamp(compensated_brightness, self.min_brightness, self.max_brightness)

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
        lux_value: float | None = None,
        weather_state: str | None = None,
    ) -> dict[str, Any]:
        """Calculate the brightness and color."""
        sun_position = self.sun.sun_position(dt)
        rgb_color: tuple[int, int, int]
        # Variable `force_rgb_color` is needed for RGB color after sunset (if enabled)
        force_rgb_color = False
        brightness_pct = self.brightness_pct(dt, is_sleep, lux_value, weather_state)
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
            r, g, b = color_temperature_to_rgb(color_temp_kelvin)
            rgb_color = (round(r), round(g), round(b))
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
        is_sleep: bool,
        transition: float | None,
        lux_value: float | None = None,
        weather_state: str | None = None,
    ) -> dict[str, float | int | tuple[float, float] | tuple[float, float, float]]:
        """Get all light settings.

        Calculating all values takes <0.5ms.
        """
        dt = utcnow() + timedelta(seconds=transition or 0)
        return self.brightness_and_color(dt, is_sleep, lux_value, weather_state)


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
    rgb = tuple(round(x * 255) for x in colorsys.hsv_to_rgb(*hsv))
    assert all(0 <= x <= 255 for x in rgb), f"Invalid RGB color: {rgb}"
    return cast("tuple[int, int, int]", rgb)


def lerp(x: float, x1: float, x2: float, y1: float, y2: float) -> float:
    """Linearly interpolate between two values."""
    return y1 + (x - x1) * (y2 - y1) / (x2 - x1)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(value, maximum))
