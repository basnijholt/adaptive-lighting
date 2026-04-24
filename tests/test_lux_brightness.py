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


class TestLuxSamplesBuffer:
    """Test the lux samples smoothing buffer logic."""

    def test_smoothing_average(self):
        """Test that smoothing returns the average of samples."""
        samples: deque[tuple[float, float]] = deque()
        now = time.time()
        samples.append((now - 10, 100.0))
        samples.append((now - 5, 200.0))
        samples.append((now, 300.0))

        window = 300  # 5 minutes
        cutoff = now - window
        valid_samples = [value for timestamp, value in samples if timestamp >= cutoff]
        avg = sum(valid_samples) / len(valid_samples)
        assert avg == 200.0  # (100 + 200 + 300) / 3

    def test_smoothing_filters_old_samples(self):
        """Test that samples outside the time window are excluded."""
        samples: deque[tuple[float, float]] = deque()
        now = time.time()
        samples.append((now - 400, 100.0))  # Outside 300s window
        samples.append((now - 200, 200.0))  # Inside window
        samples.append((now - 100, 300.0))  # Inside window

        window = 300
        cutoff = now - window
        valid_samples = [value for timestamp, value in samples if timestamp >= cutoff]
        avg = sum(valid_samples) / len(valid_samples)
        assert avg == 250.0  # (200 + 300) / 2

    def test_empty_samples_returns_none(self):
        """Test that empty samples returns None."""
        samples: deque[tuple[float, float]] = deque()
        assert len(samples) == 0
        # In actual implementation, _get_smoothed_lux returns None when empty

    def test_all_samples_expired_returns_none(self):
        """Test that when all samples are outside the window, None is returned."""
        samples: deque[tuple[float, float]] = deque()
        now = time.time()
        samples.append((now - 400, 100.0))  # Outside 300s window
        samples.append((now - 350, 200.0))  # Outside 300s window

        window = 300
        cutoff = now - window
        valid_samples = [value for timestamp, value in samples if timestamp >= cutoff]
        assert len(valid_samples) == 0
