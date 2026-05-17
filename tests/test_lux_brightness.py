"""Tests for lux sensor brightness control."""

import datetime as dt
import time
import zoneinfo
from collections import deque

from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    SunLightSettings,
)
from homeassistant.components.adaptive_lighting.switch import AdaptiveSwitch

# Create a mock astral_location object
location = Location(LocationInfo())
tzinfo = zoneinfo.ZoneInfo("UTC")


def create_sun_light_settings(
    brightness_mode: str = "lux",
    min_brightness: int = 1,
    max_brightness: int = 100,
    lux_min: int = 0,
    lux_max: int = 10000,
) -> SunLightSettings:
    """Create a SunLightSettings instance for testing."""
    return SunLightSettings(
        name="test",
        astral_location=location,
        adapt_until_sleep=False,
        max_brightness=max_brightness,
        max_color_temp=5500,
        min_brightness=min_brightness,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=dt.time(6, 0),
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=dt.time(18, 0),
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=dt.timedelta(seconds=900),
        brightness_mode_time_light=dt.timedelta(seconds=3600),
        brightness_mode=brightness_mode,
        timezone=tzinfo,
        lux_min=lux_min,
        lux_max=lux_max,
    )


class TestLuxBrightnessPct:
    """Test the _brightness_pct_lux method.

    Follows circadian behavior: low lux (dark) = dim lights, high lux (bright) = bright lights.
    """

    def test_lux_at_minimum_returns_min_brightness(self):
        """When lux is at or below lux_min (dark), brightness should be at minimum."""
        settings = create_sun_light_settings(min_brightness=10, max_brightness=100)
        assert settings._brightness_pct_lux(0) == 10
        assert settings._brightness_pct_lux(-10) == 10  # below lux_min

    def test_lux_at_maximum_returns_max_brightness(self):
        """When lux is at or above lux_max (bright), brightness should be at maximum."""
        settings = create_sun_light_settings(
            min_brightness=10,
            max_brightness=100,
            lux_max=10000,
        )
        assert settings._brightness_pct_lux(10000) == 100
        assert settings._brightness_pct_lux(15000) == 100  # above lux_max

    def test_lux_midpoint_returns_midpoint_brightness(self):
        """When lux is at midpoint, brightness should be at midpoint."""
        settings = create_sun_light_settings(
            min_brightness=0,
            max_brightness=100,
            lux_min=0,
            lux_max=10000,
        )
        # At lux 5000, brightness should be 50%
        assert settings._brightness_pct_lux(5000) == 50.0

    def test_lux_linear_interpolation(self):
        """Test linear interpolation at various lux levels."""
        settings = create_sun_light_settings(
            min_brightness=20,
            max_brightness=80,
            lux_min=0,
            lux_max=1000,
        )
        # brightness range is 80 - 20 = 60
        # at lux 0: 20 (min, dark)
        # at lux 250: 20 + (0.25 * 60) = 35
        # at lux 500: 20 + (0.5 * 60) = 50
        # at lux 750: 20 + (0.75 * 60) = 65
        # at lux 1000: 80 (max, bright)
        assert settings._brightness_pct_lux(0) == 20.0
        assert settings._brightness_pct_lux(250) == 35.0
        assert settings._brightness_pct_lux(500) == 50.0
        assert settings._brightness_pct_lux(750) == 65.0
        assert settings._brightness_pct_lux(1000) == 80.0

    def test_custom_lux_range(self):
        """Test with custom lux_min and lux_max values."""
        settings = create_sun_light_settings(
            min_brightness=10,
            max_brightness=90,
            lux_min=100,
            lux_max=1100,
        )
        # Range is 1000 lux, brightness range is 80
        # at lux 100: 10 (min, dark)
        # at lux 600 (midpoint): 10 + (0.5 * 80) = 50
        # at lux 1100: 90 (max, bright)
        assert settings._brightness_pct_lux(100) == 10.0
        assert settings._brightness_pct_lux(600) == 50.0
        assert settings._brightness_pct_lux(1100) == 90.0


