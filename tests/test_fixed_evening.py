"""Tests for the fixed local-time evening color temperature."""

import datetime as dt
import zoneinfo
from itertools import pairwise

import pytest
import voluptuous as vol
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    SunLightSettings,
)
from homeassistant.components.adaptive_lighting.const import (
    _DOMAIN_SCHEMA,
    validate_fixed_evening,
)

H = dt.timedelta(hours=1)
PARIS = zoneinfo.ZoneInfo("Europe/Paris")
PARIS_LOCATION = Location(
    LocationInfo(
        name="Paris",
        region="France",
        timezone="Europe/Paris",
        latitude=48.8566,
        longitude=2.3522,
    ),
)
TROMSO_LOCATION = Location(
    LocationInfo(
        name="Tromso",
        region="Norway",
        timezone="Europe/Oslo",
        latitude=69.6492,
        longitude=18.9553,
    ),
)


def make_settings(
    plateau_end=None,
    descent_end=None,
    *,
    location=PARIS_LOCATION,
    timezone=PARIS,
    fixed_times=False,
    **kwargs,
):
    """Astral based settings, or with fixed sunrise 06:00 / sunset 18:00 (local)."""
    params = {
        "name": "kitchen",
        "astral_observer": location.observer,
        "adapt_until_sleep": False,
        "max_brightness": 100,
        "max_color_temp": 4000,
        "min_brightness": 30,
        "min_color_temp": 2700,
        "sleep_brightness": 1,
        "sleep_rgb_or_color_temp": "color_temp",
        "sleep_color_temp": 1000,
        "sleep_rgb_color": (255, 56, 0),
        "sunrise_time": dt.time(6, 0) if fixed_times else None,
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": dt.time(18, 0) if fixed_times else None,
        "min_sunset_time": None,
        "max_sunset_time": None,
        "brightness_mode_time_dark": dt.timedelta(minutes=30),
        "brightness_mode_time_light": dt.timedelta(minutes=30),
        "timezone": timezone,
        "color_temp_fixed_plateau_end": plateau_end,
        "color_temp_fixed_descent_end": descent_end,
    }
    params.update(kwargs)
    return SunLightSettings(**params)


def kitchen(**kwargs):
    return make_settings(dt.time(21, 0), dt.time(23, 0), **kwargs)


def local(day, hour, minute=0, *, tz=PARIS):
    return dt.datetime.combine(day, dt.time(hour, minute), tz)


def kelvin(settings, when, is_sleep=False):
    return settings.brightness_and_color(when, is_sleep)["color_temp_kelvin"]


def grid(day, step_minutes=5, days=1, tz=PARIS):
    start = dt.datetime.combine(day, dt.time(0), tz)
    return [
        start + dt.timedelta(minutes=m) for m in range(0, days * 24 * 60, step_minutes)
    ]


# One day per season, plus the days around the DST changes and the solstices.
SEASON_DAYS = [
    dt.date(2026, 1, 15),
    dt.date(2026, 3, 20),
    dt.date(2026, 6, 21),
    dt.date(2026, 9, 22),
    dt.date(2026, 12, 21),
]


