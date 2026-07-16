import datetime as dt
import zoneinfo

import pytest
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    SunEvent,
    SunEvents,
    SunLightSettings,
)

# Create a mock astral location object (its `.observer` is passed to `SunEvents`)
location = Location(LocationInfo())

LAT_LONG_TZS = [
    (52.379189, 4.899431, "Europe/Amsterdam"),
    (32.87336, -117.22743, "US/Pacific"),
    (60, 50, "GMT"),
    (60, 50, "UTC"),
]


@pytest.fixture(params=LAT_LONG_TZS)
def tzinfo_and_location(request):
    lat, long, timezone = request.param
    tzinfo = zoneinfo.ZoneInfo(timezone)
    location = Location(
        LocationInfo(
            name="name",
            region="region",
            timezone=timezone,
            latitude=lat,
            longitude=long,
        ),
    )
    return tzinfo, location


def test_replace_time(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )

    new_time = dt.time(5, 30)
    datetime = dt.datetime(2022, 1, 1)
    replaced_time_utc = sun_events._replace_time(datetime.date(), new_time)
    assert replaced_time_utc.astimezone(tzinfo).time() == new_time


def test_sunrise_without_offset(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location

    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1).date()
    result = sun_events.sunrise(date)
    assert result == location.sunrise(date)


def test_sun_position_no_fixed_sunset_and_sunrise(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1).date()
    sunset = location.sunset(date)
    position = sun_events.sun_position(sunset)
    assert position == 0
    sunrise = location.sunrise(date)
    position = sun_events.sun_position(sunrise)
    assert position == 0
    noon = location.noon(date)
    position = sun_events.sun_position(noon)
    assert position == 1
    midnight = location.midnight(date)
    position = sun_events.sun_position(midnight)
    assert position == -1


def test_sun_position_fixed_sunset_and_sunrise(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=dt.time(6, 0),
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=dt.time(18, 0),
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1).date()
    sunset = sun_events.sunset(date)
    position = sun_events.sun_position(sunset)
    assert position == 0
    sunrise = sun_events.sunrise(date)
    position = sun_events.sun_position(sunrise)
    assert position == 0
    noon, midnight = sun_events.noon_and_midnight(date)
    position = sun_events.sun_position(noon)
    assert position == 1
    position = sun_events.sun_position(midnight)
    assert position == -1


