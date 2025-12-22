
import pytest
from datetime import datetime, time, timedelta, timezone
from custom_components.adaptive_lighting.color_and_brightness import SchedulePoint, SunLightSettings

# Mock minimal SunLightSettings for testing schedule
@pytest.fixture
def mock_settings():
    return SunLightSettings(
        name="test",
        astral_location=None, # Not needed for manual schedule
        adapt_until_sleep=False,
        max_brightness=100,
        max_color_temp=5500,
        min_brightness=1,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=2000,
        sleep_rgb_color=(255, 0, 0),
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=timedelta(seconds=0),
        brightness_mode_time_light=timedelta(seconds=0),
        manual_schedule=[
            SchedulePoint(time(9, 0), 100, 4000),
            SchedulePoint(time(13, 0), 100, 4500),
            SchedulePoint(time(17, 0), 95, 3700),
            SchedulePoint(time(19, 0), 80, 3000),
            SchedulePoint(time(23, 0), 50, 2500), # across midnight
            SchedulePoint(time(6, 0), 60, 2700), # morning
        ]
    )

def test_schedule_exact_match(mock_settings):
    dt = datetime(2023, 1, 1, 13, 0, tzinfo=timezone.utc)
    res = mock_settings.brightness_and_color(dt, is_sleep=False)
    assert res["brightness_pct"] == 100
    assert res["color_temp_kelvin"] == 4500

def test_schedule_interpolation(mock_settings):
    # Between 9:00 (100%, 4000K) and 13:00 (100%, 4500K) -> 11:00 should be 100%, 4250K
    dt = datetime(2023, 1, 1, 11, 0, tzinfo=timezone.utc)
    res = mock_settings.brightness_and_color(dt, is_sleep=False)
    assert res["brightness_pct"] == 100
    assert res["color_temp_kelvin"] == 4250

    # Between 17:00 (95%, 3700K) and 19:00 (80%, 3000K) -> 18:00 should be 87.5%, 3350K
    dt = datetime(2023, 1, 1, 18, 0, tzinfo=timezone.utc)
    res = mock_settings.brightness_and_color(dt, is_sleep=False)
    assert abs(res["brightness_pct"] - 87.5) < 0.1
    assert abs(res["color_temp_kelvin"] - 3350) < 5 # Allow small rounding diffs

def test_schedule_midnight_wrapping(mock_settings):
    # Between 23:00 (50%, 2500K) and 06:00 (60%, 2700K)
    # Total duration = 7 hours.
    # 02:30 is 3.5 hours after 23:00, so perfectly in middle.
    # Brightness should be 55, Color 2600
    dt = datetime(2023, 1, 2, 2, 30, tzinfo=timezone.utc)
    res = mock_settings.brightness_and_color(dt, is_sleep=False)
    assert abs(res["brightness_pct"] - 55) < 0.1
    assert abs(res["color_temp_kelvin"] - 2600) < 5

def test_sleep_override(mock_settings):
    dt = datetime(2023, 1, 1, 13, 0, tzinfo=timezone.utc)
    res = mock_settings.brightness_and_color(dt, is_sleep=True)
    assert res["brightness_pct"] == 1 # Sleep brightness
    assert res["color_temp_kelvin"] == 2000 # Sleep color temp