@pytest.mark.parametrize("day", SEASON_DAYS)
@pytest.mark.parametrize("adapt_until_sleep", [True, False])
@pytest.mark.parametrize("rgb", ["color_temp", "rgb_color"])
def test_unset_is_identical_to_before(day, adapt_until_sleep, rgb):
    """No option set: the result is bit-for-bit the same as without the fields."""
    kwargs = {"adapt_until_sleep": adapt_until_sleep, "sleep_rgb_or_color_temp": rgb}
    default = make_settings(**kwargs)
    explicit_none = make_settings(None, None, **kwargs)
    for when in grid(day, 7):
        for is_sleep in (False, True):
            assert default.brightness_and_color(
                when,
                is_sleep,
            ) == explicit_none.brightness_and_color(when, is_sleep)
        assert default.sun.sun_position(when) == explicit_none.sun.sun_position(when)


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_kitchen_curve_all_year(day):
    """4000 K until 21:00, smooth descent, 2700 K from 23:00 whatever the season."""
    settings = kitchen()
    assert kelvin(settings, local(day, 21, 0)) == 4000
    assert kelvin(settings, local(day, 20, 59)) == 4000
    assert kelvin(settings, local(day, 21, 0)) == 4000
    # cosine easing: exactly halfway at 22:00
    assert kelvin(settings, local(day, 22, 0)) == 3350
    assert 3350 < kelvin(settings, local(day, 21, 30)) < 4000
    assert 2700 < kelvin(settings, local(day, 22, 30)) < 3350
    assert kelvin(settings, local(day, 23, 0)) == 2700
    assert kelvin(settings, local(day, 23, 30)) == 2700


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_morning_and_brightness_are_unchanged(day):
    default = make_settings()
    settings = kitchen()
    for when in grid(day, 5, days=2):
        # brightness is never touched, sleep mode keeps priority
        assert settings.brightness_pct(when, False) == default.brightness_pct(
            when,
            False,
        )
        assert settings.brightness_and_color(
            when,
            True,
        ) == default.brightness_and_color(
            when,
            True,
        )
        brightness = settings.brightness_and_color(when, False)
        reference = default.brightness_and_color(when, False)
        assert brightness["brightness_pct"] == reference["brightness_pct"]
        assert brightness["sun_position"] == reference["sun_position"]
    # morning: from the end of the previous descent to solar noon
    for when in grid(day, 5):
        noon, _ = settings.sun.noon_and_midnight(when)
        if when.hour < 12 and when < noon:
            assert kelvin(settings, when) == kelvin(default, when)


def test_unrelated_brightness_modes_are_unchanged():
    day = dt.date(2026, 1, 15)
    for mode in ("default", "linear", "tanh"):
        default = make_settings(brightness_mode=mode)
        settings = kitchen(brightness_mode=mode)
        for when in grid(day, 11):
            assert settings.brightness_pct(when, False) == default.brightness_pct(
                when,
                False,
            )


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_monotonic_and_continuous_from_noon_to_the_morning(day):
    settings = kitchen()
    noon, _ = settings.sun.noon_and_midnight(local(day, 12))
    sunrise = settings.sun.sunrise(day + dt.timedelta(days=1))
    values = []
    when = noon
    while when <= sunrise:
        values.append(settings.brightness_and_color(when, False)["color_temp_kelvin"])
        when += dt.timedelta(minutes=1)
    assert values[0] == 4000
    assert values[-1] == 2700
    assert all(a >= b for a, b in pairwise(values))
    # cosine slope is at most pi/2 * 1300 K / 120 min = 17 K/min (rounded to 5 K)
    assert max(a - b for a, b in pairwise(values)) <= 20


def test_winter_evening_stays_at_max_after_sunset():
    settings = kitchen()
    day = dt.date(2026, 12, 21)
    sunset = settings.sun.sunset(day)
    assert sunset.astimezone(PARIS).hour < 18
    assert kelvin(make_settings(), sunset + 2 * H) == 2700  # legacy
    assert kelvin(settings, sunset + 2 * H) == 4000
    assert kelvin(settings, local(day, 20, 30)) == 4000


def test_summer_sun_still_up_at_the_plateau_end():
    settings = kitchen()
    day = dt.date(2026, 6, 21)
    sunset = settings.sun.sunset(day).astimezone(PARIS)
    assert sunset.hour == 21
    # the default curve is already near the minimum at sunset
    assert kelvin(make_settings(), local(day, 21, 0)) < 3000
    assert kelvin(settings, local(day, 21, 0)) == 4000
    assert kelvin(settings, local(day, 22, 0)) == 3350


def test_descent_ending_before_sunset_does_not_jump_back_up():
    # sunset 18:00, plateau until 14:00 and descent to 15:00: stays at 2700 until sunset
    settings = make_settings(dt.time(14, 0), dt.time(15, 0), fixed_times=True)
    day = dt.date(2026, 6, 1)
    assert kelvin(settings, local(day, 14, 0)) == 4000
    assert kelvin(settings, local(day, 15, 0)) == 2700
    assert kelvin(settings, local(day, 16, 30)) == 2700
    assert kelvin(settings, local(day, 17, 59)) == 2700
    assert kelvin(settings, local(day, 18, 30)) == 2700


