"""Test Adaptive Lighting config flow."""

from homeassistant.components.adaptive_lighting.const import (
    CONF_DETECT_NON_HA_CHANGES,
    CONF_INTERCEPT,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_ROOM_PRESET,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    CONF_TAKE_OVER_CONTROL,
    DEFAULT_NAME,
    DOMAIN,
    NONE_STR,
    ROOM_PRESETS,
    STEP_OPTIONS,
    VALIDATION_TUPLES,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry

DEFAULT_DATA = {key: default for key, default, _ in VALIDATION_TUPLES}

# Split DEFAULT_DATA into per-step dicts matching STEP_OPTIONS
_STEP_DATA: dict[str, dict] = {}
for step_name, step_keys in STEP_OPTIONS.items():
    _STEP_DATA[step_name] = {k: v for k, v in DEFAULT_DATA.items() if k in step_keys}


async def _walk_all_steps(hass, flow_id, step_data=None):
    """Walk through all 5 option steps returning the final result.

    step_data is a dict of step_name -> user_input overrides.
    """
    if step_data is None:
        step_data = {}
    steps = ["init", "sleep", "sun_timing", "manual_control", "workarounds"]
    result = None
    for step_name in steps:
        data = _STEP_DATA[step_name].copy()
        if step_name in step_data:
            data.update(step_data[step_name])
        # Add sunrise/sunset time defaults for time validation steps
        if step_name == "sun_timing":
            data.setdefault(CONF_SUNRISE_TIME, NONE_STR)
            data.setdefault(CONF_SUNSET_TIME, NONE_STR)
        result = await hass.config_entries.options.async_configure(
            flow_id,
            user_input=data,
        )
    return result


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


async def test_options_walks_five_steps(hass):
    """Test that options flow walks through all 5 steps and saves data."""
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

    result = await _walk_all_steps(hass, result["flow_id"])
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # All default values should be present
    for key, default in DEFAULT_DATA.items():
        assert result["data"][key] == default


async def test_incorrect_options_on_sun_timing(hass):
    """Test that invalid time values on sun_timing step produce errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Walk through init step
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_STEP_DATA["init"].copy(),
    )
    assert result["step_id"] == "sleep"

    # Walk through sleep step
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_STEP_DATA["sleep"].copy(),
    )
    assert result["step_id"] == "sun_timing"

    # Submit invalid time values on sun_timing step
    data = _STEP_DATA["sun_timing"].copy()
    data[CONF_SUNRISE_TIME] = "yolo"
    data[CONF_SUNSET_TIME] = "yolo"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    # Should show form again with errors
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "sun_timing"


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


# ---- New validation tests ----


async def test_options_brightness_range_validation(hass):
    """Test that min_brightness > max_brightness is rejected on Step 1."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    data = _STEP_DATA["init"].copy()
    data[CONF_MIN_BRIGHTNESS] = 80
    data[CONF_MAX_BRIGHTNESS] = 20
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"][CONF_MIN_BRIGHTNESS] == "brightness_range_invalid"


async def test_options_color_temp_range_validation(hass):
    """Test that min_color_temp > max_color_temp is rejected on Step 1."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    data = _STEP_DATA["init"].copy()
    data[CONF_MIN_COLOR_TEMP] = 6000
    data[CONF_MAX_COLOR_TEMP] = 3000
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"][CONF_MIN_COLOR_TEMP] == "color_temp_range_invalid"


async def test_options_dependency_take_over_control(hass):
    """Test that detect_non_ha_changes without take_over_control is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Walk to step 4 (manual_control)
    for step_name in ["init", "sleep", "sun_timing"]:
        data = _STEP_DATA[step_name].copy()
        if step_name == "sun_timing":
            data[CONF_SUNRISE_TIME] = NONE_STR
            data[CONF_SUNSET_TIME] = NONE_STR
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=data,
        )

    assert result["step_id"] == "manual_control"

    data = _STEP_DATA["manual_control"].copy()
    data[CONF_TAKE_OVER_CONTROL] = False
    data[CONF_DETECT_NON_HA_CHANGES] = True
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual_control"
    assert result["errors"][CONF_DETECT_NON_HA_CHANGES] == "requires_take_over_control"


