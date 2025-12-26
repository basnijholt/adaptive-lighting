import logging
import sys
from pathlib import Path
import datetime
from datetime import timedelta, timezone
from unittest.mock import MagicMock

# Add the parent directory to sys.path to import the component
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from custom_components.adaptive_lighting.color_and_brightness import SunLightSettings

_LOGGER = logging.getLogger(__name__)

# Mock astral location
mock_location = MagicMock()
mock_location.sunrise.return_value = datetime.datetime.now(timezone.utc).replace(
    hour=6, minute=0, second=0, microsecond=0
)
mock_location.sunset.return_value = datetime.datetime.now(timezone.utc).replace(
    hour=18, minute=0, second=0, microsecond=0
)
mock_location.noon.return_value = datetime.datetime.now(timezone.utc).replace(
    hour=12, minute=0, second=0, microsecond=0
)
mock_location.midnight.return_value = datetime.datetime.now(timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0
)


def test_independent_color():
    _LOGGER.info("Testing Independent Color Control Logic...")

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
        "independent_color_adapting": False,
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
    _LOGGER.info("\n[Case 1] Independent Control Disabled")
    settings = SunLightSettings(**base_settings)

    # At 7:00 (after main sunrise 6:00, before color sunrise 8:00)
    # Brightness should be high (sun is up), Color should be high (sun is up) because it follows main schedule
    dt = datetime.datetime.now(timezone.utc).replace(
        hour=7, minute=0, second=0, microsecond=0
    )

    res = settings.brightness_and_color(dt, is_sleep=False)
    _LOGGER.info("Time: 07:00 (Sunrise: 06:00, Color Sunrise: 08:00)")
    _LOGGER.info(f"Brightness: {res['brightness_pct']} (Expected > min)")
    _LOGGER.info(f"Color Temp: {res['color_temp_kelvin']} (Expected > min)")

    if res["color_temp_kelvin"] <= 3000:
        _LOGGER.info(
            "FAIL: Color temp should be rising as sun is up (following 06:00 sunrise)"
        )
    else:
        _LOGGER.info("PASS: Color temp is following main schedule")

    # Test Case 2: Independent Control Enabled
    _LOGGER.info("\n[Case 2] Independent Control Enabled")
    base_settings["independent_color_adapting"] = True
    settings = SunLightSettings(**base_settings)

    # At 7:00 (after main sunrise 6:00, before color sunrise 8:00)
    # Brightness should be high (sun is up)
    # Color should be LOW (color sun is NOT up yet, sunrise is 8:00)

    res = settings.brightness_and_color(dt, is_sleep=False)
    _LOGGER.info("Time: 07:00 (Sunrise: 06:00, Color Sunrise: 08:00)")
    _LOGGER.info(f"Brightness: {res['brightness_pct']} (Expected > min)")
    _LOGGER.info(f"Color Temp: {res['color_temp_kelvin']} (Expected approx min)")

    if res["brightness_pct"] <= 50:
        _LOGGER.info("FAIL: Brightness should be > min (sun is up)")
    else:
        _LOGGER.info("PASS: Brightness is up")

    # Note: sun_position for color might be -1 if it's before sunrise,
    # but the calculation logic might give something close to min_color_temp

    if res["color_temp_kelvin"] > 3100:  # Allowing small margin
        _LOGGER.info(
            f"FAIL: Color temp {res['color_temp_kelvin']} is too high! It should be near min {base_settings['min_color_temp']} because color sunrise is 08:00"
        )
    else:
        _LOGGER.info(
            f"PASS: Color temp {res['color_temp_kelvin']} is low, following color schedule"
        )

    # At 9:00 (after both sunrises)
    dt_9am = datetime.datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    res_9am = settings.brightness_and_color(dt_9am, is_sleep=False)
    _LOGGER.info("\nTime: 09:00")
    _LOGGER.info(f"Color Temp: {res_9am['color_temp_kelvin']}")
    if res_9am["color_temp_kelvin"] <= 3100:
        _LOGGER.info("FAIL: Color temp should be high now")
    else:
        _LOGGER.info("PASS: Color temp is rising")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    test_independent_color()
