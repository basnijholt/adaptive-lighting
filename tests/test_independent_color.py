import datetime
import sys
from datetime import timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

# Add the parent directory to sys.path to import the component
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from custom_components.adaptive_lighting.color_and_brightness import SunLightSettings

# Mock astral location
mock_location = MagicMock()
# Set fixed times for reliable testing
TEST_DATE = datetime.datetime(2025, 1, 1, tzinfo=timezone.utc).date()
SUNRISE = datetime.datetime.combine(TEST_DATE, datetime.time(6, 0), tzinfo=timezone.utc)
SUNSET = datetime.datetime.combine(TEST_DATE, datetime.time(18, 0), tzinfo=timezone.utc)
NOON = datetime.datetime.combine(TEST_DATE, datetime.time(12, 0), tzinfo=timezone.utc)
MIDNIGHT = datetime.datetime.combine(
    TEST_DATE + timedelta(days=1),
    datetime.time(0, 0),
    tzinfo=timezone.utc,
)

mock_location.sunrise.return_value = SUNRISE
mock_location.sunset.return_value = SUNSET
mock_location.noon.return_value = NOON
mock_location.midnight.return_value = MIDNIGHT


def test_independent_color():
    """Test independent color control logic."""
    base_settings = {
        "name": "test",
        "astral_location": mock_location,
        "adapt_until_sleep": False,
        "max_brightness": 100,
        "min_brightness": 50,
        "max_color_temp": 6000,
        "min_color_temp": 3000,
        "sleep_brightness": 1,
        "sleep_color_temp": 2000,
        "sleep_rgb_color": (255, 0, 0),
        "sleep_rgb_or_color_temp": "color_temp",
        "sunrise_time": datetime.time(6, 0),
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": datetime.time(18, 0),
        "min_sunset_time": None,
        "max_sunset_time": None,
        "sunrise_offset": timedelta(0),
        "sunset_offset": timedelta(0),
        "brightness_mode_time_dark": timedelta(seconds=900),
        "brightness_mode_time_light": timedelta(seconds=3600),
        "brightness_mode": "default",
        "timezone": timezone.utc,
        # New independent color params
        "independent_color": False,
        "color_sunrise_time": datetime.time(8, 0),  # Different from main
        "color_min_sunrise_time": None,
        "color_max_sunrise_time": None,
        "color_sunset_time": datetime.time(20, 0),  # Different from main
        "color_min_sunset_time": None,
        "color_max_sunset_time": None,
        "color_sunrise_offset": timedelta(0),
        "color_sunset_offset": timedelta(0),
    }

    # Test Case 1: Independent Control Disabled
    settings = SunLightSettings(**base_settings)

    # At 7:00 (after main sunrise 6:00, before color sunrise 8:00)
    # Brightness should be high (sun is up), Color should be high (sun is up) because it follows main schedule
    dt_7am = datetime.datetime.combine(
        TEST_DATE,
        datetime.time(7, 0),
        tzinfo=timezone.utc,
    )

    res = settings.brightness_and_color(dt_7am, is_sleep=False)

    # Assertions for Case 1
    assert (
        res["color_temp_kelvin"] > 3000
    ), "Color temp should be rising as sun is up (following 06:00 sunrise)"

    # Test Case 2: Independent Control Enabled
    base_settings["independent_color"] = True
    settings = SunLightSettings(**base_settings)

    # At 7:00 (after main sunrise 6:00, before color sunrise 8:00)
    # Brightness should be high (sun is up)
    # Color should be LOW (color sun is NOT up yet, sunrise is 8:00)

    res = settings.brightness_and_color(dt_7am, is_sleep=False)

    # Assertions for Case 2
    assert res["brightness_pct"] > 50, "Brightness should be > min (sun is up)"
    assert (
        res["color_temp_kelvin"] <= 3100
    ), f"Color temp {res['color_temp_kelvin']} is too high! It should be near min {base_settings['min_color_temp']} because color sunrise is 08:00"

    # At 9:00 (after both sunrises)
    dt_9am = datetime.datetime.combine(
        TEST_DATE,
        datetime.time(9, 0),
        tzinfo=timezone.utc,
    )
    res_9am = settings.brightness_and_color(dt_9am, is_sleep=False)

    assert res_9am["color_temp_kelvin"] > 3100, "Color temp should be high now"
