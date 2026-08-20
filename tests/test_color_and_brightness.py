import datetime as dt
import zoneinfo

import astral
import astral.sun
import pytest
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    _ALLOWED_ORDERS,
    SunEvent,
    SunEvents,
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


# ---------------------------------------------------------------------------
# Polar day/night: astral.sun.sunrise/sunset raise ValueError above the polar
# circle when the sun never crosses the horizon that day. Coordinates and
# dates below are chosen to actually trigger that (confirmed against the
# pinned astral version before writing the fix): Tromso, Norway, at the
# summer and winter solstices.
# ---------------------------------------------------------------------------

_POLAR_LATITUDE = 69.6
_POLAR_LONGITUDE = 18.9
_POLAR_SUMMER_SOLSTICE = dt.date(2026, 6, 21)
_POLAR_WINTER_SOLSTICE = dt.date(2026, 12, 21)


def _polar_sun_events():
    observer = astral.Observer(
        latitude=_POLAR_LATITUDE,
        longitude=_POLAR_LONGITUDE,
        elevation=0,
    )
    return SunEvents(
        name="test",
        astral_observer=observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
    )


@pytest.mark.parametrize("polar_date", [_POLAR_SUMMER_SOLSTICE, _POLAR_WINTER_SOLSTICE])
def test_polar_day_and_night_raise_in_astral_itself(polar_date):
    """Confirm the premise: astral really does raise for these dates.

    If a future astral version stops raising here, the fallback this PR
    adds would simply never trigger -- worth knowing rather than silently
    testing a fallback path that can no longer be reached.
    """
    observer = astral.Observer(
        latitude=_POLAR_LATITUDE,
        longitude=_POLAR_LONGITUDE,
        elevation=0,
    )
    with pytest.raises(ValueError, match="Sun is always (above|below) the horizon"):
        astral.sun.sunrise(observer, polar_date)


@pytest.mark.parametrize("polar_date", [_POLAR_SUMMER_SOLSTICE, _POLAR_WINTER_SOLSTICE])
def test_sunrise_and_sunset_do_not_raise_on_a_polar_date(polar_date):
    """The bug: `SunEvents.sunrise`/`sunset` used to propagate astral's
    ValueError uncaught, breaking the integration for the whole polar
    day/night period every year for anyone above/below the polar circle.
    """
    sun_events = _polar_sun_events()
    sun_events.sunrise(polar_date)
    sun_events.sunset(polar_date)


@pytest.mark.parametrize("polar_date", [_POLAR_SUMMER_SOLSTICE, _POLAR_WINTER_SOLSTICE])
def test_sun_events_stays_in_a_valid_order_on_a_polar_date(polar_date):
    """The four SunEvent timestamps must still form one of the cyclic
    (SUNRISE, NOON, SUNSET, MIDNIGHT) rotations `_validate_sun_event_order`
    requires -- `sun_events()` raises internally if they don't, so simply
    not raising here already proves this, but the explicit order is
    asserted too since it's the more informative failure if it regresses.
    """
    sun_events = _polar_sun_events()
    dt_at_noon = dt.datetime.combine(polar_date, dt.time(12), tzinfo=dt.UTC)
    events = sun_events.sun_events(dt_at_noon)
    names = tuple(name for name, _ in sorted(events, key=lambda e: e[1]))
    assert names in _ALLOWED_ORDERS


def test_polar_day_sun_position_stays_close_to_full_daylight():
    """Midsummer at 69.6N: the sun position should read as strongly
    daylight all day, including at local midnight (the sun is still above
    the horizon then, just low -- unlike a normal day, where midnight is
    the deepest point of night).
    """
    sun_events = _polar_sun_events()
    noon = dt.datetime.combine(_POLAR_SUMMER_SOLSTICE, dt.time(12), tzinfo=dt.UTC)
    midnight = dt.datetime.combine(_POLAR_SUMMER_SOLSTICE, dt.time(0), tzinfo=dt.UTC)
    assert sun_events.sun_position(noon) > 0.9
    assert sun_events.sun_position(midnight) > 0


def test_polar_night_sun_position_stays_close_to_full_darkness():
    """The mirror case: midwinter at 69.6N never sees the sun, including
    at local noon (still below the horizon, just less deep than at
    midnight -- unlike a normal day, where noon is the deepest daylight).
    """
    sun_events = _polar_sun_events()
    noon = dt.datetime.combine(_POLAR_WINTER_SOLSTICE, dt.time(12), tzinfo=dt.UTC)
    midnight = dt.datetime.combine(_POLAR_WINTER_SOLSTICE, dt.time(0), tzinfo=dt.UTC)
    assert sun_events.sun_position(noon) < 0
    assert sun_events.sun_position(midnight) < -0.9


def test_polar_fallback_clamps_a_large_offset_instead_of_crossing_the_anchor():
    """Caught by an external reviewer (Greptile) after opening the PR, not
    by the original design: the fallback placed a synthetic value only a
    minute from its anchor, so *any* offset past a minute pushed it across
    that anchor and reintroduced the exact ordering crash this PR fixes --
    confirmed with a 5-minute offset before redesigning the clamp.

    A large offset (bigger than the whole margin the clamp allows) has to
    be absorbed at the boundary rather than crossing it.
    """
    observer = astral.Observer(
        latitude=_POLAR_LATITUDE,
        longitude=_POLAR_LONGITUDE,
        elevation=0,
    )
    huge_offset = dt.timedelta(hours=20)
    sun_events = SunEvents(
        name="test",
        astral_observer=observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        sunrise_offset=huge_offset,
        sunset_offset=huge_offset,
    )
    dt_at_noon = dt.datetime.combine(
        _POLAR_SUMMER_SOLSTICE,
        dt.time(12),
        tzinfo=dt.UTC,
    )
    events = sun_events.sun_events(dt_at_noon)  # must not raise
    names = tuple(name for name, _ in sorted(events, key=lambda e: e[1]))
    assert names in _ALLOWED_ORDERS


def test_polar_fallback_still_respects_sunrise_and_sunset_offsets():
    """Offsets are applied after the astral call in the normal path;
    they must still apply after the polar fallback substitutes a value,
    or a user with an offset configured would see it silently ignored
    only during the weeks it's needed most.
    """
    observer = astral.Observer(
        latitude=_POLAR_LATITUDE,
        longitude=_POLAR_LONGITUDE,
        elevation=0,
    )
    plain = SunEvents(
        name="test",
        astral_observer=observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
    )
    offset = dt.timedelta(minutes=30)
    offset_events = SunEvents(
        name="test",
        astral_observer=observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        sunrise_offset=offset,
        sunset_offset=offset,
    )
    assert (
        offset_events.sunrise(_POLAR_SUMMER_SOLSTICE)
        - plain.sunrise(_POLAR_SUMMER_SOLSTICE)
        == offset
    )
    assert (
        offset_events.sunset(_POLAR_SUMMER_SOLSTICE)
        - plain.sunset(_POLAR_SUMMER_SOLSTICE)
        == offset
    )
