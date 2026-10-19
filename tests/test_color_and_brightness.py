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


# --- Color temperature plateau --------------------------------------------

PLATEAU_DAY = dt.date(2022, 6, 1)
H = dt.timedelta(hours=1)


def _plateau_settings(
    morning=dt.timedelta(),
    evening=dt.timedelta(),
    *,
    sunset_offset=dt.timedelta(),
    sunrise_offset=dt.timedelta(),
    adapt_until_sleep=False,
    brightness_mode="default",
    sleep_rgb_or_color_temp="color_temp",
    min_color_temp=2700,
    max_color_temp=4000,
):
    """Settings with fixed sunrise 06:00 and sunset 18:00 UTC (noon is 12:00)."""
    return SunLightSettings(
        name="test",
        astral_observer=location.observer,
        adapt_until_sleep=adapt_until_sleep,
        max_brightness=100,
        max_color_temp=max_color_temp,
        min_brightness=30,
        min_color_temp=min_color_temp,
        sleep_brightness=1,
        sleep_rgb_or_color_temp=sleep_rgb_or_color_temp,
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=dt.time(6, 0),
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=dt.time(18, 0),
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=dt.timedelta(minutes=30),
        brightness_mode_time_light=dt.timedelta(minutes=30),
        brightness_mode=brightness_mode,
        sunrise_offset=sunrise_offset,
        sunset_offset=sunset_offset,
        color_temp_plateau_morning=morning,
        color_temp_plateau_evening=evening,
        timezone=dt.UTC,
    )


def _at(hour, minute=0, second=0):
    return dt.datetime.combine(PLATEAU_DAY, dt.time(hour, minute, second), dt.UTC)


def _kelvin(settings, when, is_sleep=False):
    return settings.brightness_and_color(when, is_sleep)["color_temp_kelvin"]


def _day_grid(step_minutes=7):
    start = _at(0)
    return [start + dt.timedelta(minutes=m) for m in range(0, 24 * 60, step_minutes)]


def _reference_sun_position(sun, when):
    """The original (pre-plateau) formula, kept here as the reference."""
    target_ts = when.timestamp()
    (_, prev_ts), (next_event, next_ts) = sun.prev_and_next_events(when)
    h, x = (
        (prev_ts, next_ts)
        if next_event in (SunEvent.SUNSET, SunEvent.SUNRISE)
        else (next_ts, prev_ts)
    )
    k = 1 if next_event in (SunEvent.SUNSET, SunEvent.NOON) else -1
    return k * (1 - ((target_ts - h) / (h - x)) ** 2)


@pytest.mark.parametrize("sunset_offset", [dt.timedelta(), 2 * H, -2 * H])
@pytest.mark.parametrize("adapt_until_sleep", [True, False])
def test_plateau_defaults_are_bit_for_bit_identical(sunset_offset, adapt_until_sleep):
    default = _plateau_settings(
        sunset_offset=sunset_offset,
        adapt_until_sleep=adapt_until_sleep,
    )
    explicit_zero = _plateau_settings(
        dt.timedelta(0),
        dt.timedelta(seconds=0),
        sunset_offset=sunset_offset,
        adapt_until_sleep=adapt_until_sleep,
    )
    for when in _day_grid():
        reference = _reference_sun_position(default.sun, when)
        assert default.sun.sun_position(when) == reference
        assert default.sun.sun_position(when, dt.timedelta(), dt.timedelta()) == (
            reference
        )
        for is_sleep in (False, True):
            assert default.brightness_and_color(
                when,
                is_sleep,
            ) == explicit_zero.brightness_and_color(when, is_sleep)
        assert default.color_temp_kelvin(reference) == _kelvin(default, when)


def test_plateau_morning_shape():
    settings = _plateau_settings(morning=3 * H)
    assert _kelvin(settings, _at(6)) == 2700  # sunrise: still the minimum
    assert _kelvin(settings, _at(9)) == 4000  # plateau starts 3h before noon
    assert _kelvin(settings, _at(9, 0, 1)) == 4000
    assert _kelvin(settings, _at(10, 30)) == 4000
    assert _kelvin(settings, _at(12)) == 4000
    # the ramp is compressed: reaching 4000 earlier than without plateau
    default = _plateau_settings()
    assert _kelvin(settings, _at(8)) > _kelvin(default, _at(8))
    # and is monotonic
    values = [_kelvin(settings, _at(6) + dt.timedelta(minutes=m)) for m in range(361)]
    assert values == sorted(values)


