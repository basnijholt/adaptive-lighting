import dataclasses
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
    clamp,
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


@pytest.mark.parametrize("day", [dt.date(2026, 4, 17), dt.date(2026, 8, 30)])
def test_midnight_falls_in_the_night_it_belongs_to(day):
    """Derived midnight must lie between sunset and the next sunrise (#1599)."""
    location = Location(
        LocationInfo(
            name="name",
            region="region",
            timezone="UTC",
            latitude=51.5,
            longitude=0.0,  # on the prime meridian
        ),
    )
    sun_events = SunEvents(
        name="test",
        astral_observer=location.observer,
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=dt.time(8, 0),
        sunset_time=None,
        min_sunset_time=dt.time(17, 0),
        max_sunset_time=dt.time(20, 0),
        timezone=zoneinfo.ZoneInfo("UTC"),
    )
    date = dt.datetime.combine(day, dt.time(12), tzinfo=dt.UTC)
    sunset = sun_events.sunset(date)
    next_sunrise = sun_events.sunrise(date + dt.timedelta(days=1))
    _, midnight = sun_events.noon_and_midnight(date)
    assert sunset < midnight < next_sunrise

    just_after_sunset = sunset + dt.timedelta(minutes=40)
    events = sun_events.prev_and_next_events(just_after_sunset)
    assert [event for event, _ in events] == [SunEvent.SUNSET, SunEvent.MIDNIGHT]
    assert sun_events.sun_position(just_after_sunset) > -0.5


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


def _make_brightness_settings(
    tzinfo,
    location,
    *,
    min_brightness,
    max_brightness,
    brightness_mode,
):
    """Build a SunLightSettings with only the fields brightness_pct() needs."""
    return SunLightSettings(
        name="test",
        astral_observer=location.observer,
        adapt_until_sleep=False,
        max_brightness=max_brightness,
        max_color_temp=6500,
        min_brightness=min_brightness,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=2000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=dt.timedelta(minutes=30),
        brightness_mode_time_light=dt.timedelta(minutes=30),
        brightness_mode=brightness_mode,
        timezone=tzinfo,
    )


def test_clamp_handles_inverted_bounds():
    """A user can intentionally set min_brightness > max_brightness for an
    inverted timescale (#1421, e.g. a porch light that should be brighter at
    night than during the day). clamp() must still bound the value between
    whichever of the two is actually smaller/larger, not silently collapse
    to `minimum` for every input the way `max(minimum, min(value, maximum))`
    does when minimum > maximum.
    """
    assert clamp(50, 100, 15) == 50
    assert clamp(0, 100, 15) == 15
    assert clamp(200, 100, 15) == 100


def test_clamp_normal_bounds_unaffected():
    """The ordinary min <= max case must keep behaving exactly as before."""
    assert clamp(50, 0, 100) == 50
    assert clamp(-10, 0, 100) == 0
    assert clamp(150, 0, 100) == 100


@pytest.mark.parametrize("brightness_mode", ["linear", "tanh"])
def test_brightness_pct_varies_with_inverted_brightness_bounds(
    tzinfo_and_location,
    brightness_mode,
):
    """#1421: with min_brightness > max_brightness, linear/tanh modes got
    stuck returning min_brightness for every sample, because the final
    `clamp(brightness, self.min_brightness, self.max_brightness)` call
    collapsed to `minimum` regardless of the computed value. Sampling a few
    points around sunrise must show the brightness actually move instead of
    being pinned to one value.
    """
    tzinfo, location = tzinfo_and_location
    settings = _make_brightness_settings(
        tzinfo,
        location,
        min_brightness=100,
        max_brightness=15,
        brightness_mode=brightness_mode,
    )

    sunrise = location.sunrise(dt.datetime(2022, 6, 1).date())
    samples = [
        settings.brightness_pct(
            sunrise + dt.timedelta(minutes=offset),
            is_sleep=False,
        )
        for offset in (-20, -10, 0, 10, 20)
    ]

    assert len({round(value) for value in samples}) > 1, samples
    assert all(15 <= value <= 100 for value in samples), samples


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


def _make_color_settings(
    tzinfo,
    location,
    *,
    color_temp_mode,
    time_dark=dt.timedelta(0),
    time_light=dt.timedelta(hours=2),
    adapt_until_sleep=False,
):
    """Build a SunLightSettings for color_temp_mode tests (2700-6500 K)."""
    return SunLightSettings(
        name="test",
        astral_observer=location.observer,
        adapt_until_sleep=adapt_until_sleep,
        max_brightness=100,
        max_color_temp=6500,
        min_brightness=1,
        min_color_temp=2700,
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
        brightness_mode_time_dark=dt.timedelta(minutes=30),
        brightness_mode_time_light=dt.timedelta(minutes=30),
        color_temp_mode=color_temp_mode,
        color_temp_mode_time_dark=time_dark,
        color_temp_mode_time_light=time_light,
        timezone=tzinfo,
    )


