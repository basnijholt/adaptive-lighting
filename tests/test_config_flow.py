"""Test Adaptive Lighting config flow."""

from homeassistant.components.adaptive_lighting.const import (
    CONF_DETECT_NON_HA_CHANGES,
    CONF_INTERCEPT,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SUNRISE_TIME,
    CONF_SUNSET_TIME,
    CONF_TAKE_OVER_CONTROL,
    DEFAULT_NAME,
    DOMAIN,
    NONE_STR,
    STEP_INIT_OPTIONS,
    STEP_MANUAL_CONTROL_OPTIONS,
    STEP_SLEEP_OPTIONS,
    STEP_SUN_TIMING_OPTIONS,
    STEP_WORKAROUNDS_OPTIONS,
    VALIDATION_TUPLES,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry

VALIDATION_DEFAULTS = {key: default for key, default, _ in VALIDATION_TUPLES}

INIT_DATA = {k: VALIDATION_DEFAULTS[k] for k in STEP_INIT_OPTIONS}
INIT_DATA["room_preset"] = "custom"

SLEEP_DATA = {k: VALIDATION_DEFAULTS[k] for k in STEP_SLEEP_OPTIONS}

SUN_TIMING_DATA = {k: VALIDATION_DEFAULTS[k] for k in STEP_SUN_TIMING_OPTIONS}
SUN_TIMING_DATA[CONF_SUNRISE_TIME] = NONE_STR
SUN_TIMING_DATA[CONF_SUNSET_TIME] = NONE_STR

MANUAL_CONTROL_DATA = {k: VALIDATION_DEFAULTS[k] for k in STEP_MANUAL_CONTROL_OPTIONS}

WORKAROUNDS_DATA = {k: VALIDATION_DEFAULTS[k] for k in STEP_WORKAROUNDS_OPTIONS}


async def walk_options_flow(
    hass,
    entry_id,
    init_data=None,
    sleep_data=None,
    sun_timing_data=None,
    manual_control_data=None,
    workarounds_data=None,
):
    """Walk through all 5 steps of the options flow."""
    _init = init_data if init_data is not None else INIT_DATA.copy()
    _sleep = sleep_data if sleep_data is not None else SLEEP_DATA.copy()
    _sun = sun_timing_data if sun_timing_data is not None else SUN_TIMING_DATA.copy()
    _manual = (
        manual_control_data
        if manual_control_data is not None
        else MANUAL_CONTROL_DATA.copy()
    )
    _work = (
        workarounds_data if workarounds_data is not None else WORKAROUNDS_DATA.copy()
    )

    result = await hass.config_entries.options.async_init(entry_id)
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_init,
    )
    assert result["step_id"] == "sleep"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_sleep,
    )
    assert result["step_id"] == "sun_timing"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_sun,
    )
    assert result["step_id"] == "manual_control"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_manual,
    )
    assert result["step_id"] == "workarounds"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_work,
    )
    return result


# === ConfigFlow tests (unchanged) ===


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
    data = VALIDATION_DEFAULTS.copy()
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


async def test_import_twice(hass):
    """Test importing twice."""
    data = VALIDATION_DEFAULTS.copy()
    data[CONF_NAME] = DEFAULT_NAME
    for _ in range(2):
        _ = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "import"},
            data=data,
        )


async def test_menu_shown_when_entries_exist(hass):
    """Test that menu step is shown when existing entries exist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="existing",
        data={CONF_NAME: "existing"},
        options={"min_brightness": 10},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "menu"


async def test_menu_create_new_instance(hass):
    """Test creating a new instance through the menu."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="existing",
        data={CONF_NAME: "existing"},
        options={"min_brightness": 10},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["step_id"] == "menu"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"action": "new"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "new instance"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "new instance"
    assert result["options"] == {}


async def test_menu_duplicate_instance(hass):
    """Test duplicating an existing instance through the menu."""
    source_options = {"min_brightness": 20, "max_brightness": 80}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="source",
        data={CONF_NAME: "source"},
        options=source_options,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["step_id"] == "menu"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"action": entry.entry_id},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "duplicated"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "duplicated"
    assert result["options"] == source_options


# === OptionsFlow tests (rewritten for 5-step wizard) ===


async def test_options(hass):
    """Test updating options through all 5 steps."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await walk_options_flow(hass, entry.entry_id)
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_incorrect_options(hass):
    """Test invalid options at the sun_timing step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    # Walk to sun_timing step
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=INIT_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SLEEP_DATA.copy(),
    )
    assert result["step_id"] == "sun_timing"

    # Submit invalid data
    bad_sun_data = SUN_TIMING_DATA.copy()
    bad_sun_data[CONF_SUNRISE_TIME] = "yolo"
    bad_sun_data[CONF_SUNSET_TIME] = "yolo"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=bad_sun_data,
    )
    # Should stay on sun_timing with errors
    assert result["step_id"] == "sun_timing"