def test_noon_and_midnight(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    date = dt.datetime(2022, 1, 1)
    noon, midnight = sun_events.noon_and_midnight(date)
    assert noon == location.noon(date)
    assert midnight == location.midnight(date)


def test_sun_events(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )

    date = dt.datetime(2022, 1, 1)
    events = sun_events.sun_events(date)
    assert len(events) == 4
    assert (SunEvent.SUNRISE, location.sunrise(date).timestamp()) in events


def test_prev_and_next_events(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    datetime = dt.datetime(2022, 1, 1, 10, 0)
    after_sunrise = sun_events.sunrise(datetime.date()) + dt.timedelta(hours=1)
    prev_event, next_event = sun_events.prev_and_next_events(after_sunrise)
    assert prev_event[0] == SunEvent.SUNRISE
    assert next_event[0] == SunEvent.NOON


def test_closest_event(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        timezone=tzinfo,
    )
    datetime = dt.datetime(2022, 1, 1, 6, 0)
    sunrise = sun_events.sunrise(datetime.date())
    event_name, ts = sun_events.closest_event(sunrise)
    assert event_name == SunEvent.SUNRISE
    assert ts == location.sunrise(sunrise.date()).timestamp()


def _custom_curve_settings(tzinfo, location, **overrides):
    """Build a `SunLightSettings` with a fixed 17:30 sunset/06:00 sunrise.

    Defaults to `color_temp_mode="custom"` with `sunset_color_temp=3000` and
    `min_color_temp=2000`, so tests only need to override what they're
    exercising (the completion delay/time).
    """
    defaults = {
        "name": "test",
        "astral_observer": location.observer,
        "adapt_until_sleep": False,
        "max_brightness": 100,
        "max_color_temp": 5500,
        "min_brightness": 1,
        "min_color_temp": 2000,
        "sleep_brightness": 1,
        "sleep_rgb_or_color_temp": "color_temp",
        "sleep_color_temp": 1000,
        "sleep_rgb_color": (255, 56, 0),
        "sunrise_time": dt.time(6, 0),
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": dt.time(17, 30),
        "min_sunset_time": None,
        "max_sunset_time": None,
        "brightness_mode_time_dark": dt.timedelta(seconds=900),
        "brightness_mode_time_light": dt.timedelta(seconds=3600),
        "color_temp_mode": "custom",
        "sunset_color_temp": 3000,
        "timezone": tzinfo,
    }
    defaults.update(overrides)
    return SunLightSettings(**defaults)


def test_custom_curve_reaches_sunset_color_temp_at_sunset(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    settings = _custom_curve_settings(
        tzinfo,
        location,
        sunset_color_temp_time=dt.time(21, 0),
    )
    date = dt.datetime(2026, 1, 15).date()
    sunset = settings.sun.sunset(date)
    sun_position = settings.sun.sun_position(sunset)
    ct = settings.color_temp_kelvin(sunset, sun_position)
    assert abs(ct - 3000) <= 5


def test_custom_curve_reaches_min_color_temp_at_completion_time(
    tzinfo_and_location,
):
    tzinfo, location = tzinfo_and_location
    settings = _custom_curve_settings(
        tzinfo,
        location,
        sunset_color_temp_time=dt.time(21, 0),
    )
    date = dt.datetime(2026, 1, 15).date()
    completion = dt.datetime.combine(date, dt.time(21, 0), tzinfo=tzinfo)
    sun_position = settings.sun.sun_position(completion)
    ct = settings.color_temp_kelvin(completion, sun_position)
    assert ct == 2000


def test_custom_curve_holds_min_color_temp_after_completion(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    settings = _custom_curve_settings(
        tzinfo,
        location,
        sunset_color_temp_time=dt.time(21, 0),
    )
    date = dt.datetime(2026, 1, 15).date()
    later = dt.datetime.combine(date, dt.time(23, 30), tzinfo=tzinfo)
    sun_position = settings.sun.sun_position(later)
    ct = settings.color_temp_kelvin(later, sun_position)
    assert ct == 2000


def test_custom_curve_midpoint_is_interpolated(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    settings = _custom_curve_settings(
        tzinfo,
        location,
        sunset_color_temp_time=dt.time(21, 0),
    )
    date = dt.datetime(2026, 1, 15).date()
    # Halfway between 17:30 sunset and 21:00 completion is 19:15.
    midpoint = dt.datetime.combine(date, dt.time(19, 15), tzinfo=tzinfo)
    sun_position = settings.sun.sun_position(midpoint)
    ct = settings.color_temp_kelvin(midpoint, sun_position)
    assert abs(ct - 2500) <= 5


def test_custom_curve_delay_takes_priority_over_time(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    settings = _custom_curve_settings(
        tzinfo,
        location,
        sunset_color_temp_delay=dt.timedelta(minutes=90),
        # Should be ignored since delay is set and > 0.
        sunset_color_temp_time=dt.time(23, 0),
    )
    date = dt.datetime(2026, 1, 15).date()
    completion = dt.datetime.combine(date, dt.time(19, 0), tzinfo=tzinfo)
    sun_position = settings.sun.sun_position(completion)
    ct = settings.color_temp_kelvin(completion, sun_position)
    assert ct == 2000


def test_custom_curve_morning_is_unaffected(tzinfo_and_location):
    """The custom sunset curve should not change the sunrise->noon ramp."""
    tzinfo, location = tzinfo_and_location
    custom = _custom_curve_settings(
        tzinfo,
        location,
        sunset_color_temp_time=dt.time(21, 0),
    )
    default = _custom_curve_settings(
        tzinfo,
        location,
        color_temp_mode="default",
    )
    date = dt.datetime(2026, 1, 15).date()
    mid_morning = dt.datetime.combine(date, dt.time(8, 0), tzinfo=tzinfo)
    sun_position = custom.sun.sun_position(mid_morning)
    assert custom.color_temp_kelvin(
        mid_morning,
        sun_position,
    ) == default.color_temp_kelvin(mid_morning, sun_position)


def test_default_color_temp_mode_is_unchanged(tzinfo_and_location):
    """Regression: `color_temp_mode="default"` must match the old behavior."""
    tzinfo, location = tzinfo_and_location
    settings = _custom_curve_settings(tzinfo, location, color_temp_mode="default")
    date = dt.datetime(2026, 1, 15).date()
    sunset = settings.sun.sunset(date)
    sun_position = settings.sun.sun_position(sunset)
    ct = settings.color_temp_kelvin(sunset, sun_position)
    # In default mode, `min_color_temp` (not `sunset_color_temp`) is reached
    # exactly at sunset.
    assert ct == 2000