def test_plateau_evening_shape():
    settings = _plateau_settings(evening=4 * H)
    assert _kelvin(settings, _at(12)) == 4000
    assert _kelvin(settings, _at(16)) == 4000  # plateau ends 4h after noon
    assert _kelvin(settings, _at(16, 0, 1)) >= 3995
    assert _kelvin(settings, _at(18)) == 2700  # sunset: the minimum again
    default = _plateau_settings()
    assert _kelvin(settings, _at(15)) > _kelvin(default, _at(15))
    values = [_kelvin(settings, _at(12) + dt.timedelta(minutes=m)) for m in range(361)]
    assert values == sorted(values, reverse=True)


def test_plateau_sides_are_independent():
    default = _plateau_settings()
    morning = _plateau_settings(morning=3 * H)
    evening = _plateau_settings(evening=3 * H)
    both = _plateau_settings(morning=3 * H, evening=3 * H)
    noon = _at(12)
    for when in _day_grid(5):
        before_noon = when < noon
        after_noon = when > noon
        if after_noon:
            # a morning plateau never changes the evening
            assert morning.brightness_and_color(
                when,
                False,
            ) == default.brightness_and_color(when, False)
            assert both.brightness_and_color(when, False) == (
                evening.brightness_and_color(when, False)
            )
        if before_noon:
            # an evening plateau never changes the morning
            assert evening.brightness_and_color(
                when,
                False,
            ) == default.brightness_and_color(when, False)
            assert both.brightness_and_color(when, False) == (
                morning.brightness_and_color(when, False)
            )


def test_plateau_is_continuous_at_its_boundaries():
    settings = _plateau_settings(morning=2 * H, evening=2 * H)
    eps = dt.timedelta(milliseconds=1)
    for boundary in (_at(10), _at(14)):
        before = settings.sun.sun_position(boundary - eps, 2 * H, 2 * H)
        after = settings.sun.sun_position(boundary + eps, 2 * H, 2 * H)
        assert abs(before - after) < 1e-6
        assert max(before, after) == pytest.approx(1, abs=1e-6)
    # sunrise and sunset still map to exactly 0
    for event in (_at(6), _at(18)):
        assert settings.sun.sun_position(event, 2 * H, 2 * H) == pytest.approx(
            0,
            abs=1e-9,
        )


def test_plateau_never_decreases_color_temp():
    default = _plateau_settings()
    plateau = _plateau_settings(morning=5 * H, evening=3 * H)
    for when in _day_grid(3):
        assert _kelvin(plateau, when) >= _kelvin(default, when)


@pytest.mark.parametrize("plateau", [dt.timedelta(hours=12), dt.timedelta(days=3)])
def test_plateau_larger_than_the_half_day_is_clamped(plateau):
    settings = _plateau_settings(plateau, plateau)
    sun = settings.sun
    assert _kelvin(settings, _at(6)) == 2700
    assert _kelvin(settings, _at(18)) == 2700
    assert _kelvin(settings, _at(12)) == 4000
    previous = None
    for when in _day_grid(1):
        position = sun.sun_position(when, plateau, plateau)
        assert -1 <= position <= 1
        if previous is not None and _at(6) <= when <= _at(18):
            # no jump bigger than what a smooth ramp over 10% of the half-day
            # (36 minutes) allows between consecutive minutes
            assert abs(position - previous) < 0.1
        previous = position
    # a ramp of 10% of the half-day (36 minutes) remains at both ends
    assert _kelvin(settings, _at(17, 59)) < 4000
    assert _kelvin(settings, _at(17, 30)) < 4000
    assert _kelvin(settings, _at(6, 30)) < 4000