async def test_options_flow_for_yaml_import(hass):
    """Test that options flow for YAML-imported entries shows empty form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        source=SOURCE_IMPORT,
        options={},
    )
    entry.add_to_hass(hass)

    hass.data.setdefault(DOMAIN, {}).setdefault("__yaml__", set()).add(entry.unique_id)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result.get("data_schema") is None


# === Room preset tests ===


async def test_room_preset_bedroom(hass):
    """Test bedroom preset applies correct defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    init_data = INIT_DATA.copy()
    init_data["room_preset"] = "bedroom"
    result = await walk_options_flow(hass, entry.entry_id, init_data=init_data)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["max_brightness"] == 80
    assert result["data"]["min_color_temp"] == 2000
    assert result["data"]["max_color_temp"] == 4000


async def test_room_preset_custom(hass):
    """Test custom preset does not override values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    init_data = INIT_DATA.copy()
    init_data["room_preset"] = "custom"
    init_data["max_brightness"] = 75
    result = await walk_options_flow(hass, entry.entry_id, init_data=init_data)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["max_brightness"] == 75


# === Dependency validation tests ===


async def test_dependency_detect_non_ha(hass):
    """Test detect_non_ha_changes requires take_over_control."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=INIT_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SLEEP_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SUN_TIMING_DATA.copy(),
    )
    assert result["step_id"] == "manual_control"

    bad_manual = MANUAL_CONTROL_DATA.copy()
    bad_manual[CONF_DETECT_NON_HA_CHANGES] = True
    bad_manual[CONF_TAKE_OVER_CONTROL] = False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=bad_manual,
    )
    assert result["step_id"] == "manual_control"
    assert (
        result["errors"].get(CONF_DETECT_NON_HA_CHANGES) == "requires_take_over_control"
    )


async def test_dependency_multi_light_intercept(hass):
    """Test multi_light_intercept requires intercept."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=INIT_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SLEEP_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SUN_TIMING_DATA.copy(),
    )

    bad_manual = MANUAL_CONTROL_DATA.copy()
    bad_manual[CONF_MULTI_LIGHT_INTERCEPT] = True
    bad_manual[CONF_INTERCEPT] = False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=bad_manual,
    )
    assert result["step_id"] == "manual_control"
    assert result["errors"].get(CONF_MULTI_LIGHT_INTERCEPT) == "requires_intercept"


async def test_dependency_send_split_delay(hass):
    """Test send_split_delay requires separate_turn_on_commands."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=INIT_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SLEEP_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=SUN_TIMING_DATA.copy(),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=MANUAL_CONTROL_DATA.copy(),
    )
    assert result["step_id"] == "workarounds"

    bad_workarounds = WORKAROUNDS_DATA.copy()
    bad_workarounds[CONF_SEND_SPLIT_DELAY] = 100
    bad_workarounds[CONF_SEPARATE_TURN_ON_COMMANDS] = False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=bad_workarounds,
    )
    assert result["step_id"] == "workarounds"
    assert result["errors"].get(CONF_SEND_SPLIT_DELAY) == "requires_separate_turn_on"


# === Range validation tests ===


async def test_brightness_range_validation(hass):
    """Test min_brightness > max_brightness is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    bad_init = INIT_DATA.copy()
    bad_init["min_brightness"] = 80
    bad_init["max_brightness"] = 20
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=bad_init,
    )
    assert result["step_id"] == "init"
    assert result["errors"].get("min_brightness") == "brightness_range_invalid"


# === Full wizard test ===


async def test_full_wizard_non_defaults(hass):
    """Test full wizard with non-default values preserves all settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    init = INIT_DATA.copy()
    init["min_brightness"] = 10
    init["max_brightness"] = 90

    sleep = SLEEP_DATA.copy()
    sleep["sleep_brightness"] = 5

    sun = SUN_TIMING_DATA.copy()
    sun["sunrise_offset"] = 300

    manual = MANUAL_CONTROL_DATA.copy()
    manual["autoreset_control_seconds"] = 3600

    work = WORKAROUNDS_DATA.copy()
    work["skip_redundant_commands"] = True

    result = await walk_options_flow(
        hass,
        entry.entry_id,
        init_data=init,
        sleep_data=sleep,
        sun_timing_data=sun,
        manual_control_data=manual,
        workarounds_data=work,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["min_brightness"] == 10
    assert result["data"]["max_brightness"] == 90
    assert result["data"]["sleep_brightness"] == 5
    assert result["data"]["sunrise_offset"] == 300
    assert result["data"]["autoreset_control_seconds"] == 3600
    assert result["data"]["skip_redundant_commands"] is True
