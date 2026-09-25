"""Config flow tests for the CDiT Adaptive Lighting fork.

Covers spec/options-flow/spec.md requirements R1, R2, R3, R5, R6, R7.
"""

from __future__ import annotations

from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    NumberSelector,
    NumberSelectorMode,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_lighting.config_flow import (
    SECTION_ADVANCED,
    SECTION_AMBIENT_LUX,
    SECTION_DAYTIME,
    SECTION_DIAGNOSTICS,
    SECTION_LIGHT_CONTROL,
    SECTION_SUN,
    SECTION_TARGETS,
    _build_options_schema,
)
from custom_components.adaptive_lighting.const import (
    CONF_INCLUDE_CONFIG_IN_ATTRIBUTES,
    CONF_INTERCEPT,
    CONF_INTERVAL,
    CONF_LIGHTS,
    CONF_LUX_SENSOR,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_COLOR_TEMP,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_COLOR_TEMP,
    CONF_MULTI_LIGHT_INTERCEPT,
    CONF_PREFER_RGB_COLOR,
    CONF_SEND_SPLIT_DELAY,
    CONF_SEPARATE_TURN_ON_COMMANDS,
    CONF_SKIP_REDUNDANT_COMMANDS,
    CONF_SUNRISE_ENTITY,
    CONF_SUNSET_ENTITY,
    CONF_TARGET_LUX,
    DEFAULT_NAME,
    DEFAULT_SUNRISE_ENTITY,
    DEFAULT_SUNSET_ENTITY,
    DOMAIN,
)

EXPECTED_SECTIONS = (
    SECTION_TARGETS,
    SECTION_DAYTIME,
    SECTION_SUN,
    SECTION_AMBIENT_LUX,
    SECTION_LIGHT_CONTROL,
    SECTION_ADVANCED,
    SECTION_DIAGNOSTICS,
)

EXPECTED_SECTION_FIELDS: dict[str, set[str]] = {
    SECTION_TARGETS: {CONF_LIGHTS},
    SECTION_DAYTIME: {
        CONF_MIN_BRIGHTNESS,
        CONF_MAX_BRIGHTNESS,
        CONF_MIN_COLOR_TEMP,
        CONF_MAX_COLOR_TEMP,
        CONF_PREFER_RGB_COLOR,
    },
    SECTION_SUN: {CONF_SUNRISE_ENTITY, CONF_SUNSET_ENTITY},
    SECTION_AMBIENT_LUX: {CONF_LUX_SENSOR},
    SECTION_LIGHT_CONTROL: {CONF_INTERCEPT, CONF_MULTI_LIGHT_INTERCEPT},
    SECTION_ADVANCED: {
        CONF_INTERVAL,
        "transition",
        "initial_transition",
        "adapt_delay",
        CONF_SEPARATE_TURN_ON_COMMANDS,
        CONF_SKIP_REDUNDANT_COMMANDS,
    },
    SECTION_DIAGNOSTICS: {CONF_INCLUDE_CONFIG_IN_ATTRIBUTES},
}


def _section_inner_keys(schema_section) -> set[str]:
    """Return the field names inside a sectioned schema entry."""
    # `section()` returns a special wrapper object whose `schema` attribute
    # holds the inner vol.Schema. Each key is a vol.Marker (Required/Optional)
    # whose `schema` is the field name string.
    inner = schema_section.schema.schema  # vol.Schema → underlying dict
    return {str(k.schema) if hasattr(k, "schema") else str(k) for k in inner}


# ---------------------------------------------------------------------------
# R1: section layout
# ---------------------------------------------------------------------------


def test_options_schema_has_all_seven_sections_in_order() -> None:
    """R1: the options form returns the seven named sections in order."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    keys = [
        k.schema if hasattr(k, "schema") else k
        for k in schema.schema  # type: ignore[attr-defined]
    ]
    assert tuple(keys) == EXPECTED_SECTIONS


def test_each_section_contains_only_its_specified_fields() -> None:
    """R1 scenario 2: every field appears in exactly one section, matching
    the layout table.
    """
    schema = _build_options_schema(
        {},
        show_send_split_delay=True,
        show_target_lux=False,
    )
    for marker in schema.schema:  # type: ignore[attr-defined]
        section_id = marker.schema if hasattr(marker, "schema") else marker
        inner_fields = _section_inner_keys(schema.schema[marker])  # type: ignore[index]
        expected = EXPECTED_SECTION_FIELDS[section_id].copy()
        # Advanced gains send_split_delay when its driver is true.
        if section_id == SECTION_ADVANCED:
            expected.add(CONF_SEND_SPLIT_DELAY)
        assert (
            inner_fields == expected
        ), f"section {section_id}: expected {expected}, got {inner_fields}"


# ---------------------------------------------------------------------------
# R2: conditional visibility of send_split_delay
# ---------------------------------------------------------------------------


def test_send_split_delay_hidden_when_driver_false() -> None:
    """R2: send_split_delay is absent when separate_turn_on_commands=False."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    advanced_marker = next(
        m
        for m in schema.schema  # type: ignore[attr-defined]
        if (m.schema if hasattr(m, "schema") else m) == SECTION_ADVANCED
    )
    advanced = schema.schema[advanced_marker]  # type: ignore[index]
    assert CONF_SEND_SPLIT_DELAY not in _section_inner_keys(advanced)