def test_before_the_plateau_end_it_is_the_regular_afternoon_value_at_noon():
    settings = make_settings(dt.time(18, 0), dt.time(20, 0), fixed_times=True)
    day = dt.date(2026, 6, 1)
    noon, _ = settings.sun.noon_and_midnight(local(day, 12))
    assert kelvin(settings, noon) == 4000
    assert kelvin(settings, noon + 3 * H) == 4000  # default curve would be lower
    assert kelvin(make_settings(fixed_times=True), noon + 3 * H) < 4000


# --- midnight ---------------------------------------------------------------


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_descent_across_midnight(day):
    settings = make_settings(dt.time(23, 0), dt.time(1, 0))
    assert kelvin(settings, local(day, 22, 59)) == 4000
    assert kelvin(settings, local(day, 23, 0)) == 4000
    next_day = day + dt.timedelta(days=1)
    assert kelvin(settings, local(day, 23, 30)) > 3350
    assert kelvin(settings, local(next_day, 0, 0)) == 3350
    assert kelvin(settings, local(next_day, 0, 30)) < 3350
    assert kelvin(settings, local(next_day, 1, 0)) == 2700
    assert kelvin(settings, local(next_day, 3, 0)) == 2700
    # the day after, the same thing happens again at the same wall-clock times
    assert kelvin(settings, local(next_day, 23, 0)) == 4000


def test_pre_midnight_times_do_not_leak_into_the_morning():
    settings = kitchen()
    default = make_settings()
    day = dt.date(2026, 3, 20)
    for hour in range(12):
        when = local(day, hour, 30)
        noon, _ = settings.sun.noon_and_midnight(when)
        if when < noon:
            assert kelvin(settings, when) == kelvin(default, when)


def test_descent_end_clamped_at_the_next_sunrise():
    # plateau 20:00, descent end 08:00 (12h) but sunrise is 06:00
    settings = make_settings(dt.time(20, 0), dt.time(8, 0), fixed_times=True)
    day = dt.date(2026, 6, 1)
    nxt = day + dt.timedelta(days=1)
    assert kelvin(settings, local(day, 20, 0)) == 4000
    assert kelvin(settings, local(nxt, 6, 0)) == 2700
    assert kelvin(settings, local(nxt, 5, 59)) <= 2705
    assert kelvin(settings, local(nxt, 6, 30)) == kelvin(
        make_settings(fixed_times=True),
        local(nxt, 6, 30),
    )


def test_window_that_does_not_fit_before_the_next_sunrise_is_ignored():
    # plateau 12:00-12:30 but noon is 15:00: nothing to do
    settings = make_settings(
        dt.time(12, 0),
        dt.time(12, 30),
        fixed_times=True,
        sunrise_time=dt.time(8, 0),
        sunset_time=dt.time(22, 0),
    )
    default = make_settings(
        fixed_times=True,
        sunrise_time=dt.time(8, 0),
        sunset_time=dt.time(22, 0),
    )
    for when in grid(dt.date(2026, 6, 1), 10):
        assert settings.brightness_and_color(
            when,
            False,
        ) == default.brightness_and_color(
            when,
            False,
        )


def test_plateau_end_before_solar_noon_starts_the_descent_at_noon():
    # noon is 15:00, plateau_end 12:00, descent end 17:00: 2h descent from noon
    settings = make_settings(
        dt.time(12, 0),
        dt.time(17, 0),
        fixed_times=True,
        sunrise_time=dt.time(8, 0),
        sunset_time=dt.time(22, 0),
    )
    day = dt.date(2026, 6, 1)
    assert kelvin(settings, local(day, 15, 0)) == 4000
    assert kelvin(settings, local(day, 16, 0)) == 3350
    assert kelvin(settings, local(day, 17, 0)) == 2700


# --- DST and time zones --------------------------------------------------