def _ct(settings, when):
    return settings.brightness_and_color(when, is_sleep=False)["color_temp_kelvin"]


def test_color_temp_mode_linear_holds_max_between_ramps(tzinfo_and_location):
    """Linear mode: min at sunrise, max from sunrise+time_light until
    sunset-time_light, back to min at sunset (time_dark=0).
    """
    tzinfo, location = tzinfo_and_location
    settings = _make_color_settings(tzinfo, location, color_temp_mode="linear")
    date = dt.datetime(2022, 3, 21, tzinfo=tzinfo)
    sunrise = settings.sun.sunrise(date)
    sunset = settings.sun.sunset(date)
    hour = dt.timedelta(hours=1)

    assert _ct(settings, sunrise) == 2700
    assert _ct(settings, sunrise + hour) == 4600  # halfway up the 2 h ramp
    assert _ct(settings, sunrise + 2 * hour) == 6500
    assert _ct(settings, sunrise + 3 * hour) == 6500
    assert _ct(settings, sunset - 3 * hour) == 6500
    assert _ct(settings, sunset - 2 * hour) == 6500
    assert _ct(settings, sunset - hour) == 4600
    assert _ct(settings, sunset) == 2700
    assert _ct(settings, sunset + hour) == 2700
    assert _ct(settings, sunrise - hour) == 2700


def test_color_temp_mode_time_dark_extends_ramp_into_night(tzinfo_and_location):
    """time_dark moves the warm end of the ramp before sunrise / after sunset."""
    tzinfo, location = tzinfo_and_location
    settings = _make_color_settings(
        tzinfo,
        location,
        color_temp_mode="linear",
        time_dark=dt.timedelta(hours=1),
        time_light=dt.timedelta(hours=1),
    )
    date = dt.datetime(2022, 3, 21, tzinfo=tzinfo)
    sunrise = settings.sun.sunrise(date)
    sunset = settings.sun.sunset(date)
    hour = dt.timedelta(hours=1)
    assert _ct(settings, sunrise - hour) == 2700
    assert _ct(settings, sunrise) == 4600
    assert _ct(settings, sunrise + hour) == 6500
    assert _ct(settings, sunset - hour) == 6500
    assert _ct(settings, sunset) == 4600
    assert _ct(settings, sunset + hour) == 2700


def test_color_temp_mode_tanh_is_monotonic_and_holds(tzinfo_and_location):
    tzinfo, location = tzinfo_and_location
    settings = _make_color_settings(tzinfo, location, color_temp_mode="tanh")
    date = dt.datetime(2022, 3, 21, tzinfo=tzinfo)
    sunrise = settings.sun.sunrise(date)
    sunset = settings.sun.sunset(date)
    up = [_ct(settings, sunrise + dt.timedelta(minutes=m)) for m in range(0, 121, 10)]
    assert up == sorted(up)
    assert up[0] < 3000  # ~5 % of the range at sunrise
    assert up[-1] > 6200  # ~95 % of the range at sunrise + time_light
    assert _ct(settings, sunrise + dt.timedelta(hours=4)) == 6500
    down = [
        _ct(settings, sunset - dt.timedelta(minutes=m)) for m in range(120, -1, -10)
    ]
    assert down == sorted(down, reverse=True)


def test_color_temp_mode_default_is_unchanged(tzinfo_and_location):
    """Default mode ignores dt: same values as the sun-position curve."""
    tzinfo, location = tzinfo_and_location
    settings = _make_color_settings(tzinfo, location, color_temp_mode="default")
    date = dt.datetime(2022, 3, 21, tzinfo=tzinfo)
    sunrise = settings.sun.sunrise(date)
    for minutes in range(-120, 15 * 60, 37):
        when = sunrise + dt.timedelta(minutes=minutes)
        pos = settings.sun.sun_position(when)
        assert _ct(settings, when) == settings.color_temp_kelvin(pos)


