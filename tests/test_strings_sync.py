"""Tests to verify config strings, translations, and services stay in sync.

These tests use only stdlib + direct const imports (no homeassistant dependency)
so they can run without the HA test environment.
"""

import json
from pathlib import Path

import yaml

_COMPONENT_DIR = (
    Path(__file__).parent.parent / "custom_components" / "adaptive_lighting"
)
_TRANSLATIONS_DIR = _COMPONENT_DIR / "translations"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _strings() -> dict:
    return _load_json(_COMPONENT_DIR / "strings.json")


def _en_json() -> dict:
    return _load_json(_TRANSLATIONS_DIR / "en.json")


# ---------------------------------------------------------------------------
# Test: strings.json and en.json have the same options step structure
# ---------------------------------------------------------------------------


def test_strings_and_en_json_step_keys_match():
    """The set of step names under options.step must match between files."""
    strings_steps = set(_strings()["options"]["step"].keys())
    en_steps = set(_en_json()["options"]["step"].keys())
    assert strings_steps == en_steps, (
        f"Step key mismatch — strings.json has {strings_steps - en_steps} extra, "
        f"en.json has {en_steps - strings_steps} extra"
    )


# ---------------------------------------------------------------------------
# Test: every translation file has the same step structure as strings.json
# ---------------------------------------------------------------------------


def test_translation_files_have_step_structure():
    """All translation files must define the same set of step keys."""
    expected_steps = set(_strings()["options"]["step"].keys())
    failures = []
    for path in sorted(_TRANSLATIONS_DIR.glob("*.json")):
        data = _load_json(path)
        actual_steps = set(data.get("options", {}).get("step", {}).keys())
        if actual_steps != expected_steps:
            missing = expected_steps - actual_steps
            extra = actual_steps - expected_steps
            failures.append(f"{path.name}: missing={missing}, extra={extra}")
    assert not failures, "Translation step structure mismatches:\n" + "\n".join(
        failures
    )


# ---------------------------------------------------------------------------
# Test: every translation file has the same error keys as strings.json
# ---------------------------------------------------------------------------


def test_translation_files_have_error_keys():
    """All translation files must define the same set of error keys."""
    expected_errors = set(_strings()["options"]["error"].keys())
    failures = []
    for path in sorted(_TRANSLATIONS_DIR.glob("*.json")):
        data = _load_json(path)
        actual_errors = set(data.get("options", {}).get("error", {}).keys())
        if actual_errors != expected_errors:
            missing = expected_errors - actual_errors
            extra = actual_errors - expected_errors
            failures.append(f"{path.name}: missing={missing}, extra={extra}")
    assert not failures, "Translation error key mismatches:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Test: services.yaml fields all have descriptions
# ---------------------------------------------------------------------------


def test_services_yaml_fields_have_descriptions():
    """Every field under every service in services.yaml must have a description."""
    services = _load_yaml(_COMPONENT_DIR / "services.yaml")
    missing = []
    for service_name, service_def in services.items():
        for field_name, field_def in service_def.get("fields", {}).items():
            if not field_def.get("description"):
                missing.append(f"{service_name}.{field_name}")
    assert not missing, "Services.yaml fields missing descriptions: " + ", ".join(
        missing
    )


# ---------------------------------------------------------------------------
# Test: strings.json options.error keys match what config_flow.py uses
# ---------------------------------------------------------------------------


def test_error_keys_cover_config_flow():
    """Error keys defined in strings.json must include all keys used in config_flow."""
    # These are the error keys assigned in config_flow.py.
    # If config_flow adds new error keys, this list must be updated.
    config_flow_error_keys = {
        "option_error",
        "entity_missing",
    }
    strings_error_keys = set(_strings()["options"]["error"].keys())
    missing = config_flow_error_keys - strings_error_keys
    assert not missing, f"config_flow.py uses error keys not in strings.json: {missing}"


# ---------------------------------------------------------------------------
# Test: en.json and strings.json have identical options content
# ---------------------------------------------------------------------------


def test_en_json_matches_strings_json_options():
    """en.json options section must be structurally identical to strings.json."""
    strings_options = _strings()["options"]
    en_options = _en_json()["options"]
    # Compare step keys and error keys (content may differ due to HA key refs)
    assert set(strings_options["step"].keys()) == set(en_options["step"].keys())
    assert set(strings_options["error"].keys()) == set(en_options["error"].keys())
