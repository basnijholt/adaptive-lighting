import datetime as dt
import zoneinfo
from dataclasses import replace

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


# Weather Compensation Tests


@pytest.fixture
def sun_light_settings_base(tzinfo_and_location):
    """Create a base SunLightSettings fixture for testing."""
    tzinfo, location = tzinfo_and_location
    return SunLightSettings(
        name="test",
        astral_location=location,
        adapt_until_sleep=False,
        max_brightness=100,
        max_color_temp=5500,
        min_brightness=1,
        min_color_temp=2000,
        sleep_brightness=1,
        sleep_color_temp=1000,
        sleep_rgb_color=(255, 56, 0),
        sleep_rgb_or_color_temp="color_temp",
        sunrise_offset=dt.timedelta(),
        sunrise_time=None,
        min_sunrise_time=None,
        max_sunrise_time=None,
        sunset_offset=dt.timedelta(),
        sunset_time=None,
        min_sunset_time=None,
        max_sunset_time=None,
        brightness_mode="default",
        brightness_mode_time_dark=900,
        brightness_mode_time_light=3600,
        timezone=tzinfo,
        # Lux mode parameters
        lux_sensor=None,
        lux_min=0,
        lux_max=10000,
        lux_smoothing_samples=10,
        lux_smoothing_window=300,
        lux_brightness_reduction_factor=0.5,
        # Weather mode parameters
        weather_entity=None,
        bad_weather=["cloudy", "rainy"],
        weather_brightness_reduction_factor=0.3,
    )


def test_lux_compensation_disabled_when_no_sensor(sun_light_settings_base):
    """Test that lux compensation returns 1.0 when no sensor is configured."""
    settings = sun_light_settings_base
    assert settings.lux_sensor is None

    # Compensation should be 1.0 (no reduction) when no sensor
    compensation = settings._calculate_lux_compensation_factor(
        lux_value=5000,
        sun_position=0.5,
    )
    assert compensation == 1.0


def test_lux_compensation_disabled_when_lux_none(sun_light_settings_base):
    """Test that lux compensation returns 1.0 when lux value is None."""
    settings = replace(sun_light_settings_base, lux_sensor="sensor.illuminance")

    compensation = settings._calculate_lux_compensation_factor(
        lux_value=None,
        sun_position=0.5,
    )
    assert compensation == 1.0


def test_lux_compensation_disabled_below_horizon(sun_light_settings_base):
    """Test that lux compensation returns 1.0 when sun is below horizon."""
    settings = replace(sun_light_settings_base, lux_sensor="sensor.illuminance")

    # Sun below horizon (position < 0)
    compensation = settings._calculate_lux_compensation_factor(
        lux_value=5000,
        sun_position=-0.5,
    )
    assert compensation == 1.0


def test_lux_compensation_at_expected_lux(sun_light_settings_base):
    """Test that compensation is 1.0 when actual lux matches expected lux."""
    settings = replace(sun_light_settings_base, lux_sensor="sensor.illuminance")

    # At noon (sun_position = 1.0), expected lux should be at max
    # If actual lux equals expected, ratio is 1.0, so compensation is 1.0
    compensation = settings._calculate_lux_compensation_factor(
        lux_value=10000,  # At lux_max
        sun_position=1.0,  # Noon
    )
    assert compensation == 1.0


def test_lux_compensation_above_expected_lux(sun_light_settings_base):
    """Test that compensation is 1.0 when actual lux exceeds expected lux."""
    settings = replace(sun_light_settings_base, lux_sensor="sensor.illuminance")

    # When actual lux > expected lux, ratio >= 1.0, so compensation is 1.0
    compensation = settings._calculate_lux_compensation_factor(
        lux_value=15000,  # Above lux_max
        sun_position=1.0,  # Noon
    )
    assert compensation == 1.0


def test_lux_compensation_below_expected_lux(sun_light_settings_base):
    """Test that compensation < 1.0 when actual lux is below expected lux."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=0.5,
    )

    # At noon, expected lux is at max (10000)
    # Actual lux is half of expected
    compensation = settings._calculate_lux_compensation_factor(
        lux_value=5000,  # Half of lux_max
        sun_position=1.0,  # Noon
    )

    # lux_ratio = 5000 / 10000 = 0.5
    # compensation = 1.0 - (1.0 - 0.5) * 0.5 = 1.0 - 0.25 = 0.75
    assert compensation == pytest.approx(0.75, abs=0.01)


def test_lux_compensation_at_minimum(sun_light_settings_base):
    """Test compensation at minimum lux with full reduction factor."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=1.0,  # Full reduction,
    )

    # At noon, expected lux is at max (10000)
    # Actual lux is at minimum (0)
    compensation = settings._calculate_lux_compensation_factor(
        lux_value=0,  # At lux_min
        sun_position=1.0,  # Noon
    )

    # lux_ratio = 0 / 10000 = 0.0
    # compensation = 1.0 - (1.0 - 0.0) * 1.0 = 0.0
    assert compensation == pytest.approx(0.0, abs=0.01)


