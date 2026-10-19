"""Tests for the custom temperature of the fixed evening color temperature plateau."""

import datetime as dt
import zoneinfo
from itertools import pairwise

import pytest
import voluptuous as vol
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.const import (
    _DOMAIN_SCHEMA,
    validate_fixed_plateau_kelvin,
)

from .test_fixed_evening import (
    PARIS,
    SEASON_DAYS,
    TROMSO_LOCATION,
    grid,
    kelvin,
    local,
    make_settings,
)

TOULOUSE = Location(
    LocationInfo(
        name="Toulouse",
        region="France",
        timezone="Europe/Paris",
        latitude=43.57,
        longitude=1.48,
    ),
)
OSLO = zoneinfo.ZoneInfo("Europe/Oslo")
MINUTE = dt.timedelta(minutes=1)


def user_case(plateau_kelvin=4000, **kwargs):
    """Charles' kitchen: 5500 K at noon, held at 4000 K until 21:00, 2700 K at 23:00."""
    params = {
        "location": TOULOUSE,
        "max_color_temp": 5500,
        "sunset_offset": dt.timedelta(hours=2),
        "color_temp_plateau_morning": dt.timedelta(seconds=3600),
        "color_temp_plateau_evening": dt.timedelta(seconds=14400),
        "color_temp_fixed_plateau_kelvin": plateau_kelvin,
    }
    params.update(kwargs)
    return make_settings(dt.time(21, 0), dt.time(23, 0), **params)


def without_fixed(**kwargs):
    """The same settings without any evening option."""
    kwargs.setdefault("location", TOULOUSE)
    kwargs.setdefault("color_temp_plateau_morning", dt.timedelta(seconds=3600))
    kwargs.setdefault("color_temp_plateau_evening", dt.timedelta(seconds=14400))
    return make_settings(
        max_color_temp=5500,
        sunset_offset=dt.timedelta(hours=2),
        **kwargs,
    )


def solar_noon(settings, day):
    when = local(day, 12, 0)
    return min(
        (ts for ev, ts in settings.sun.sun_events(when) if ev.name == "NOON"),
    )


ALL_DAYS = [dt.date(2026, 1, 1) + dt.timedelta(days=n) for n in range(365)]


def test_target_is_reached_and_held_until_21h_every_day_of_the_year():
    """Exactly 4000 K from 20:00 to 21:00 (Cuisine options), 365 days, DST included."""
    settings = user_case()
    for day in ALL_DAYS:
        for hour, minute in [(20, 0), (20, 15), (20, 30), (20, 45), (20, 59), (21, 0)]:
            assert kelvin(settings, local(day, hour, minute)) == 4000, (day, hour)
        assert kelvin(settings, local(day, 22, 0)) == 3350, day
        assert kelvin(settings, local(day, 23, 0)) == 2700, day
        assert kelvin(settings, local(day, 23, 30)) == 2700, day


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_user_case_all_year(day):
    """Daytime maximum kept, target held, then easing to the minimum."""
    settings = user_case()
    peak = max(kelvin(settings, when) for when in grid(day, 5))
    assert peak >= 5490  # the daytime maximum is not capped by the plateau
    assert kelvin(settings, local(day, 14, 0)) >= 5490
    held = [kelvin(settings, when) for when in grid(day, 1)]
    start = 20 * 60
    assert held[start : 21 * 60 + 1] == [4000] * 61
    assert kelvin(settings, local(day, 22, 30)) == 2890
    assert kelvin(settings, local(day, 21, 30)) == 3810


@pytest.mark.parametrize("day", SEASON_DAYS)
@pytest.mark.parametrize("plateau_evening", [0, 3600, 4 * 3600, 8 * 3600, 43200])
@pytest.mark.parametrize("plateau_morning", [0, 3600])
def test_target_is_held_for_any_evening_plateau_duration(
    day,
    plateau_evening,
    plateau_morning,
):
    """Between the regular curve and the target, the target is always reached."""
    extra = {
        "color_temp_plateau_evening": dt.timedelta(seconds=plateau_evening),
        "color_temp_plateau_morning": dt.timedelta(seconds=plateau_morning),
    }
    fixed = user_case(**extra)
    regular = without_fixed(**extra)
    noon = dt.datetime.fromtimestamp(solar_noon(fixed, day), PARIS)
    for when in grid(day, 3):
        if noon <= when <= local(day, 21, 0):
            value = kelvin(fixed, when)
            assert value >= 4000
            # never above what the regular curve (or the target) would give
            assert value <= max(kelvin(regular, when), 4000)
    for minute in range(20 * 60, 21 * 60 + 1, 5):
        assert kelvin(fixed, local(day, 0, 0) + dt.timedelta(minutes=minute)) == 4000