def test_plateau_with_a_collapsed_day():
    # sunrise and sunset only a few seconds apart around noon
    settings = SunLightSettings(
        name="test",
        astral_observer=location.observer,
        adapt_until_sleep=False,
        max_brightness=100,
        max_color_temp=4000,
        min_brightness=30,
        min_color_temp=2700,
        sleep_brightness=1,
        sleep_rgb_or_color_temp="color_temp",
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sunrise_time=dt.time(11, 59, 58),
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_time=dt.time(12, 0, 2),
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode_time_dark=dt.timedelta(minutes=30),
        brightness_mode_time_light=dt.timedelta(minutes=30),
        color_temp_plateau_morning=12 * H,
        color_temp_plateau_evening=12 * H,
        timezone=dt.UTC,
    )
    for seconds in range(-5, 6):
        when = _at(12) + dt.timedelta(seconds=seconds)
        assert 2700 <= _kelvin(settings, when) <= 4000
    assert _kelvin(settings, _at(12)) == 4000
    assert _kelvin(settings, _at(3)) == 2700


def test_plateau_does_not_touch_the_night_or_sleep():
    default = _plateau_settings(adapt_until_sleep=True)
    plateau = _plateau_settings(5 * H, 5 * H, adapt_until_sleep=True)
    for when in _day_grid(11):
        if when < _at(6) or when > _at(18):
            # below the horizon (including the transition to the sleep color)
            assert plateau.brightness_and_color(when, False) == (
                default.brightness_and_color(when, False)
            )
        # sleep mode ignores the color temperature curve entirely
        sleep = plateau.brightness_and_color(when, True)
        assert sleep == default.brightness_and_color(when, True)
        assert sleep["color_temp_kelvin"] == 1000
        assert sleep["brightness_pct"] == 1


def test_plateau_with_rgb_sleep_color_after_sunset():
    default = _plateau_settings(
        adapt_until_sleep=True,
        sleep_rgb_or_color_temp="rgb_color",
    )
    plateau = _plateau_settings(
        4 * H,
        4 * H,
        adapt_until_sleep=True,
        sleep_rgb_or_color_temp="rgb_color",
    )
    for when in (_at(19), _at(22), _at(1), _at(5, 30)):
        assert plateau.brightness_and_color(when, False) == (
            default.brightness_and_color(when, False)
        )


@pytest.mark.parametrize("brightness_mode", ["default", "linear", "tanh"])
def test_plateau_does_not_change_brightness(brightness_mode):
    default = _plateau_settings(brightness_mode=brightness_mode)
    plateau = _plateau_settings(
        5 * H,
        5 * H,
        brightness_mode=brightness_mode,
        adapt_until_sleep=True,
    )
    reference = _plateau_settings(
        brightness_mode=brightness_mode,
        adapt_until_sleep=True,
    )
    for when in _day_grid(9):
        for is_sleep in (False, True):
            assert plateau.brightness_pct(when, is_sleep) == (
                reference.brightness_pct(when, is_sleep)
            )
            result = plateau.brightness_and_color(when, is_sleep)
            ref = reference.brightness_and_color(when, is_sleep)
            assert result["brightness_pct"] == ref["brightness_pct"]
            # the (brightness-driving) sun position itself is left untouched
            assert result["sun_position"] == ref["sun_position"]
        assert default.brightness_pct(when, False) == reference.brightness_pct(
            when,
            False,
        )


def test_plateau_with_sunset_offset_is_anchored_on_noon():
    # sunrise 06:00 and sunset 18:00 + 2h offset = 20:00, so the (adjusted) noon,
    # the middle of the two, is 13:00 and the evening ramp spans 13:00 -> 20:00
    settings = _plateau_settings(evening=4 * H, sunset_offset=2 * H)
    default = _plateau_settings(sunset_offset=2 * H)
    assert _kelvin(settings, _at(11)) == _kelvin(default, _at(11))
    assert _kelvin(settings, _at(13)) == 4000
    assert _kelvin(settings, _at(17)) == 4000  # plateau ends 4h after noon
    assert _kelvin(settings, _at(18)) < 4000
    assert _kelvin(settings, _at(18)) > _kelvin(default, _at(18))
    assert _kelvin(settings, _at(20)) == 2700  # the offset sunset is respected
    # the morning is not affected by the sunset offset nor the other way around
    morning = _plateau_settings(morning=2 * H, sunset_offset=2 * H)
    assert _kelvin(morning, _at(11)) == 4000
    assert _kelvin(morning, _at(8)) > _kelvin(default, _at(8))
    assert _kelvin(morning, _at(14)) == _kelvin(default, _at(14))