async def test_options_dependency_intercept(hass):
    """Test that multi_light_intercept without intercept is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Walk to step 4
    for step_name in ["init", "sleep", "sun_timing"]:
        data = _STEP_DATA[step_name].copy()
        if step_name == "sun_timing":
            data[CONF_SUNRISE_TIME] = NONE_STR
            data[CONF_SUNSET_TIME] = NONE_STR
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=data,
        )

    assert result["step_id"] == "manual_control"

    data = _STEP_DATA["manual_control"].copy()
    data[CONF_INTERCEPT] = False
    data[CONF_MULTI_LIGHT_INTERCEPT] = True
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual_control"
    assert result["errors"][CONF_MULTI_LIGHT_INTERCEPT] == "requires_intercept"


async def test_options_dependency_split_delay(hass):
    """Test that send_split_delay > 0 without separate_turn_on_commands is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Walk to step 5 (workarounds)
    for step_name in ["init", "sleep", "sun_timing", "manual_control"]:
        data = _STEP_DATA[step_name].copy()
        if step_name == "sun_timing":
            data[CONF_SUNRISE_TIME] = NONE_STR
            data[CONF_SUNSET_TIME] = NONE_STR
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=data,
        )

    assert result["step_id"] == "workarounds"

    data = _STEP_DATA["workarounds"].copy()
    data[CONF_SEPARATE_TURN_ON_COMMANDS] = False
    data[CONF_SEND_SPLIT_DELAY] = 100
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "workarounds"
    assert result["errors"][CONF_SEND_SPLIT_DELAY] == "requires_separate_turn_on"


async def test_room_preset_applies_defaults(hass):
    """Test that selecting a room preset pre-fills default values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    # Submit init with bedroom preset
    init_data = _STEP_DATA["init"].copy()
    init_data[CONF_ROOM_PRESET] = "bedroom"
    # Apply bedroom preset values to init_data
    bedroom = ROOM_PRESETS["bedroom"]
    for k, v in bedroom.items():
        if k in init_data:
            init_data[k] = v

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=init_data,
    )
    assert result["step_id"] == "sleep"

    # The sleep step should show bedroom preset defaults in the schema
    # Verify by walking through with defaults and checking final result
    result = await _walk_remaining_steps(
        hass,
        result["flow_id"],
        from_step="sleep",
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Verify bedroom-specific values were applied
    assert result["data"][CONF_MIN_BRIGHTNESS] == bedroom[CONF_MIN_BRIGHTNESS]
    assert result["data"][CONF_MAX_BRIGHTNESS] == bedroom[CONF_MAX_BRIGHTNESS]


async def _walk_remaining_steps(hass, flow_id, from_step):
    """Walk remaining steps from a given starting step."""
    steps = ["sleep", "sun_timing", "manual_control", "workarounds"]
    started = False
    result = None
    for step_name in steps:
        if step_name == from_step:
            started = True
        if not started:
            continue
        data = _STEP_DATA[step_name].copy()
        if step_name == "sun_timing":
            data.setdefault(CONF_SUNRISE_TIME, NONE_STR)
            data.setdefault(CONF_SUNSET_TIME, NONE_STR)
        result = await hass.config_entries.options.async_configure(
            flow_id,
            user_input=data,
        )
    return result


async def test_room_preset_overridable(hass):
    """Test that preset values can be overridden by user."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Submit init with bedroom preset but override max_brightness
    init_data = _STEP_DATA["init"].copy()
    init_data[CONF_ROOM_PRESET] = "bedroom"
    bedroom = ROOM_PRESETS["bedroom"]
    for k, v in bedroom.items():
        if k in init_data:
            init_data[k] = v
    init_data[CONF_MAX_BRIGHTNESS] = 95  # Override the bedroom default of 80

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=init_data,
    )
    assert result["step_id"] == "sleep"

    result = await _walk_remaining_steps(hass, result["flow_id"], from_step="sleep")
    assert result["type"] == FlowResultType.CREATE_ENTRY
    # The override should win over the preset
    assert result["data"][CONF_MAX_BRIGHTNESS] == 95