@pytest.mark.parametrize(
    "day",
    [
        dt.date(2026, 3, 28),  # night to the spring-forward day
        dt.date(2026, 3, 29),
        dt.date(2026, 10, 24),  # night to the fall-back day
        dt.date(2026, 10, 25),
    ],
)
@pytest.mark.parametrize(
    ("plateau_end", "descent_end"),
    [
        (dt.time(21, 0), dt.time(23, 0)),
        (dt.time(23, 0), dt.time(3, 30)),  # contains the 02:00-03:00 DST change
        (dt.time(23, 0), dt.time(2, 30)),  # 02:30 does not exist / exists twice
    ],
)
def test_dst_changes_stay_continuous_and_monotonic(day, plateau_end, descent_end):
    settings = make_settings(plateau_end, descent_end)
    start = dt.datetime.combine(day, dt.time(12), PARIS)
    noon, _ = settings.sun.noon_and_midnight(start)
    end = settings.sun.sunrise(day + dt.timedelta(days=1))
    values = []
    when = noon
    while when <= end:
        values.append(kelvin(settings, when))
        when += dt.timedelta(minutes=1)
    assert values[0] == 4000
    assert values[-1] == 2700
    assert all(a >= b for a, b in pairwise(values))
    assert max(a - b for a, b in pairwise(values)) <= 25
    if descent_end == dt.time(23, 0):
        assert kelvin(settings, local(day, 22, 0)) == 3350


def test_dst_day_wall_clock_times_hold():
    # on both DST days the evening is still 4000 K at 20:59 and 2700 K at 23:00
    for day in (dt.date(2026, 3, 29), dt.date(2026, 10, 25)):
        settings = kitchen()
        assert kelvin(settings, local(day, 20, 59)) == 4000
        assert kelvin(settings, local(day, 23, 0)) == 2700


def test_times_are_interpreted_in_the_configured_time_zone():
    day = dt.date(2026, 3, 20)
    paris = kitchen()
    utc = make_settings(
        dt.time(21, 0),
        dt.time(23, 0),
        timezone=zoneinfo.ZoneInfo("UTC"),
    )
    # 21:00 in Paris (UTC+1 in March) is 20:00 UTC: Paris is already descending
    # one hour before UTC is
    moment = dt.datetime(2026, 3, 20, 21, 30, tzinfo=dt.UTC)
    assert kelvin(utc, moment) > kelvin(paris, moment)
    assert kelvin(paris, dt.datetime(2026, 3, 20, 20, 0, tzinfo=dt.UTC)) == 4000
    assert kelvin(paris, dt.datetime(2026, 3, 20, 22, 0, tzinfo=dt.UTC)) == 2700
    assert kelvin(paris, local(day, 22, 0)) == 3350
    # the same instant gives the same answer whatever tz the datetime carries
    instant = local(day, 22, 0)
    assert kelvin(paris, instant) == kelvin(paris, instant.astimezone(dt.UTC))
    assert kelvin(paris, instant) == kelvin(
        paris,
        instant.astimezone(zoneinfo.ZoneInfo("Asia/Tokyo")),
    )


# --- sleep mode, rgb, adapt_until_sleep, polar -------------------------------


def test_sleep_mode_keeps_priority():
    day = dt.date(2026, 12, 21)
    default = make_settings()
    settings = kitchen()
    for hour in (9, 14, 19, 22, 23):
        when = local(day, hour)
        assert settings.brightness_and_color(
            when,
            True,
        ) == default.brightness_and_color(
            when,
            True,
        )


def test_rgb_sleep_color_after_sunset_does_not_override_the_fixed_evening():
    day = dt.date(2026, 12, 21)
    settings = kitchen(adapt_until_sleep=True, sleep_rgb_or_color_temp="rgb_color")
    default = make_settings(adapt_until_sleep=True, sleep_rgb_or_color_temp="rgb_color")
    when = local(day, 19, 0)  # after sunset, still in the plateau
    result = settings.brightness_and_color(when, False)
    assert result["color_temp_kelvin"] == 4000
    assert result["force_rgb_color"] is False
    assert default.brightness_and_color(when, False)["force_rgb_color"] is True
    # after the descent the night behavior is the legacy one
    late = local(day, 23, 30)
    assert settings.brightness_and_color(late, False) == default.brightness_and_color(
        late,
        False,
    )