class TestBrightnessPctWithLux:
    """Test the brightness_pct method with lux mode."""

    def test_lux_mode_with_lux_value(self):
        """When brightness_mode is 'lux' and lux_value is provided, use lux calculation."""
        settings = create_sun_light_settings(
            brightness_mode="lux",
            min_brightness=10,
            max_brightness=100,
            lux_max=10000,
        )
        dt_now = dt.datetime(2022, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        result = settings.brightness_pct(dt_now, is_sleep=False, lux_value=5000)
        # At lux 5000, should be midpoint
        assert result == 55.0  # 10 + (0.5 * (100 - 10)) = 55

    def test_lux_mode_without_lux_value_falls_back(self):
        """When brightness_mode is 'lux' but no lux_value, fall back to sun-based."""
        settings = create_sun_light_settings(
            brightness_mode="lux",
            min_brightness=10,
            max_brightness=100,
        )
        dt_noon = dt.datetime(2022, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        result = settings.brightness_pct(dt_noon, is_sleep=False, lux_value=None)
        # Should fall back to default sun-based calculation (sun position > 0 at noon)
        assert result == 100  # max_brightness when sun is up

    def test_non_lux_mode_ignores_lux_value(self):
        """When brightness_mode is not 'lux', lux_value is ignored."""
        settings = create_sun_light_settings(
            brightness_mode="default",
            min_brightness=10,
            max_brightness=100,
        )
        dt_noon = dt.datetime(2022, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        result = settings.brightness_pct(dt_noon, is_sleep=False, lux_value=10000)
        # Should use sun-based calculation, not lux
        assert result == 100  # max_brightness when sun is up (not based on lux)

    def test_sleep_mode_overrides_lux(self):
        """When is_sleep is True, sleep_brightness is returned regardless of lux."""
        settings = create_sun_light_settings(brightness_mode="lux")
        dt_now = dt.datetime(2022, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
        result = settings.brightness_pct(dt_now, is_sleep=True, lux_value=5000)
        assert result == 1  # sleep_brightness


class TestGetSettingsWithLux:
    """Test the get_settings method with lux value."""

    def test_get_settings_passes_lux_value(self):
        """Verify get_settings passes lux_value through to brightness calculation."""
        settings = create_sun_light_settings(
            brightness_mode="lux",
            min_brightness=10,
            max_brightness=100,
            lux_max=10000,
        )
        result = settings.get_settings(is_sleep=False, transition=0, lux_value=5000)
        assert "brightness_pct" in result
        assert result["brightness_pct"] == 55.0


class _LuxBufferFixture:
    """Minimal stand-in that binds the real AdaptiveSwitch smoothing methods.

    `_add_lux_sample` / `_get_smoothed_lux` only touch `_lux_samples`,
    `_lux_smoothing_samples`, and `_lux_smoothing_window` — no hass, no
    config entry — so we can exercise the production code paths directly.
    """

    _add_lux_sample = AdaptiveSwitch._add_lux_sample
    _get_smoothed_lux = AdaptiveSwitch._get_smoothed_lux

    def __init__(self, smoothing_samples: int = 5, smoothing_window: int = 300):
        self._lux_samples: deque[tuple[float, float]] = deque()
        self._lux_smoothing_samples = smoothing_samples
        self._lux_smoothing_window = smoothing_window


class TestLuxSamplesBuffer:
    """Test the AdaptiveSwitch lux smoothing buffer."""

    def test_smoothing_average(self):
        """Smoothed value is the mean of samples inside the window."""
        sw = _LuxBufferFixture()
        sw._add_lux_sample(100.0)
        sw._add_lux_sample(200.0)
        sw._add_lux_sample(300.0)
        assert sw._get_smoothed_lux() == 200.0

    def test_smoothing_filters_old_samples(self):
        """Samples older than the window are excluded from the average."""
        sw = _LuxBufferFixture(smoothing_window=300)
        now = time.time()
        sw._lux_samples.append((now - 400, 100.0))  # outside 300s window
        sw._lux_samples.append((now - 200, 200.0))  # inside
        sw._lux_samples.append((now - 100, 300.0))  # inside
        assert sw._get_smoothed_lux() == 250.0

    def test_empty_buffer_returns_none(self):
        """An empty buffer yields None."""
        sw = _LuxBufferFixture()
        assert sw._get_smoothed_lux() is None

    def test_all_samples_expired_falls_back_to_most_recent(self):
        """When every sample is outside the window, return the most recent value.

        Intentional per _get_smoothed_lux docstring — a stale value is a more
        useful signal mid-adaptation than None (which would force a silent
        revert to the sun-based fallback).
        """
        sw = _LuxBufferFixture(smoothing_window=300)
        now = time.time()
        sw._lux_samples.append((now - 400, 100.0))
        sw._lux_samples.append((now - 350, 200.0))
        assert sw._get_smoothed_lux() == 200.0  # most recent fallback

    def test_buffer_caps_at_smoothing_samples(self):
        """The deque never exceeds _lux_smoothing_samples in length."""
        sw = _LuxBufferFixture(smoothing_samples=3)
        for value in (10.0, 20.0, 30.0, 40.0, 50.0):
            sw._add_lux_sample(value)
        assert len(sw._lux_samples) == 3
        assert sw._get_smoothed_lux() == 40.0  # mean of 30, 40, 50
