"""Tests for the intensity dial on `SunLightSettings`."""

import datetime as dt
import zoneinfo

import pytest
from astral import LocationInfo
from astral.location import Location
from homeassistant.components.adaptive_lighting.color_and_brightness import (
    SunLightSettings,
)

TZINFO = zoneinfo.ZoneInfo("Europe/Amsterdam")
LOCATION = Location(
    LocationInfo(
        name="name",
        region="region",
        timezone="Europe/Amsterdam",
        latitude=52.379189,
        longitude=4.899431,
    ),
)

# Spread over a winter day so that the daylight branch, the post-sunset branch
# and solar midnight are all covered.
TIMES = [dt.datetime(2022, 1, 1, hour, tzinfo=dt.UTC) for hour in range(0, 24, 3)]

MIN_BRIGHTNESS = 20
MAX_BRIGHTNESS = 100
MIN_COLOR_TEMP = 2200
MAX_COLOR_TEMP = 5500
SLEEP_BRIGHTNESS = 1
SLEEP_COLOR_TEMP = 1000


def make_settings(**kwargs) -> SunLightSettings:
    """Build a `SunLightSettings`, overriding any field by keyword."""
    defaults = {
        "name": "test",
        "astral_observer": LOCATION.observer,
        "adapt_until_sleep": False,
        "max_brightness": MAX_BRIGHTNESS,
        "max_color_temp": MAX_COLOR_TEMP,
        "min_brightness": MIN_BRIGHTNESS,
        "min_color_temp": MIN_COLOR_TEMP,
        "sleep_brightness": SLEEP_BRIGHTNESS,
        "sleep_rgb_or_color_temp": "color_temp",
        "sleep_color_temp": SLEEP_COLOR_TEMP,
        "sleep_rgb_color": (255, 56, 0),
        "sunrise_time": None,
        "min_sunrise_time": None,
        "max_sunrise_time": None,
        "sunset_time": None,
        "min_sunset_time": None,
        "max_sunset_time": None,
        "brightness_mode_time_dark": dt.timedelta(seconds=900),
        "brightness_mode_time_light": dt.timedelta(seconds=3600),
        "timezone": TZINFO,
    }
    return SunLightSettings(**(defaults | kwargs))


def floor_values(intensity_floor: str) -> tuple[int, int]:
    """The (brightness, color temp) the dial interpolates towards."""
    if intensity_floor == "sleep":
        return SLEEP_BRIGHTNESS, SLEEP_COLOR_TEMP
    return MIN_BRIGHTNESS, MIN_COLOR_TEMP


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
@pytest.mark.parametrize("adapt_until_sleep", [True, False])
@pytest.mark.parametrize("is_sleep", [True, False])
@pytest.mark.parametrize("datetime", TIMES)
def test_full_intensity_changes_nothing(
    datetime,
    is_sleep,
    adapt_until_sleep,
    intensity_floor,
):
    """The default (100) must leave the adaptive result untouched."""
    default = make_settings(adapt_until_sleep=adapt_until_sleep)
    dialled = make_settings(
        adapt_until_sleep=adapt_until_sleep,
        intensity=100,
        intensity_floor=intensity_floor,
    )
    assert dialled.brightness_and_color(
        datetime,
        is_sleep=is_sleep,
    ) == default.brightness_and_color(datetime, is_sleep=is_sleep)


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
def test_apply_intensity_short_circuits_at_full(intensity_floor):
    """At 100 the interpolation is skipped outright, not merely a no-op."""
    settings = make_settings(intensity=100, intensity_floor=intensity_floor)
    arguments = (50.0, 3000, (255, 180, 100))
    assert (
        settings._apply_intensity(*arguments, is_sleep=False, keep_rgb=False)
        == arguments
    )