def test_adapt_until_sleep_night_resumes_after_the_descent():
    day = dt.date(2026, 12, 21)
    settings = kitchen(adapt_until_sleep=True)
    default = make_settings(adapt_until_sleep=True)
    # once the descent is over, the night is the regular one again
    for hour, minute in [(23, 30), (2, 0), (5, 0)]:
        when = local(day if hour > 12 else day + dt.timedelta(days=1), hour, minute)
        assert kelvin(settings, when) == kelvin(default, when)
    # ... with a step from 2700 K at the end of the descent (documented)
    assert kelvin(settings, local(day, 23, 0)) == 2700
    assert kelvin(default, local(day, 23, 0)) < 2700
    # in the plateau/descent the fixed curve is used, not the night gradient
    assert kelvin(settings, local(day, 20, 0)) == 4000
    assert kelvin(settings, local(day, 22, 0)) == 3350


@pytest.mark.parametrize("day", [dt.date(2026, 6, 21), dt.date(2026, 12, 21)])
def test_polar_days(day):
    settings = make_settings(
        dt.time(21, 0),
        dt.time(23, 0),
        location=TROMSO_LOCATION,
        timezone=zoneinfo.ZoneInfo("Europe/Oslo"),
    )
    tz = zoneinfo.ZoneInfo("Europe/Oslo")
    for when in grid(day, 10, days=2, tz=tz):
        assert 2700 <= kelvin(settings, when) <= 4000


# --- validation ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("plateau_end", "descent_end"),
    [
        (None, None),
        ("None", "None"),
        ("21:00:00", "23:00:00"),
        ("21:00", "23:00"),
        (dt.time(21, 0), dt.time(23, 0)),
        ("12:00:00", "13:00:00"),
        ("12:00:00", "00:00:00"),  # exactly 12 hours
        ("23:00:00", "01:00:00"),  # across midnight
        ("23:59:59", "00:00:00"),
        ("21:00:00", "21:00:01"),
    ],
)
def test_valid_pairs(plateau_end, descent_end):
    validate_fixed_evening(plateau_end, descent_end)


@pytest.mark.parametrize(
    ("plateau_end", "descent_end"),
    [
        ("21:00:00", None),  # only one
        (None, "23:00:00"),
        ("21:00:00", "None"),
        ("21:00:00", "21:00:00"),  # no descent
        ("23:00:00", "21:00:00"),  # 22 hours, i.e. the descent would be inverted
        ("21:00:00", "20:59:59"),
        ("11:59:59", "13:00:00"),  # plateau end in the morning
        ("08:00:00", "10:00:00"),
        ("12:00:00", "00:00:01"),  # more than 12 hours
        ("nonsense", "23:00:00"),
        ("25:00:00", "23:00:00"),
    ],
)
def test_invalid_pairs(plateau_end, descent_end):
    with pytest.raises(vol.Invalid):
        validate_fixed_evening(plateau_end, descent_end)


def test_yaml_schema():
    schema = _DOMAIN_SCHEMA
    config = schema({})
    assert "color_temp_fixed_plateau_end" not in config
    assert "color_temp_fixed_descent_end" not in config
    config = schema(
        {
            "color_temp_fixed_plateau_end": "21:00:00",
            "color_temp_fixed_descent_end": "23:00:00",
        },
    )
    assert config["color_temp_fixed_plateau_end"] == "21:00:00"
    assert config["color_temp_fixed_descent_end"] == "23:00:00"
    with pytest.raises(vol.Invalid):
        schema({"color_temp_fixed_plateau_end": "21:00:00"})
    with pytest.raises(vol.Invalid):
        schema(
            {
                "color_temp_fixed_plateau_end": "22:00:00",
                "color_temp_fixed_descent_end": "22:00:00",
            },
        )
