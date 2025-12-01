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

# Split DEFAULT_DATA into basic and advanced for section-based input
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
    advanced_data[CONF_SUNRISE_TIME] = NONE_STR
    advanced_data[CONF_SUNSET_TIME] = NONE_STR
    user_input = {
        **BASIC_DATA,
        "advanced": advanced_data,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Verify flattened data is saved correctly
    expected_data = {**BASIC_DATA, **advanced_data}
    for key, value in expected_data.items():
        assert result["data"][key] == value


async def test_incorrect_options(hass):
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
    user_input = {
        **BASIC_DATA,
        "advanced": advanced_data,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    # Should show form with errors
    assert result["type"] == FlowResultType.FORM
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