def test_plateau_with_sunrise_and_sunset_times_and_limits():
    settings = _plateau_settings(morning=2 * H, evening=2 * H, sunrise_offset=-1 * H)
    # sunrise is 05:00 and sunset 18:00: noon is their midpoint (11:30)
    sunrise = settings.sun.sunrise(PLATEAU_DAY)
    sunset = settings.sun.sunset(PLATEAU_DAY)
    noon, _ = settings.sun.noon_and_midnight(_at(12))
    assert noon == sunrise + (sunset - sunrise) / 2
    assert _kelvin(settings, noon) == 4000
    assert _kelvin(settings, noon - 2 * H) == 4000
    assert _kelvin(settings, noon + 2 * H) == 4000
    assert _kelvin(settings, sunrise) == 2700
    assert _kelvin(settings, sunset) == 2700


def test_plateau_astral_sunrise_and_sunset(tzinfo_and_location):
    tzinfo, loc = tzinfo_and_location
    kwargs = {
        "name": "test",
        "astral_observer": loc.observer,
        "adapt_until_sleep": False,
        "max_brightness": 100,
        "max_color_temp": 4000,
        "min_brightness": 30,
        "min_color_temp": 2700,
        "sleep_brightness": 1,
        "sleep_rgb_or_color_temp": "color_temp",
        "sleep_color_temp": 1000,
        "sleep_rgb_color": (255, 56, 0),
        "sunrise_time": None,
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": None,
        "min_sunset_time": None,
        "max_sunset_time": None,
        "brightness_mode_time_dark": dt.timedelta(minutes=30),
        "brightness_mode_time_light": dt.timedelta(minutes=30),
        "sunset_offset": 2 * H,
        "timezone": tzinfo,
    }
    default = SunLightSettings(**kwargs)
    plateau = SunLightSettings(
        **kwargs,
        color_temp_plateau_morning=2 * H,
        color_temp_plateau_evening=4 * H,
    )
    day = dt.datetime(2022, 3, 20, tzinfo=dt.UTC)
    noon, _ = default.sun.noon_and_midnight(day)
    assert _kelvin(plateau, noon) == 4000
    assert _kelvin(plateau, noon - 2 * H) == 4000
    assert _kelvin(plateau, noon + 4 * H) == 4000
    assert _kelvin(plateau, default.sun.sunset(day.date())) == 2700
    assert _kelvin(plateau, default.sun.sunrise(day.date())) == 2700


@pytest.mark.parametrize("date", [POLAR_NIGHT_DATE, MIDNIGHT_SUN_DATE])
def test_plateau_on_polar_days(date):
    kwargs = {
        "name": "test",
        "astral_observer": TROMSO.observer,
        "adapt_until_sleep": False,
        "max_brightness": 100,
        "max_color_temp": 4000,
        "min_brightness": 30,
        "min_color_temp": 2700,
        "sleep_brightness": 1,
        "sleep_rgb_or_color_temp": "color_temp",
        "sleep_color_temp": 1000,
        "sleep_rgb_color": (255, 56, 0),
        "sunrise_time": None,
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": None,
        "min_sunset_time": None,
        "max_sunset_time": None,
        "brightness_mode_time_dark": dt.timedelta(hours=1),
        "brightness_mode_time_light": dt.timedelta(hours=1),
        "timezone": zoneinfo.ZoneInfo("Europe/Oslo"),
    }
    plateau = SunLightSettings(
        **kwargs,
        color_temp_plateau_morning=12 * H,
        color_temp_plateau_evening=12 * H,
    )
    start = dt.datetime(date.year, date.month, date.day, tzinfo=dt.UTC)
    noon, _ = plateau.sun.noon_and_midnight(start)
    assert _kelvin(plateau, noon) == 4000
    for minutes in range(0, 24 * 60, 5):
        when = start + dt.timedelta(minutes=minutes)
        assert 2700 <= _kelvin(plateau, when) <= 4000