@pytest.mark.parametrize("intensity", [0, 25, 50, 75, 100])
@pytest.mark.parametrize("datetime", TIMES)
def test_sleep_mode_ignores_the_dial(datetime, intensity):
    """Sleep mode already is the sleep value, so the dial must not touch it."""
    default = make_settings()
    dialled = make_settings(intensity=intensity)
    assert dialled.brightness_and_color(
        datetime,
        is_sleep=True,
    ) == default.brightness_and_color(datetime, is_sleep=True)


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
@pytest.mark.parametrize("datetime", TIMES)
def test_zero_intensity_reaches_the_floor(datetime, intensity_floor):
    """0 must land exactly on the configured floor, at every hour."""
    settings = make_settings(intensity=0, intensity_floor=intensity_floor)
    result = settings.brightness_and_color(datetime, is_sleep=False)
    brightness, color_temp = floor_values(intensity_floor)
    assert result["brightness_pct"] == pytest.approx(brightness)
    assert result["color_temp_kelvin"] == 5 * round(color_temp / 5)


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
@pytest.mark.parametrize("datetime", TIMES)
def test_half_intensity_is_the_midpoint(datetime, intensity_floor):
    """The dial interpolates linearly between the floor and the full value."""
    full = make_settings().brightness_and_color(datetime, is_sleep=False)
    half = make_settings(
        intensity=50,
        intensity_floor=intensity_floor,
    ).brightness_and_color(datetime, is_sleep=False)
    brightness, color_temp = floor_values(intensity_floor)
    assert half["brightness_pct"] == pytest.approx(
        brightness + (full["brightness_pct"] - brightness) / 2,
    )
    expected_kelvin = round(color_temp + (full["color_temp_kelvin"] - color_temp) / 2)
    assert half["color_temp_kelvin"] == 5 * round(expected_kelvin / 5)


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
@pytest.mark.parametrize("datetime", TIMES)
def test_intensity_is_monotonic(datetime, intensity_floor):
    """Turning the dial up may never dim or cool the light."""
    results = [
        make_settings(
            intensity=intensity,
            intensity_floor=intensity_floor,
        ).brightness_and_color(datetime, is_sleep=False)
        for intensity in (0, 25, 50, 75, 100)
    ]
    brightnesses = [result["brightness_pct"] for result in results]
    kelvins = [result["color_temp_kelvin"] for result in results]
    assert brightnesses == sorted(brightnesses)
    assert kelvins == sorted(kelvins)


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
@pytest.mark.parametrize("intensity", [0, 25, 50, 75, 100])
@pytest.mark.parametrize("datetime", TIMES)
def test_results_stay_in_range(datetime, intensity, intensity_floor):
    """Whatever the dial does, the output must remain a legal light setting."""
    result = make_settings(
        intensity=intensity,
        intensity_floor=intensity_floor,
    ).brightness_and_color(datetime, is_sleep=False)
    full = make_settings().brightness_and_color(datetime, is_sleep=False)
    brightness, color_temp = floor_values(intensity_floor)
    assert brightness <= result["brightness_pct"] <= full["brightness_pct"]
    assert 0 < result["brightness_pct"] <= 100
    assert color_temp <= result["color_temp_kelvin"] <= full["color_temp_kelvin"]
    assert all(0 <= channel <= 255 for channel in result["rgb_color"])


@pytest.mark.parametrize(
    ("intensity_floor", "adapt_until_sleep", "expected"),
    [
        ("sleep", False, True),
        ("sleep", True, True),
        ("minimum", False, False),
        ("minimum", True, True),
    ],
)
def test_intensity_floor_is_sleep(intensity_floor, adapt_until_sleep, expected):
    """`adapt_until_sleep` forces the sleep floor, whatever the option says."""
    settings = make_settings(
        intensity_floor=intensity_floor,
        adapt_until_sleep=adapt_until_sleep,
    )
    assert settings.intensity_floor_is_sleep is expected


@pytest.mark.parametrize("intensity", [0, 25, 50, 75, 100])
@pytest.mark.parametrize("datetime", TIMES)
def test_adapt_until_sleep_overrides_the_floor(datetime, intensity):
    """With `adapt_until_sleep` on, `intensity_floor` makes no difference.

    The adaptive color temperature then descends below `min_color_temp` towards
    `sleep_color_temp`, so a `min_color_temp` floor would sit above the adaptive
    value and turning the dial down would make the light cooler.
    """
    results = [
        make_settings(
            intensity=intensity,
            intensity_floor=intensity_floor,
            adapt_until_sleep=True,
        ).brightness_and_color(datetime, is_sleep=False)
        for intensity_floor in ("sleep", "minimum")
    ]
    assert results[0] == results[1]


@pytest.mark.parametrize("intensity_floor", ["sleep", "minimum"])
@pytest.mark.parametrize("adapt_until_sleep", [True, False])
@pytest.mark.parametrize("datetime", TIMES)
def test_rgb_path_always_has_the_sleep_floor(
    datetime,
    adapt_until_sleep,
    intensity_floor,
):
    """`_apply_intensity` walks RGB towards `sleep_rgb_color` unconditionally.

    That is only sound because the RGB path implies `adapt_until_sleep`, which
    forces the sleep floor.
    """
    settings = make_settings(
        intensity=50,
        intensity_floor=intensity_floor,
        adapt_until_sleep=adapt_until_sleep,
        sleep_rgb_or_color_temp="rgb_color",
    )
    if settings.brightness_and_color(datetime, is_sleep=False)["force_rgb_color"]:
        assert settings.intensity_floor_is_sleep


def test_rgb_path_is_covered():
    """Guard against `test_rgb_path_always_has_the_sleep_floor` going vacuous."""
    settings = make_settings(
        adapt_until_sleep=True,
        sleep_rgb_or_color_temp="rgb_color",
    )
    assert any(
        settings.brightness_and_color(datetime, is_sleep=False)["force_rgb_color"]
        for datetime in TIMES
    )