def test_send_split_delay_visible_when_driver_true() -> None:
    """R2: send_split_delay appears when separate_turn_on_commands=True."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=True,
        show_target_lux=False,
    )
    advanced_marker = next(
        m
        for m in schema.schema  # type: ignore[attr-defined]
        if (m.schema if hasattr(m, "schema") else m) == SECTION_ADVANCED
    )
    advanced = schema.schema[advanced_marker]  # type: ignore[index]
    assert CONF_SEND_SPLIT_DELAY in _section_inner_keys(advanced)


# ---------------------------------------------------------------------------
# R3: entity-driven sun timing
# ---------------------------------------------------------------------------


def test_default_sunrise_and_sunset_entities() -> None:
    """R3: default entities point at the built-in sun.sun sensors."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    sun_marker = next(
        m
        for m in schema.schema  # type: ignore[attr-defined]
        if (m.schema if hasattr(m, "schema") else m) == SECTION_SUN
    )
    sun_inner = schema.schema[sun_marker].schema.schema  # type: ignore[index]
    defaults = {
        (k.schema if hasattr(k, "schema") else k): k.default()
        for k in sun_inner
        if hasattr(k, "default")
    }
    assert (
        defaults[CONF_SUNRISE_ENTITY]
        == DEFAULT_SUNRISE_ENTITY
        == "sensor.sun_next_rising"
    )
    assert (
        defaults[CONF_SUNSET_ENTITY]
        == DEFAULT_SUNSET_ENTITY
        == "sensor.sun_next_setting"
    )


def test_sun_entity_selectors_are_strict_timestamp_sensors() -> None:
    """R3 + D14: both sun-event entity selectors filter by domain=sensor and
    device_class=timestamp.
    """
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    sun_marker = next(
        m
        for m in schema.schema  # type: ignore[attr-defined]
        if (m.schema if hasattr(m, "schema") else m) == SECTION_SUN
    )
    sun_inner = schema.schema[sun_marker].schema.schema  # type: ignore[index]
    for k, v in sun_inner.items():
        field_name = k.schema if hasattr(k, "schema") else k
        if field_name in (CONF_SUNRISE_ENTITY, CONF_SUNSET_ENTITY):
            assert isinstance(v, EntitySelector)
            cfg = v.config
            # HA normalizes `domain="sensor"` to `domain=["sensor"]` and
            # `device_class="timestamp"` to `device_class=["timestamp"]`.
            domain = cfg.get("domain")
            device_class = cfg.get("device_class")
            assert "sensor" in (domain if isinstance(domain, list) else [domain])
            assert "timestamp" in (
                device_class if isinstance(device_class, list) else [device_class]
            )


# ---------------------------------------------------------------------------
# R5: native HA selectors
# ---------------------------------------------------------------------------


def test_brightness_uses_slider_number_selector() -> None:
    """R5: brightness fields are NumberSelectors with slider mode, 1-100 %, step 1."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    daytime_marker = next(
        m
        for m in schema.schema  # type: ignore[attr-defined]
        if (m.schema if hasattr(m, "schema") else m) == SECTION_DAYTIME
    )
    inner = schema.schema[daytime_marker].schema.schema  # type: ignore[index]
    for k, v in inner.items():
        field_name = k.schema if hasattr(k, "schema") else k
        if field_name in (CONF_MIN_BRIGHTNESS, CONF_MAX_BRIGHTNESS):
            assert isinstance(v, NumberSelector)
            cfg = v.config
            assert cfg["min"] == 1
            assert cfg["max"] == 100
            assert cfg["step"] == 1
            assert cfg["unit_of_measurement"] == "%"
            assert cfg["mode"] == NumberSelectorMode.SLIDER


def test_color_temp_uses_box_number_selector() -> None:
    """R5: color-temp fields are NumberSelectors, 1000-10000 K, step 100."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    daytime_marker = next(
        m
        for m in schema.schema  # type: ignore[attr-defined]
        if (m.schema if hasattr(m, "schema") else m) == SECTION_DAYTIME
    )
    inner = schema.schema[daytime_marker].schema.schema  # type: ignore[index]
    for k, v in inner.items():
        field_name = k.schema if hasattr(k, "schema") else k
        if field_name in (CONF_MIN_COLOR_TEMP, CONF_MAX_COLOR_TEMP):
            assert isinstance(v, NumberSelector)
            cfg = v.config
            assert cfg["min"] == 1000
            assert cfg["max"] == 10000
            assert cfg["step"] == 100
            assert cfg["unit_of_measurement"] == "K"


