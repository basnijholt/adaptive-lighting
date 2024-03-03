"""Tests for Adaptive Lighting utils."""

from unittest.mock import Mock

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import Context, State

from custom_components.adaptive_lighting.adaptation_utils import (
    ServiceData,
    _create_service_call_data_iterator,
    _has_relevant_service_data_attributes,
    _remove_redundant_attributes,
    _split_service_call_data,
    prepare_adaptation_data,
)


@pytest.mark.parametrize(
    ("input_data", "expected_data_list"),
    [
        (
            {"foo": 1},
            [],
        ),
        (
            {ATTR_BRIGHTNESS: 10},
            [{ATTR_BRIGHTNESS: 10}],
        ),
        (
            {ATTR_COLOR_TEMP_KELVIN: 3500},
            [{ATTR_COLOR_TEMP_KELVIN: 3500}],
        ),
        (
            {ATTR_ENTITY_ID: "foo", ATTR_BRIGHTNESS: 10},
            [{ATTR_ENTITY_ID: "foo", ATTR_BRIGHTNESS: 10}],
        ),
        (
            {ATTR_BRIGHTNESS: 10, ATTR_COLOR_TEMP_KELVIN: 3500},
            [{ATTR_BRIGHTNESS: 10}, {ATTR_COLOR_TEMP_KELVIN: 3500}],
        ),
        (
            {ATTR_BRIGHTNESS: 10, ATTR_COLOR_TEMP_KELVIN: 3500, ATTR_TRANSITION: 2},
            [
                {ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 1},
                {ATTR_COLOR_TEMP_KELVIN: 3500, ATTR_TRANSITION: 1},
            ],
        ),
        (
            {ATTR_TRANSITION: 1},
            [],
        ),
    ],
    ids=[
        "remove irrelevant attributes",
        "brightness only yields one service call",
        "color only yields one service call",
        "include entity ID",
        "brightness and color are split into two with brightness first",
        "transition time is distributed among service calls",
        "ignore transition time without service calls",
    ],
)
async def test_split_service_call_data(input_data, expected_data_list):
    """Test splitting of service call data."""
    assert _split_service_call_data(input_data) == expected_data_list


@pytest.mark.parametrize(
    ("service_data", "state", "service_data_expected"),
    [
        (
            {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 2},
            State("light.test", STATE_ON),
            {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 2},
        ),
        (
            {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 2},
            State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 10}),
            {ATTR_ENTITY_ID: "light.test", ATTR_TRANSITION: 2},
        ),
        (
            {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 2},
            State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 11}),
            {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 2},
        ),
    ],
    ids=[
        "pass all attributes on empty state",
        "remove attributes whose values equal the state",
        "keep attributes whose values differ from the state",
    ],
)
async def test_remove_redundant_attributes(
    service_data: ServiceData,
    state: State | None,
    service_data_expected: ServiceData,
):
    """Test filtering of service data."""
    assert _remove_redundant_attributes(service_data, state) == service_data_expected


@pytest.mark.parametrize(
    ("service_data", "expected_relevant"),
    [
        (
            {ATTR_ENTITY_ID: "light.test"},
            False,
        ),
        (
            {ATTR_TRANSITION: 2},
            False,
        ),
        (
            {ATTR_BRIGHTNESS: 10},
            True,
        ),
        (
            {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10, ATTR_TRANSITION: 2},
            True,
        ),
    ],
)
async def test_has_relevant_service_data_attributes(
    service_data: ServiceData,
    expected_relevant: bool,
):
    """Test the determination of relevancy of service data"""
    assert _has_relevant_service_data_attributes(service_data) == expected_relevant


