"""Test Adaptive Lighting config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.adaptive_lighting.const import (
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    DEFAULT_NAME,
    DOMAIN,
    NONE_STR,
    VALIDATION_TUPLES,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry

DEFAULT_DATA = {key: default for key, default, _ in VALIDATION_TUPLES}


async def test_flow_manual_configuration(hass):
    """Test that config flow works."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["handler"] == "adaptive_lighting"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "living room"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "living room"


async def test_import_success(hass):
    """Test import step is successful."""
    data = DEFAULT_DATA.copy()
    data[CONF_NAME] = DEFAULT_NAME
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data=data,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_NAME
    for key, value in data.items():
        assert result["data"][key] == value


async def test_options(hass):
    """Test updating options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    data = DEFAULT_DATA.copy()
    data[CONF_SUNRISE_TIME] = NONE_STR
    data[CONF_SUNSET_TIME] = NONE_STR
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for key, value in data.items():
        assert result["data"][key] == value


async def test_incorrect_options(hass):
    """Test updating incorrect options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    data = DEFAULT_DATA.copy()
    data[CONF_SUNRISE_TIME] = "yolo"
    data[CONF_SUNSET_TIME] = "yolo"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )


async def test_import_twice(hass):
    """Test importing twice."""
    data = DEFAULT_DATA.copy()
    data[CONF_NAME] = DEFAULT_NAME
    for _ in range(2):
        _ = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=data,
        )


@pytest.fixture
def mock_config_entries_async_forward_entry_setup() -> Generator[AsyncMock]:
    """Mock async_forward_entry_setup."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
    ) as mock_fn:
        yield mock_fn


# TODO: Fix, broken for all supported versions
# But in ≤2024.5 it gives homeassistant.config_entries.UnknownEntry: cd69dbda65bd3f86e9a32d974cdfa23f
# and ≥2024.6 it times out


async def test_changing_options_when_using_yaml(
    hass,
    mock_config_entries_async_forward_entry_setup,
):
    """Test changing options when using YAML."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        source=SOURCE_IMPORT,
        options={},
    )
    entry.add_to_hass(hass)

    await hass.block_till_done()
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )
