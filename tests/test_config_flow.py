"""Test Adaptive Lighting config flow."""

import json

import pytest
import voluptuous as vol

try:
    from probatio import to_field_list
except ImportError:
    from voluptuous_serialize import convert as to_field_list
from homeassistant.components.adaptive_lighting.const import (
    BASIC_OPTIONS,
    CONF_EXPAND_LIGHT_GROUPS,
    CONF_INITIAL_TRANSITION,
    CONF_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    DEFAULT_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON,
    DEFAULT_NAME,
    DOMAIN,
    NONE_STR,
    VALIDATION_TUPLES,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import config_validation as cv

from tests.common import MockConfigEntry

DEFAULT_DATA = {key: default for key, default, _ in VALIDATION_TUPLES}

# Split DEFAULT_DATA into basic and advanced for section-based input
BASIC_DATA = {key: value for key, value in DEFAULT_DATA.items() if key in BASIC_OPTIONS}
ADVANCED_DATA = {
    key: value for key, value in DEFAULT_DATA.items() if key not in BASIC_OPTIONS
}


def _schema_defaults(schema: vol.Schema) -> dict[str, object]:
    """Return the defaults from a voluptuous schema."""
    return {
        key.schema: key.default() if callable(key.default) else key.default
        for key in schema.schema
    }


def _advanced_section(result) -> section:
    """Return the advanced options section from a flow result."""
    advanced = result["data_schema"].schema["advanced"]
    assert isinstance(advanced, section)
    return advanced


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
    """Test updating options with collapsible sections."""
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

    # Build input with advanced options nested in "advanced" section
    advanced_data = ADVANCED_DATA.copy()
    advanced_data[CONF_INITIAL_TRANSITION] = 23
    advanced_data[CONF_EXPAND_LIGHT_GROUPS] = False
    advanced_data[CONF_SUNRISE_TIME] = NONE_STR
    advanced_data[CONF_SUNSET_TIME] = NONE_STR
    basic_data = {**BASIC_DATA, "min_brightness": 12}
    user_input = {
        **basic_data,
        "advanced": advanced_data,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Verify flattened data is saved correctly
    expected_data = {**basic_data, **advanced_data}
    for key, value in expected_data.items():
        assert result["data"][key] == value

    assert "advanced" not in result["data"]

    # Starting the flow again must load the saved flat options into both parts
    # of the sectioned form.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert _schema_defaults(result["data_schema"])["min_brightness"] == 12
    assert (
        _schema_defaults(_advanced_section(result).schema)[CONF_INITIAL_TRANSITION]
        == 23
    )


async def test_options_schema_has_each_setting_once(hass):
    """Test that basic and advanced options partition all settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME, "interval": 120, "min_brightness": 7},
        options={"min_brightness": 12},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    advanced = _advanced_section(result)

    assert advanced.options == {"collapsed": True}
    assert (
        _schema_defaults(advanced.schema)[CONF_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON]
        is DEFAULT_MANUAL_CONTROL_ON_EXTERNAL_TURN_ON
    )
    assert {key.schema for key in schema if key.schema != "advanced"} == BASIC_OPTIONS
    assert {key.schema for key in advanced.schema.schema} == set(
        DEFAULT_DATA,
    ) - BASIC_OPTIONS
    assert _schema_defaults(result["data_schema"])["interval"] == 120
    assert _schema_defaults(result["data_schema"])["min_brightness"] == 12

    serialized_schema = to_field_list(
        result["data_schema"],
        custom_serializer=cv.custom_serializer,
    )
    json.dumps(serialized_schema)
    serialized_advanced = next(
        field for field in serialized_schema if field["name"] == "advanced"
    )
    assert serialized_advanced["type"] == "expandable"
    assert serialized_advanced["expanded"] is False
    assert {field["name"] for field in serialized_advanced["schema"]} == set(
        DEFAULT_DATA,
    ) - BASIC_OPTIONS


@pytest.mark.parametrize("lights", [[], ["light.missing"]])
async def test_incorrect_options(hass, lights):
    """Test updating incorrect options in advanced section."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Build input with invalid advanced options nested in section
    advanced_data = ADVANCED_DATA.copy()
    advanced_data[CONF_SUNRISE_TIME] = "yolo"
    advanced_data[CONF_SUNSET_TIME] = "yolo"
    basic_data = {**BASIC_DATA, "min_brightness": 12, "lights": lights}
    user_input = {
        **basic_data,
        "advanced": advanced_data,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    # Should show form with errors
    assert result["type"] == FlowResultType.FORM
    expected_errors = {"base": "option_error"}
    if lights:
        expected_errors["lights"] = "entity_missing"
    assert result["errors"] == expected_errors
    assert _schema_defaults(result["data_schema"])["lights"] == lights
    assert _schema_defaults(result["data_schema"])["min_brightness"] == 12
    assert (
        _schema_defaults(_advanced_section(result).schema)[CONF_SUNRISE_TIME] == "yolo"
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


async def test_options_flow_for_yaml_import(hass):
    """Test that options flow for YAML-imported entries shows empty form.

    When a config entry is imported from YAML (source=SOURCE_IMPORT),
    the options flow should show an empty form since the user should
    modify the YAML configuration directly, not through the UI.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        source=SOURCE_IMPORT,
        options={},
    )
    entry.add_to_hass(hass)

    # For YAML imports, the switch setup requires the unique_id to be in
    # hass.data[DOMAIN]["__yaml__"], otherwise it deletes the entry.
    # This simulates what async_step_import does.
    hass.data.setdefault(DOMAIN, {}).setdefault("__yaml__", set()).add(entry.unique_id)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # For YAML imports, the options flow shows an empty form (data_schema=None)
    # This is intentional - users should modify YAML, not UI
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result.get("data_schema") is None
    assert result["description_placeholders"] == {
        "docs_url": "https://github.com/basnijholt/adaptive-lighting#readme",
        "webapp_url": "https://basnijholt.github.io/adaptive-lighting",
    }


async def test_menu_shown_when_entries_exist(hass):
    """Test that menu step is shown when existing entries exist."""
    # Create an existing entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="existing",
        data={CONF_NAME: "existing"},
        options={"min_brightness": 10},
    )
    entry.add_to_hass(hass)

    # Start a new config flow - should show menu
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "menu"


async def test_menu_create_new_instance(hass):
    """Test creating a new instance through the menu."""
    # Create an existing entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="existing",
        data={CONF_NAME: "existing"},
        options={"min_brightness": 10},
    )
    entry.add_to_hass(hass)

    # Start config flow - shows menu
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["step_id"] == "menu"

    # Choose to create new instance
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"action": "new"},
    )

    # Should show name form
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Enter name
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "new instance"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "new instance"
    # New instance should have no options (not duplicated)
    assert result["options"] == {}


async def test_menu_duplicate_instance(hass):
    """Test duplicating an existing instance through the menu."""
    # Create an existing entry with custom options
    source_options = {"min_brightness": 20, "max_brightness": 80}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="source",
        data={CONF_NAME: "source"},
        options=source_options,
    )
    entry.add_to_hass(hass)

    # Start config flow - shows menu
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["step_id"] == "menu"

    # Choose to duplicate existing entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"action": entry.entry_id},
    )

    # Should show name form
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Enter name for duplicated instance
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "duplicated"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "duplicated"
    # Duplicated instance should have copied options
    assert result["options"] == source_options