@pytest.mark.parametrize("day", [dt.date(2026, 1, 15), dt.date(2026, 12, 21)])
def test_when_the_regular_curve_gets_there_in_time_it_is_not_altered(day):
    """In winter the regular afternoon curve reaches the target by itself."""
    fixed = user_case()
    regular = without_fixed()
    noon = dt.datetime.fromtimestamp(solar_noon(fixed, day), PARIS)
    for when in grid(day, 3):
        if noon <= when <= local(day, 21, 0):
            assert kelvin(fixed, when) == max(kelvin(regular, when), 4000)


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_morning_brightness_and_noon_are_unchanged(day):
    """Everything before solar noon, and the brightness all day, is untouched."""
    fixed = user_case()
    regular = without_fixed()
    noon = dt.datetime.fromtimestamp(solar_noon(fixed, day), PARIS)
    for when in grid(day, 3):
        a = fixed.brightness_and_color(when, False)
        b = regular.brightness_and_color(when, False)
        assert a["brightness_pct"] == b["brightness_pct"]
        if when < noon:
            assert a == b
    # the sleep mode keeps priority
    for when in grid(day, 30):
        assert fixed.brightness_and_color(when, True) == regular.brightness_and_color(
            when,
            True,
        )


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_unset_target_is_identical_to_before(day):
    """No target: exactly the behavior of the fixed times without the option."""
    old = make_settings(dt.time(21, 0), dt.time(23, 0), location=TOULOUSE)
    new = make_settings(
        dt.time(21, 0),
        dt.time(23, 0),
        location=TOULOUSE,
        color_temp_fixed_plateau_kelvin=None,
    )
    for when in grid(day, 7):
        assert old.brightness_and_color(when, False) == new.brightness_and_color(
            when,
            False,
        )


@pytest.mark.parametrize("day", SEASON_DAYS)
def test_target_equal_to_max_is_identical_to_unset(day):
    """A target at the maximum is the historical hold at the maximum."""
    old = make_settings(dt.time(21, 0), dt.time(23, 0), location=TOULOUSE)
    new = make_settings(
        dt.time(21, 0),
        dt.time(23, 0),
        location=TOULOUSE,
        color_temp_fixed_plateau_kelvin=4000,
    )
    for when in grid(day, 7):
        assert old.brightness_and_color(when, False) == new.brightness_and_color(
            when,
            False,
        )


@pytest.mark.parametrize("plateau_kelvin", [2700, 2705, 3000, 4000, 5000, 5495, 5500])
@pytest.mark.parametrize(
    "day",
    [*SEASON_DAYS, dt.date(2026, 3, 28), dt.date(2026, 3, 29), dt.date(2026, 10, 25)],
)
def test_continuous_monotonic_and_bounded(day, plateau_kelvin):
    """No jump anywhere, non-increasing from noon on, always within min and max."""
    settings = user_case(plateau_kelvin)
    values = [(when, kelvin(settings, when)) for when in grid(day, 1, days=2)]
    noon = dt.datetime.fromtimestamp(solar_noon(settings, day), PARIS)
    for _, value in values:
        assert 2700 <= value <= 5500
    for (_, a), (_, b) in pairwise(values):
        assert abs(a - b) <= 40  # per minute; the steepest legit slope is ~37 K/min
    after_noon = [value for when, value in values if noon <= when <= local(day, 23, 0)]
    assert after_noon == sorted(after_noon, reverse=True)


@pytest.mark.parametrize("plateau_end_hour", [12, 14, 15, 17, 19, 21])
@pytest.mark.parametrize("day", [dt.date(2026, 6, 21), dt.date(2026, 12, 21)])
def test_no_step_when_the_plateau_ends_before_the_target_is_reached(
    day,
    plateau_end_hour,
):
    """An early plateau end squeezes the ramp (steeper) but never steps."""
    settings = make_settings(
        dt.time(plateau_end_hour, 0),
        dt.time(23, 0),
        location=TOULOUSE,
        max_color_temp=5500,
        sunset_offset=dt.timedelta(hours=2),
        color_temp_fixed_plateau_kelvin=3000,
    )
    values = [kelvin(settings, when) for when in grid(day, 1, days=2)]
    # a 30 minute ramp over 2500 K peaks at 167 K/min; a step would be far larger
    assert max(abs(a - b) for a, b in pairwise(values)) <= 170
    assert kelvin(settings, local(day, 23, 0)) == 2700
    noon = dt.datetime.fromtimestamp(solar_noon(settings, day), PARIS)
    plateau_end = local(day, plateau_end_hour, 0)
    if plateau_end >= noon + dt.timedelta(hours=1):
        assert kelvin(settings, plateau_end) == 3000
        assert kelvin(settings, plateau_end - dt.timedelta(minutes=29)) == 3000


def test_target_at_the_minimum():
    """A target equal to the minimum follows the curve down and then holds."""
    settings = user_case(2700)
    day = dt.date(2026, 10, 19)
    values = [kelvin(settings, when) for when in grid(day, 1, days=2)]
    assert max(abs(a - b) for a, b in pairwise(values)) <= 40
    # the regular curve is still slightly above the minimum at 21:00 here
    assert 2700 <= kelvin(settings, local(day, 21, 0)) <= 2760
    assert kelvin(settings, local(day, 22, 0)) <= 2730
    assert kelvin(settings, local(day, 23, 0)) == 2700
    assert kelvin(settings, local(day, 14, 0)) > 5000


def test_max_equals_min_does_not_divide_by_zero():
    settings = make_settings(
        dt.time(21, 0),
        dt.time(23, 0),
        location=TOULOUSE,
        min_color_temp=3000,
        max_color_temp=3000,
        color_temp_fixed_plateau_kelvin=3000,
    )
    for when in grid(dt.date(2026, 6, 21), 10):
        assert kelvin(settings, when) == 3000


def test_exact_values_for_the_user_case_in_october():
    """Toulouse, 2026-10-19: max by day, 4000 K from 20:00, 2700 K at 23:00."""
    settings = user_case()
    day = dt.date(2026, 10, 19)
    assert kelvin(settings, local(day, 14, 0)) == 5500  # still reaches the maximum
    assert kelvin(settings, local(day, 17, 0)) == 5495
    assert kelvin(settings, local(day, 18, 0)) == 5295
    assert kelvin(settings, local(day, 19, 0)) == 4795
    assert kelvin(settings, local(day, 19, 30)) == 4435
    assert kelvin(settings, local(day, 20, 0)) == 4000
    assert kelvin(settings, local(day, 21, 0)) == 4000
    assert kelvin(settings, local(day, 21, 30)) == 3810
    assert kelvin(settings, local(day, 22, 0)) == 3350
    assert kelvin(settings, local(day, 22, 30)) == 2890
    assert kelvin(settings, local(day, 23, 0)) == 2700


@pytest.mark.parametrize(
    "plateau_end",
    [dt.time(12, 0), dt.time(13, 0), dt.time(14, 30), dt.time(15, 5), dt.time(15, 30)],
)
@pytest.mark.parametrize("day", [dt.date(2026, 6, 21), dt.date(2026, 12, 21)])
def test_plateau_end_close_to_solar_noon(day, plateau_end):
    """A short afternoon squeezes the ramp but stays continuous, bounded, monotonic."""
    settings = make_settings(
        plateau_end,
        dt.time(23, 0),
        location=TOULOUSE,
        max_color_temp=5500,
        sunset_offset=dt.timedelta(hours=2),
        color_temp_fixed_plateau_kelvin=4000,
    )
    noon = dt.datetime.fromtimestamp(solar_noon(settings, day), PARIS)
    values = [(w, kelvin(settings, w)) for w in grid(day, 1, days=2)]
    assert all(2700 <= v <= 5500 for _, v in values)
    after = [v for w, v in values if noon <= w <= local(day, 23, 0)]
    assert after == sorted(after, reverse=True)
    # when the plateau end is after solar noon the target is held until then
    plateau_dt = dt.datetime.combine(day, plateau_end, PARIS)
    if plateau_dt >= noon + dt.timedelta(hours=1):
        assert kelvin(settings, plateau_dt) == 4000
        assert kelvin(settings, plateau_dt - dt.timedelta(minutes=1)) == 4000
        assert max(abs(a - b) for (_, a), (_, b) in pairwise(values)) <= 150
    else:  # less than 1 h after noon: ignored, the historical behavior
        old = make_settings(
            plateau_end,
            dt.time(23, 0),
            location=TOULOUSE,
            max_color_temp=5500,
            sunset_offset=dt.timedelta(hours=2),
        )
        for when in grid(day, 7):
            assert kelvin(settings, when) == kelvin(old, when)


@pytest.mark.parametrize("day", [dt.date(2026, 3, 29), dt.date(2026, 10, 25)])
def test_dst_wall_clock_times_hold(day):
    settings = user_case()
    assert kelvin(settings, local(day, 23, 0)) == 2700
    assert kelvin(settings, local(day, 22, 0)) == 3350