def test_booleans_use_boolean_selector() -> None:
    """R5: every boolean field renders as a BooleanSelector."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=True,
        show_target_lux=False,
    )
    boolean_fields = {
        CONF_PREFER_RGB_COLOR,
        CONF_INTERCEPT,
        CONF_MULTI_LIGHT_INTERCEPT,
        CONF_SEPARATE_TURN_ON_COMMANDS,
        CONF_SKIP_REDUNDANT_COMMANDS,
        CONF_INCLUDE_CONFIG_IN_ATTRIBUTES,
    }
    for marker in schema.schema:  # type: ignore[attr-defined]
        section = schema.schema[marker]  # type: ignore[index]
        for k, v in section.schema.schema.items():
            field_name = k.schema if hasattr(k, "schema") else k
            if field_name in boolean_fields:
                assert isinstance(
                    v,
                    BooleanSelector,
                ), f"{field_name} is {type(v).__name__}, expected BooleanSelector"


# ---------------------------------------------------------------------------
# Full flow integration tests (R6, R7)
# ---------------------------------------------------------------------------


async def test_user_flow_creates_entry(hass) -> None:
    """The user step creates an entry with the given name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_NAME: "living room"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "living room"


async def test_options_flow_renders_sectioned_schema(hass) -> None:
    """R1 + R6: opening options on a UI-managed entry shows the sectioned form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
        version=2,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # The form's data_schema contains the seven section keys.
    schema_keys = [
        (k.schema if hasattr(k, "schema") else k)
        for k in result["data_schema"].schema  # type: ignore[union-attr,attr-defined]
    ]
    assert tuple(schema_keys) == EXPECTED_SECTIONS


# ---------------------------------------------------------------------------
# Lux: conditional target_lux visibility
# ---------------------------------------------------------------------------


def test_target_lux_hidden_when_no_sensor() -> None:
    """target_lux should not appear when lux_sensor is empty."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    lux_marker = next(
        m
        for m in schema.schema
        if (m.schema if hasattr(m, "schema") else m) == SECTION_AMBIENT_LUX
    )
    lux_fields = _section_inner_keys(schema.schema[lux_marker])
    assert CONF_LUX_SENSOR in lux_fields
    assert CONF_TARGET_LUX not in lux_fields


def test_target_lux_visible_when_sensor_set() -> None:
    """target_lux should appear when lux_sensor is populated."""
    schema = _build_options_schema(
        {CONF_LUX_SENSOR: "sensor.office_lux"},
        show_send_split_delay=False,
        show_target_lux=True,
    )
    lux_marker = next(
        m
        for m in schema.schema
        if (m.schema if hasattr(m, "schema") else m) == SECTION_AMBIENT_LUX
    )
    lux_fields = _section_inner_keys(schema.schema[lux_marker])
    assert CONF_LUX_SENSOR in lux_fields
    assert CONF_TARGET_LUX in lux_fields


def test_lux_sensor_selector_filters_to_illuminance() -> None:
    """lux_sensor entity selector should filter to device_class=illuminance."""
    schema = _build_options_schema(
        {},
        show_send_split_delay=False,
        show_target_lux=False,
    )
    lux_marker = next(
        m
        for m in schema.schema
        if (m.schema if hasattr(m, "schema") else m) == SECTION_AMBIENT_LUX
    )
    lux_inner = schema.schema[lux_marker].schema.schema
    for k, v in lux_inner.items():
        field_name = k.schema if hasattr(k, "schema") else k
        if field_name == CONF_LUX_SENSOR:
            assert isinstance(v, EntitySelector)
            cfg = v.config
            domain = cfg.get("domain")
            device_class = cfg.get("device_class")
            assert "sensor" in (domain if isinstance(domain, list) else [domain])
            assert "illuminance" in (
                device_class if isinstance(device_class, list) else [device_class]
            )