@pytest.mark.parametrize(
    ("service_datas", "filter_by_state", "service_datas_expected"),
    [
        (
            [{ATTR_ENTITY_ID: "light.test"}],
            False,
            [{ATTR_ENTITY_ID: "light.test"}],
        ),
        (
            [{ATTR_ENTITY_ID: "light.test"}, {ATTR_ENTITY_ID: "light.test2"}],
            False,
            [{ATTR_ENTITY_ID: "light.test"}, {ATTR_ENTITY_ID: "light.test2"}],
        ),
        (
            [{ATTR_ENTITY_ID: "light.test"}],
            True,
            [],
        ),
        (
            [{ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10}],
            True,
            [],
        ),
        (
            [{ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 11}],
            True,
            [{ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 11}],
        ),
        (
            [
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 11},
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 22},
            ],
            True,
            [
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 11},
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 22},
            ],
        ),
        (
            [
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 10},
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 22},
            ],
            True,
            [
                {ATTR_ENTITY_ID: "light.test", ATTR_BRIGHTNESS: 22},
            ],
        ),
    ],
    ids=[
        "single item passed through without filtering",
        "two items passed through without filtering",
        "filter removes item without relevant attributes",
        "filter removes item with relevant attribute that equals the state",
        "filter keeps item with relevant attribute that is different from state",
        "filter keeps two items with relevant attributes that are different from state",
        "filter removes item that equals state and keeps items that differs from state",
    ],
)
async def test_create_service_call_data_iterator(
    service_datas: list[ServiceData],
    filter_by_state: bool,
    service_datas_expected: list[ServiceData],
    hass_states_mock,
):
    """Test the generator function for correct enumeration and filtering."""
    generated_service_datas = [
        data
        async for data in _create_service_call_data_iterator(
            hass_states_mock,
            service_datas,
            filter_by_state,
        )
    ]

    assert generated_service_datas == service_datas_expected
    assert (
        hass_states_mock.states.get.call_count == 0
        if not filter_by_state
        else len(service_datas)
    )


@pytest.mark.parametrize(
    (
        "service_data",
        "split",
        "filter_by_state",
        "service_datas_expected",
        "sleep_time_expected",
    ),
    [
        (
            {
                ATTR_ENTITY_ID: "light.test",
                ATTR_BRIGHTNESS: 10,
                ATTR_COLOR_TEMP_KELVIN: 4000,
            },
            False,
            False,
            [
                {
                    ATTR_ENTITY_ID: "light.test",
                    ATTR_BRIGHTNESS: 10,
                    ATTR_COLOR_TEMP_KELVIN: 4000,
                },
            ],
            1.2,
        ),
        (
            {
                ATTR_ENTITY_ID: "light.test",
                ATTR_BRIGHTNESS: 10,
                ATTR_COLOR_TEMP_KELVIN: 4000,
            },
            True,
            False,
            [
                {
                    ATTR_ENTITY_ID: "light.test",
                    ATTR_BRIGHTNESS: 10,
                },
                {
                    ATTR_ENTITY_ID: "light.test",
                    ATTR_COLOR_TEMP_KELVIN: 4000,
                },
            ],
            0.7,
        ),
        (
            {
                ATTR_ENTITY_ID: "light.test",
                ATTR_BRIGHTNESS: 10,
                ATTR_COLOR_TEMP_KELVIN: 4000,
            },
            False,
            True,
            [
                {
                    ATTR_ENTITY_ID: "light.test",
                    ATTR_COLOR_TEMP_KELVIN: 4000,
                },
            ],
            1.2,
        ),
        (
            {
                ATTR_ENTITY_ID: "light.test",
                ATTR_BRIGHTNESS: 10,
                ATTR_COLOR_TEMP_KELVIN: 4000,
            },
            True,
            True,
            [
                {
                    ATTR_ENTITY_ID: "light.test",
                    ATTR_COLOR_TEMP_KELVIN: 4000,
                },
            ],
            0.7,
        ),
    ],
    ids=[
        "service data passed through",
        "service data split",
        "service data filtered",
        "service data split and filtered",
    ],
)
async def test_prepare_adaptation_data(
    hass_states_mock,
    service_data,
    split,
    filter_by_state,
    service_datas_expected,
    sleep_time_expected,
):
    """Test creation of correct service data objects."""
    data = prepare_adaptation_data(
        hass_states_mock,
        "test.entity",
        Context(id="test-id"),
        1,
        0.2,
        service_data,
        split,
        filter_by_state,
        force=False,
    )

    generated_service_datas = [item async for item in data.service_call_datas]

    assert data.entity_id == "test.entity"
    assert data.context.id == "test-id"
    assert data.sleep_time == sleep_time_expected
    assert generated_service_datas == service_datas_expected


@pytest.fixture(name="hass_states_mock")
def fixture_hass_states_mock():
    """Mocks a HA state machine which returns a mock state."""
    hass = Mock()
    hass.states.get.return_value = Mock(attributes={ATTR_BRIGHTNESS: 10})
    return hass