def test_polar_days():
    for day in (dt.date(2026, 6, 21), dt.date(2026, 12, 21)):
        settings = make_settings(
            dt.time(21, 0),
            dt.time(23, 0),
            location=TROMSO_LOCATION,
            timezone=OSLO,
            max_color_temp=5500,
            color_temp_fixed_plateau_kelvin=4000,
        )
        regular = make_settings(
            dt.time(21, 0),
            dt.time(23, 0),
            location=TROMSO_LOCATION,
            timezone=OSLO,
            max_color_temp=5500,
        )
        when = grid(day, 5, days=2, tz=OSLO)
        values = [kelvin(settings, w) for w in when]
        baseline = [kelvin(regular, w) for w in when]
        assert all(2700 <= value <= 5500 for value in values)

        def steepest(series):
            return max(abs(a - b) for a, b in pairwise(series))

        # the (very short, synthetic) polar days are steep by themselves; the
        # option must not add a step on top of the historical fixed evening
        assert steepest(values) <= steepest(baseline)


@pytest.mark.parametrize("rgb", ["color_temp", "rgb_color"])
@pytest.mark.parametrize("adapt_until_sleep", [True, False])
def test_sleep_and_night_options_keep_working(rgb, adapt_until_sleep):
    day = dt.date(2026, 10, 19)
    fixed = user_case(adapt_until_sleep=adapt_until_sleep, sleep_rgb_or_color_temp=rgb)
    regular = without_fixed(
        adapt_until_sleep=adapt_until_sleep,
        sleep_rgb_or_color_temp=rgb,
    )
    for when in grid(day, 15, days=2):
        assert fixed.brightness_and_color(when, True) == regular.brightness_and_color(
            when,
            True,
        )
        assert (
            fixed.brightness_and_color(when, False)["brightness_pct"]
            == regular.brightness_and_color(when, False)["brightness_pct"]
        )


# --- validation ----------------------------------------------------------------


@pytest.mark.parametrize("kelvin_value", [None, "None"])
def test_unset_is_always_valid(kelvin_value):
    validate_fixed_plateau_kelvin(kelvin_value, None, None, 2700, 5500)
    validate_fixed_plateau_kelvin(kelvin_value, "21:00:00", "23:00:00", 2700, 5500)


@pytest.mark.parametrize("kelvin_value", [2700, 4000, 5500, "4000"])
def test_valid_targets(kelvin_value):
    validate_fixed_plateau_kelvin(kelvin_value, "21:00:00", "23:00:00", 2700, 5500)


@pytest.mark.parametrize(
    ("kelvin_value", "plateau_end", "descent_end"),
    [
        (4000, None, None),  # needs the times
        (4000, "21:00:00", None),
        (4000, None, "23:00:00"),
        (4000, "None", "None"),
        (2699, "21:00:00", "23:00:00"),  # below min
        (5501, "21:00:00", "23:00:00"),  # above max
        (999, "21:00:00", "23:00:00"),
        (10001, "21:00:00", "23:00:00"),
        (0, "21:00:00", "23:00:00"),
        (-4000, "21:00:00", "23:00:00"),
        ("warm", "21:00:00", "23:00:00"),
        ("", "21:00:00", "23:00:00"),
    ],
)
def test_invalid_targets(kelvin_value, plateau_end, descent_end):
    with pytest.raises(vol.Invalid):
        validate_fixed_plateau_kelvin(
            kelvin_value,
            plateau_end,
            descent_end,
            2700,
            5500,
        )


def test_yaml_schema():
    times = {
        "color_temp_fixed_plateau_end": "21:00:00",
        "color_temp_fixed_descent_end": "23:00:00",
    }
    assert "color_temp_fixed_plateau_kelvin" not in _DOMAIN_SCHEMA({})
    assert "color_temp_fixed_plateau_kelvin" not in _DOMAIN_SCHEMA(times)
    config = _DOMAIN_SCHEMA(
        {**times, "color_temp_fixed_plateau_kelvin": 4000, "max_color_temp": 5500},
    )
    assert config["color_temp_fixed_plateau_kelvin"] == 4000
    for bad in (
        {"color_temp_fixed_plateau_kelvin": 4000},  # no times
        {**times, "color_temp_fixed_plateau_kelvin": 6000},  # above the default max
        {**times, "color_temp_fixed_plateau_kelvin": 1999},  # below the default min
        {**times, "color_temp_fixed_plateau_kelvin": 500},
        {**times, "color_temp_fixed_plateau_kelvin": "warm"},
        {
            **times,
            "color_temp_fixed_plateau_kelvin": 4100,
            "max_color_temp": 4000,
        },
    ):
        with pytest.raises(vol.Invalid):
            _DOMAIN_SCHEMA(bad)