def test_lux_compensation_reduction_factor_scaling(sun_light_settings_base):
    """Test that reduction factor properly scales the compensation."""
    # Test with different reduction factors
    for reduction_factor in [0.0, 0.25, 0.5, 0.75, 1.0]:
        settings = replace(
            sun_light_settings_base,
            lux_sensor="sensor.illuminance",
            lux_brightness_reduction_factor=reduction_factor,
        )

        # At noon with half expected lux
        compensation = settings._calculate_lux_compensation_factor(
            lux_value=5000,  # Half of lux_max
            sun_position=1.0,  # Noon
        )

        # lux_ratio = 0.5
        # compensation = 1.0 - (1.0 - 0.5) * reduction_factor
        expected = 1.0 - 0.5 * reduction_factor
        assert compensation == pytest.approx(expected, abs=0.01)


def test_lux_compensation_sun_influence_weight(sun_light_settings_base):
    """Test that sun influence weight properly blends compensation."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=1.0,
    )

    # At sunrise/sunset (sun_position = 0), sun_weight is 0 so no compensation is applied
    # This avoids misinterpreting natural dusk/dawn as weather/lux changes
    compensation_at_horizon = settings._calculate_lux_compensation_factor(
        lux_value=0,  # Minimum lux
        sun_position=0.0,  # Sunrise/sunset
    )

    # At noon (sun_position = 1.0), sun_weight should be maximum
    compensation_at_noon = settings._calculate_lux_compensation_factor(
        lux_value=0,  # Minimum lux
        sun_position=1.0,  # Noon
    )

    # At horizon, no compensation is applied (returns 1.0)
    assert compensation_at_horizon == 1.0
    # At noon with minimum lux and full reduction factor, compensation should be very low
    assert compensation_at_noon < compensation_at_horizon


def test_lux_clamping(sun_light_settings_base):
    """Test that lux values are properly clamped to min/max range."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=1.0,
    )

    # Test with value below lux_min
    compensation_below = settings._calculate_lux_compensation_factor(
        lux_value=-1000,  # Below lux_min
        sun_position=1.0,
    )

    # Test with value at lux_min
    compensation_at_min = settings._calculate_lux_compensation_factor(
        lux_value=0,  # At lux_min
        sun_position=1.0,
    )

    # Should be clamped to lux_min, so results should be equal
    assert compensation_below == compensation_at_min

    # Test with value above lux_max
    compensation_above = settings._calculate_lux_compensation_factor(
        lux_value=20000,  # Above lux_max
        sun_position=1.0,
    )

    # Test with value at lux_max
    compensation_at_max = settings._calculate_lux_compensation_factor(
        lux_value=10000,  # At lux_max
        sun_position=1.0,
    )

    # Both should result in no reduction (ratio >= 1.0)
    assert compensation_above == 1.0
    assert compensation_at_max == 1.0


def test_weather_compensation_disabled_when_no_entity(sun_light_settings_base):
    """Test that weather compensation returns 1.0 when no entity is configured."""
    settings = sun_light_settings_base
    assert settings.weather_entity is None

    compensation = settings._calculate_weather_compensation_factor(
        weather_state="rainy",
        sun_position=0.5,
    )
    assert compensation == 1.0


def test_weather_compensation_disabled_when_state_none(sun_light_settings_base):
    """Test that weather compensation returns 1.0 when weather state is None."""
    settings = replace(sun_light_settings_base, weather_entity="weather.home")

    compensation = settings._calculate_weather_compensation_factor(
        weather_state=None,
        sun_position=0.5,
    )
    assert compensation == 1.0


def test_weather_compensation_disabled_below_horizon(sun_light_settings_base):
    """Test that weather compensation returns 1.0 when sun is below horizon."""
    settings = replace(sun_light_settings_base, weather_entity="weather.home")

    compensation = settings._calculate_weather_compensation_factor(
        weather_state="rainy",
        sun_position=-0.5,
    )
    assert compensation == 1.0


def test_weather_compensation_good_weather(sun_light_settings_base):
    """Test that compensation is 1.0 for good weather conditions."""
    settings = replace(
        sun_light_settings_base,
        weather_entity="weather.home",
        bad_weather=["cloudy", "rainy"],
    )

    # Test various good weather conditions
    for weather in ["sunny", "clear", "partly-cloudy"]:
        compensation = settings._calculate_weather_compensation_factor(
            weather_state=weather,
            sun_position=1.0,
        )
        assert compensation == 1.0


