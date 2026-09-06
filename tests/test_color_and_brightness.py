import datetime as dt
import zoneinfo

import astral.sun
import pytest
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    _POLAR_SUN_EVENT_OFFSET,
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


# Tromsø, Norway (69.6°N) has polar night (Nov-Jan) and midnight sun (May-Jul).
TROMSO = Location(
    LocationInfo(
        name="Tromsø",
        region="Norway",
        timezone="Europe/Oslo",
        latitude=69.6489,
        longitude=18.9551,
    ),
)
POLAR_NIGHT_DATE = dt.date(2026, 1, 7)
MIDNIGHT_SUN_DATE = dt.date(2026, 7, 7)
MCMURDO = Location(
    LocationInfo(
        name="McMurdo Station",
        region="Antarctica",
        timezone="Antarctica/McMurdo",
        latitude=-77.8419,
        longitude=166.6863,
    ),
)


def _polar_sun_events(location=TROMSO, **kwargs):
    defaults = {
        "name": "test",
        "astral_observer": location.observer,
        "sunrise_time": None,
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": None,
        "min_sunset_time": None,
        "max_sunset_time": None,
        "timezone": zoneinfo.ZoneInfo(location.timezone),
    }
    return SunEvents(**{**defaults, **kwargs})


def test_polar_night_synthesizes_short_day():
    # `astral` cannot compute sunrise/sunset (the sun never rises), see #1485
    with pytest.raises(ValueError):  # noqa: PT011
        astral.sun.sunrise(TROMSO.observer, POLAR_NIGHT_DATE)
    sun_events = _polar_sun_events()
    noon = astral.sun.noon(TROMSO.observer, POLAR_NIGHT_DATE)
    assert sun_events.sunrise(POLAR_NIGHT_DATE) == noon - _POLAR_SUN_EVENT_OFFSET
    assert sun_events.sunset(POLAR_NIGHT_DATE) == noon + _POLAR_SUN_EVENT_OFFSET


def test_midnight_sun_synthesizes_short_night():
    # `astral` cannot compute sunrise/sunset (the sun never sets), see #1485
    with pytest.raises(ValueError):  # noqa: PT011
        astral.sun.sunset(TROMSO.observer, MIDNIGHT_SUN_DATE)
    sun_events = _polar_sun_events()
    midnight = astral.sun.midnight(TROMSO.observer, MIDNIGHT_SUN_DATE)
    next_midnight = astral.sun.midnight(
        TROMSO.observer,
        MIDNIGHT_SUN_DATE + dt.timedelta(days=1),
    )
    assert sun_events.sunrise(MIDNIGHT_SUN_DATE) == midnight + _POLAR_SUN_EVENT_OFFSET
    assert (
        sun_events.sunset(MIDNIGHT_SUN_DATE) == next_midnight - _POLAR_SUN_EVENT_OFFSET
    )


@pytest.mark.parametrize(
    ("date", "midnight_sun"),
    [(dt.date(2026, 1, 7), True), (dt.date(2026, 7, 7), False)],
)
def test_polar_fallback_handles_southern_hemisphere(date, midnight_sun):
    sun_events = _polar_sun_events(MCMURDO)
    noon = astral.sun.noon(MCMURDO.observer, date)
    midnight = astral.sun.midnight(MCMURDO.observer, date)
    next_midnight = astral.sun.midnight(MCMURDO.observer, date + dt.timedelta(days=1))

    if midnight_sun:
        assert sun_events.sunrise(date) == midnight + _POLAR_SUN_EVENT_OFFSET
        assert sun_events.sunset(date) == next_midnight - _POLAR_SUN_EVENT_OFFSET
    else:
        assert sun_events.sunrise(date) == noon - _POLAR_SUN_EVENT_OFFSET
        assert sun_events.sunset(date) == noon + _POLAR_SUN_EVENT_OFFSET


def test_boundary_day_with_real_sunrise_and_synthetic_sunset():
    # At the start of the midnight sun period, `astral` computes a real
    # sunrise for this date but raises for sunset (this exact date depends on
    # astral's numerics). The synthetic sunset must stay consistent with the
    # nearly 24-hour day instead of collapsing into a polar-night day.
    date = dt.date(2026, 5, 18)
    astral.sun.sunrise(TROMSO.observer, date)  # does not raise
    with pytest.raises(ValueError):  # noqa: PT011
        astral.sun.sunset(TROMSO.observer, date)
    sun_events = _polar_sun_events()
    day_length = sun_events.sunset(date) - sun_events.sunrise(date)
    assert day_length > dt.timedelta(hours=22)


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
def test_sun_position_on_polar_days(date):
    sun_events = _polar_sun_events()
    datetime = dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc)
    noon, midnight = sun_events.noon_and_midnight(datetime)
    assert sun_events.sun_position(noon) == 1
    assert sun_events.sun_position(midnight) == -1
    assert sun_events.sun_position(sun_events.sunrise(date)) == 0
    assert sun_events.sun_position(sun_events.sunset(date)) == 0