def test_color_temp_mode_adapt_until_sleep_at_night(tzinfo_and_location):
    """After the ramp has reached min_color_temp, adapt_until_sleep still
    walks toward sleep_color_temp at night, as in default mode.
    """
    tzinfo, location = tzinfo_and_location
    linear = _make_color_settings(
        tzinfo,
        location,
        color_temp_mode="linear",
        adapt_until_sleep=True,
    )
    default = _make_color_settings(
        tzinfo,
        location,
        color_temp_mode="default",
        adapt_until_sleep=True,
    )
    date = dt.datetime(2022, 3, 21, tzinfo=tzinfo)
    sunset = linear.sun.sunset(date)
    for hours in (1, 3, 5):
        when = sunset + dt.timedelta(hours=hours)
        assert _ct(linear, when) == _ct(default, when)
        assert _ct(linear, when) < 2700


def _fixed_day_settings(color_temp_mode, dark, light, *, rgb=False):
    """Fixed sunrise 06:00 / sunset 18:00, adapt_until_sleep on, sleep 1000 K."""
    location = Location(LocationInfo("n", "r", "UTC", 52.0, 4.9))
    return SunLightSettings(
        name="test",
        astral_observer=location.observer,
        adapt_until_sleep=True,
        max_brightness=100,
        max_color_temp=6500,
        min_brightness=1,
        min_color_temp=2700,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="rgb_color" if rgb else "color_temp",
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=dt.time(6),
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=dt.time(18),
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=dt.timedelta(minutes=30),
        brightness_mode_time_light=dt.timedelta(minutes=30),
        color_temp_mode=color_temp_mode,
        color_temp_mode_time_dark=dt.timedelta(seconds=dark),
        color_temp_mode_time_light=dt.timedelta(seconds=light),
        timezone=dt.UTC,
    )


_DAY = dt.datetime(2022, 3, 21, tzinfo=dt.UTC)


@pytest.mark.parametrize("color_temp_mode", ["linear", "tanh"])
def test_color_temp_mode_reaches_sleep_color_temp_at_midnight(color_temp_mode):
    """The night handoff is by time, so a tanh ramp (which never reaches
    min_color_temp exactly) still walks to sleep_color_temp.
    """
    settings = _fixed_day_settings(color_temp_mode, 900, 3600)
    assert _ct(settings, _DAY + dt.timedelta(hours=24)) == 1000


@pytest.mark.parametrize(
    ("color_temp_mode", "dark", "rgb"),
    [
        ("linear", 3600, False),
        ("tanh", 900, False),
        ("linear", 3600, True),
        ("tanh", 900, True),
        ("linear", 0, False),
    ],
)
def test_color_temp_mode_evening_and_morning_have_no_jumps(color_temp_mode, dark, rgb):
    """Sampled every minute from 16:00 to 08:00: no step in color temperature or
    RGB, including where the dark ramp hands over to the night curve.
    """
    settings = _fixed_day_settings(color_temp_mode, dark, 3600, rgb=rgb)
    prev = None
    for minute in range(16 * 60, 32 * 60):
        cur = settings.brightness_and_color(
            _DAY + dt.timedelta(minutes=minute),
            is_sleep=False,
        )
        if prev is not None:
            assert abs(cur["color_temp_kelvin"] - prev["color_temp_kelvin"]) <= 100
            assert (
                max(
                    abs(a - b)
                    for a, b in zip(cur["rgb_color"], prev["rgb_color"], strict=True)
                )
                <= 10
            )
        prev = cur


def test_color_temp_mode_rgb_follows_ramp_after_sunset():
    """During the dark ramp the RGB sleep blend must not kick in yet."""
    settings = _fixed_day_settings("linear", 3600, 3600, rgb=True)
    during = settings.brightness_and_color(
        _DAY + dt.timedelta(hours=18, minutes=30), is_sleep=False
    )
    assert not during["force_rgb_color"]
    after = settings.brightness_and_color(_DAY + dt.timedelta(hours=20), is_sleep=False)
    assert after["force_rgb_color"]


@pytest.mark.parametrize("mode", ["linear", "tanh"])
def test_zero_ramp_durations_switch_at_the_event(mode):
    """Both durations zero used to divide by zero; now it is a step at the event."""
    settings = _fixed_day_settings(mode, 0, 0)
    settings = dataclasses.replace(
        settings,
        adapt_until_sleep=False,
        brightness_mode=mode,
        brightness_mode_time_dark=dt.timedelta(0),
        brightness_mode_time_light=dt.timedelta(0),
    )
    noon = settings.brightness_and_color(_DAY + dt.timedelta(hours=12), is_sleep=False)
    night = settings.brightness_and_color(_DAY + dt.timedelta(hours=22), is_sleep=False)
    assert (noon["color_temp_kelvin"], noon["brightness_pct"]) == (6500, 100)
    assert (night["color_temp_kelvin"], night["brightness_pct"]) == (2700, 1)
