"""Test Adaptive Lighting config flow."""

from homeassistant.components.adaptive_lighting.const import (
    BASIC_OPTIONS,
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

# Split DEFAULT_DATA into basic and advanced options
BASIC_DATA = {key: value for key, value in DEFAULT_DATA.items() if key in BASIC_OPTIONS}
ADVANCED_DATA = {
    key: value for key, value in DEFAULT_DATA.items() if key not in BASIC_OPTIONS
}


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
    """Test updating options with multi-step flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    # Step 1: Init with basic options
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Submit basic options - this should show the menu
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=BASIC_DATA.copy(),
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"

    # Choose to go to advanced options
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "advanced"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced"

    # Submit advanced options
    advanced_data = ADVANCED_DATA.copy()
    advanced_data[CONF_SUNRISE_TIME] = NONE_STR
    advanced_data[CONF_SUNSET_TIME] = NONE_STR
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=advanced_data,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Verify all data is saved (basic + advanced)
    expected_data = {**BASIC_DATA, **advanced_data}
    for key, value in expected_data.items():
        assert result["data"][key] == value


async def test_options_finish_without_advanced(hass):
    """Test updating options and finishing without advanced step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    # Step 1: Init with basic options
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Submit basic options - this should show the menu
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=BASIC_DATA.copy(),
    )
    assert result["type"] == FlowResultType.MENU

    # Choose to finish (skip advanced options)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "finish"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Verify only basic data is saved
    for key, value in BASIC_DATA.items():
        assert result["data"][key] == value


async def test_incorrect_options(hass):
    """Test updating incorrect options in advanced step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    # Step 1: Init with basic options
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=BASIC_DATA.copy(),
    )
    assert result["type"] == FlowResultType.MENU

    # Choose to go to advanced options
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "advanced"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced"

    # Submit invalid advanced options
    advanced_data = ADVANCED_DATA.copy()
    advanced_data[CONF_SUNRISE_TIME] = "yolo"
    advanced_data[CONF_SUNSET_TIME] = "yolo"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=advanced_data,
    )
    # Should show form again with errors
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced"
    assert result["errors"] == {"base": "option_error"}


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