def test_polar_night_min_max_times_shape_the_synthetic_day():
    # The (min/max)_(sunrise/sunset)_time options apply on top of the
    # synthetic sun events, so users can still shape their schedule.
    sun_events = _polar_sun_events(
        max_sunrise_time=dt.time(9, 0),
        min_sunset_time=dt.time(17, 0),
        timezone=dt.timezone.utc,
    )
    expected_sunrise = dt.datetime(2026, 1, 7, 9, 0, tzinfo=dt.timezone.utc)
    expected_sunset = dt.datetime(2026, 1, 7, 17, 0, tzinfo=dt.timezone.utc)
    assert sun_events.sunrise(POLAR_NIGHT_DATE) == expected_sunrise
    assert sun_events.sunset(POLAR_NIGHT_DATE) == expected_sunset


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
@pytest.mark.parametrize(
    ("sunrise_offset", "sunset_offset"),
    [
        (dt.timedelta(hours=-20), dt.timedelta(hours=-20)),
        (dt.timedelta(hours=-20), dt.timedelta(hours=20)),
        (dt.timedelta(hours=20), dt.timedelta(hours=-20)),
        (dt.timedelta(hours=20), dt.timedelta(hours=20)),
    ],
)
def test_polar_offsets_cannot_invert_event_order(
    date,
    sunrise_offset,
    sunset_offset,
):
    sun_events = _polar_sun_events(
        sunrise_offset=sunrise_offset,
        sunset_offset=sunset_offset,
    )

    events = dict(
        sun_events.sun_events(dt.datetime.combine(date, dt.time(), tzinfo=dt.UTC)),
    )
    midnight = dt.datetime.fromtimestamp(events[SunEvent.MIDNIGHT], tz=dt.UTC)
    next_midnight = astral.sun.midnight(TROMSO.observer, date + dt.timedelta(days=1))
    noon = dt.datetime.fromtimestamp(events[SunEvent.NOON], tz=dt.UTC)
    sunrise = dt.datetime.fromtimestamp(events[SunEvent.SUNRISE], tz=dt.UTC)
    sunset = dt.datetime.fromtimestamp(events[SunEvent.SUNSET], tz=dt.UTC)

    assert midnight < sunrise < noon < sunset < next_midnight


def test_polar_fallback_applies_offsets_within_solar_anchors():
    offset = dt.timedelta(minutes=15)
    plain = _polar_sun_events()
    shifted = _polar_sun_events(
        sunrise_offset=offset,
        sunset_offset=offset,
    )

    assert (
        shifted.sunrise(MIDNIGHT_SUN_DATE) - plain.sunrise(MIDNIGHT_SUN_DATE) == offset
    )
    assert shifted.sunset(MIDNIGHT_SUN_DATE) - plain.sunset(MIDNIGHT_SUN_DATE) == offset


def test_sun_position_all_year_in_polar_region():
    # Covers the transitions into and out of polar night and midnight sun;
    # `sun_position` internally validates the order of the sun events.
    sun_events = _polar_sun_events()
    datetime = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    while datetime < end:
        position = sun_events.sun_position(datetime)
        assert -1 <= position <= 1
        datetime += dt.timedelta(hours=8)


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
def test_brightness_and_color_on_polar_days(date):
    settings = SunLightSettings(
        name="test",
        astral_observer=TROMSO.observer,
        adapt_until_sleep=False,
        max_brightness=100,
        max_color_temp=5500,
        min_brightness=30,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=dt.timedelta(hours=1),
        brightness_mode_time_light=dt.timedelta(hours=1),
        timezone=zoneinfo.ZoneInfo("Europe/Oslo"),
    )
    datetime = dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc)
    noon, midnight = settings.sun.noon_and_midnight(datetime)
    at_noon = settings.brightness_and_color(noon, is_sleep=False)
    assert at_noon["brightness_pct"] == 100
    assert at_noon["color_temp_kelvin"] == 5500
    at_midnight = settings.brightness_and_color(midnight, is_sleep=False)
    assert at_midnight["brightness_pct"] == 30
    assert at_midnight["color_temp_kelvin"] == 2000