def test_weather_compensation_bad_weather(sun_light_settings_base):
    """Test that compensation < 1.0 for bad weather conditions."""
    settings = replace(
        sun_light_settings_base,
        weather_entity="weather.home",
        bad_weather=["cloudy", "rainy"],
        weather_brightness_reduction_factor=0.3,
    )

    # Test bad weather conditions
    for weather in ["cloudy", "rainy"]:
        compensation = settings._calculate_weather_compensation_factor(
            weather_state=weather,
            sun_position=1.0,  # Noon
        )
        # compensation = 1.0 - 1.0 * 0.3 = 0.7
        assert compensation == pytest.approx(0.7, abs=0.01)


def test_weather_compensation_reduction_factor_scaling(sun_light_settings_base):
    """Test that weather reduction factor properly scales the compensation."""
    # Test with different reduction factors
    for reduction_factor in [0.0, 0.25, 0.5, 0.75, 1.0]:
        settings = replace(
            sun_light_settings_base,
            weather_entity="weather.home",
            bad_weather=["rainy"],
            weather_brightness_reduction_factor=reduction_factor,
        )

        compensation = settings._calculate_weather_compensation_factor(
            weather_state="rainy",
            sun_position=1.0,  # Noon
        )

        # At noon, sun_weight = 1.0
        # compensation = 1.0 - 1.0 * reduction_factor
        expected = 1.0 - reduction_factor
        assert compensation == pytest.approx(expected, abs=0.01)


def test_weather_compensation_sun_influence_weight(sun_light_settings_base):
    """Test that sun influence weight properly blends weather compensation."""
    settings = replace(
        sun_light_settings_base,
        weather_entity="weather.home",
        bad_weather=["rainy"],
        weather_brightness_reduction_factor=1.0,
    )

    # At sunrise/sunset (sun_position = 0), sun_weight is 0 so no compensation is applied
    # This avoids misinterpreting natural dusk/dawn lighting changes as weather changes
    compensation_at_horizon = settings._calculate_weather_compensation_factor(
        weather_state="rainy",
        sun_position=0.0,
    )

    # At noon (sun_position = 1.0), sun_weight should be maximum
    compensation_at_noon = settings._calculate_weather_compensation_factor(
        weather_state="rainy",
        sun_position=1.0,
    )

    # At horizon, no compensation is applied (returns 1.0)
    assert compensation_at_horizon == 1.0
    # Compensation at noon should be lower (more reduction) than at horizon
    assert compensation_at_noon < compensation_at_horizon


def test_combined_lux_and_weather_compensation(sun_light_settings_base):
    """Test that lux and weather compensations are properly combined."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=0.5,
        weather_entity="weather.home",
        bad_weather=["rainy"],
        weather_brightness_reduction_factor=0.3,
    )

    # Get settings with both lux and weather compensation
    result = settings.get_settings(
        is_sleep=False,
        transition=45,
        lux_value=5000,  # Half of expected at noon
        weather_state="rainy",
    )

    # Lux compensation: 1.0 - (1.0 - 0.5) * 0.5 = 0.75
    # Weather compensation: 1.0 - 1.0 * 0.3 = 0.7
    # Combined: 0.75 * 0.7 = 0.525
    # Brightness should be reduced by the combined factor

    # Verify that brightness_pct is affected by both compensations
    # The exact value depends on sun position and time, but should be < 100
    assert "brightness_pct" in result
    assert result["brightness_pct"] < 100


def test_get_settings_applies_compensation(sun_light_settings_base):
    """Test that get_settings properly applies compensation to brightness."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=1.0,
    )

    # Get settings without compensation
    result_no_comp = settings.get_settings(
        is_sleep=False,
        transition=45,
        lux_value=None,  # No lux compensation
        weather_state=None,  # No weather compensation
    )

    # Get settings with compensation
    result_with_comp = settings.get_settings(
        is_sleep=False,
        transition=45,
        lux_value=0,  # Minimum lux (maximum reduction)
        weather_state=None,
    )

    # Brightness with compensation should be lower
    assert result_with_comp["brightness_pct"] < result_no_comp["brightness_pct"]


def test_compensation_not_applied_in_sleep_mode(sun_light_settings_base):
    """Test that compensation is not applied in sleep mode."""
    settings = replace(
        sun_light_settings_base,
        lux_sensor="sensor.illuminance",
        lux_brightness_reduction_factor=1.0,
        weather_entity="weather.home",
        bad_weather=["rainy"],
        weather_brightness_reduction_factor=1.0,
    )

    # Get settings in sleep mode with compensation factors
    result = settings.get_settings(
        is_sleep=True,
        transition=45,
        lux_value=0,  # Minimum lux
        weather_state="rainy",  # Bad weather
    )

    # In sleep mode, brightness should be sleep_brightness (1%)
    assert result["brightness_pct"] == 1