def test_target_lux_selector_uses_box_mode() -> None:
    """target_lux should be a NumberSelector in BOX mode, range 1-10000, unit lx."""
    schema = _build_options_schema(
        {CONF_LUX_SENSOR: "sensor.office_lux"},
        show_send_split_delay=False,
        show_target_lux=True,
    )
    lux_marker = next(
        m
        for m in schema.schema
        if (m.schema if hasattr(m, "schema") else m) == SECTION_AMBIENT_LUX
    )
    lux_inner = schema.schema[lux_marker].schema.schema
    for k, v in lux_inner.items():
        field_name = k.schema if hasattr(k, "schema") else k
        if field_name == CONF_TARGET_LUX:
            assert isinstance(v, NumberSelector)
            cfg = v.config
            assert cfg["min"] == 1
            assert cfg["max"] == 10000
            assert cfg["step"] == 10
            assert cfg["unit_of_measurement"] == "lx"
            assert cfg["mode"] == NumberSelectorMode.BOX


async def test_options_flow_shows_lux_reading_placeholder(hass) -> None:
    """The options flow should include description_placeholders with current_lux."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
        version=2,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert "description_placeholders" in result
    assert "current_lux" in result["description_placeholders"]


# ---------------------------------------------------------------------------
# Same-session re-render of conditional fields (options-flow conditionals)
# ---------------------------------------------------------------------------


def _full_section_payload() -> dict:
    """A schema-valid sectioned options submission (conditional fields off)."""
    return {
        SECTION_TARGETS: {CONF_LIGHTS: []},
        SECTION_DAYTIME: {
            CONF_MIN_BRIGHTNESS: 5,
            CONF_MAX_BRIGHTNESS: 100,
            CONF_MIN_COLOR_TEMP: 2000,
            CONF_MAX_COLOR_TEMP: 5500,
            CONF_PREFER_RGB_COLOR: False,
        },
        SECTION_SUN: {
            CONF_SUNRISE_ENTITY: DEFAULT_SUNRISE_ENTITY,
            CONF_SUNSET_ENTITY: DEFAULT_SUNSET_ENTITY,
        },
        # Omit lux_sensor entirely: an EntitySelector rejects an explicit "",
        # so the empty case is expressed by absence (the vol.Optional default).
        SECTION_AMBIENT_LUX: {},
        SECTION_LIGHT_CONTROL: {
            CONF_INTERCEPT: True,
            CONF_MULTI_LIGHT_INTERCEPT: False,
        },
        SECTION_ADVANCED: {
            CONF_INTERVAL: 90,
            "transition": 45,
            "initial_transition": 1,
            "adapt_delay": 0,
            CONF_SEPARATE_TURN_ON_COMMANDS: False,
            CONF_SKIP_REDUNDANT_COMMANDS: True,
        },
        SECTION_DIAGNOSTICS: {CONF_INCLUDE_CONFIG_IN_ATTRIBUTES: False},
    }


def _result_section_fields(result, section_name: str) -> set[str]:
    """Extract a section's field names from a rendered flow result schema."""
    schema = result["data_schema"].schema
    marker = next(
        m for m in schema if (m.schema if hasattr(m, "schema") else m) == section_name
    )
    return _section_inner_keys(schema[marker])


async def _open_options(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_NAME,
        data={CONF_NAME: DEFAULT_NAME},
        options={},
        version=2,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_options_flow_saves_when_no_conditional_pending(hass) -> None:
    """Regression: a submission with no driver enabled still saves directly."""
    result = await _open_options(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_full_section_payload(),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_target_lux_revealed_same_session_when_sensor_selected(hass) -> None:
    """options-flow conditionals: picking a lux sensor re-renders the form with
    target_lux present, in the SAME session (no save-and-reopen round-trip).
    """
    result = await _open_options(hass)
    assert CONF_TARGET_LUX not in _result_section_fields(result, SECTION_AMBIENT_LUX)

    payload = _full_section_payload()
    payload[SECTION_AMBIENT_LUX] = {CONF_LUX_SENSOR: "sensor.office_lux"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=payload,
    )
    # Must re-render rather than save, and now expose target_lux.
    assert result["type"] is FlowResultType.FORM
    assert CONF_TARGET_LUX in _result_section_fields(result, SECTION_AMBIENT_LUX)


async def test_target_lux_saved_on_second_submit_after_reveal(hass) -> None:
    """After the reveal re-render, submitting with target_lux set saves."""
    result = await _open_options(hass)
    payload = _full_section_payload()
    payload[SECTION_AMBIENT_LUX] = {CONF_LUX_SENSOR: "sensor.office_lux"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=payload,
    )
    assert result["type"] is FlowResultType.FORM  # revealed

    payload[SECTION_AMBIENT_LUX] = {
        CONF_LUX_SENSOR: "sensor.office_lux",
        CONF_TARGET_LUX: 500,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=payload,
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LUX_SENSOR] == "sensor.office_lux"
    assert result["data"][CONF_TARGET_LUX] == 500
