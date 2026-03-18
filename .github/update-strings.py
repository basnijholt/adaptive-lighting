"""Update strings.json and en.json from const.py."""

import json
import sys
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).parent.parent))

from custom_components.adaptive_lighting import const

folder = Path("custom_components") / "adaptive_lighting"
strings_fname = folder / "strings.json"
en_fname = folder / "translations" / "en.json"
with strings_fname.open() as f:
    strings = json.load(f)

# Step option groupings
STEP_OPTIONS = {
    "init": const.STEP_INIT_OPTIONS,
    "sleep": const.STEP_SLEEP_OPTIONS,
    "sun_timing": const.STEP_SUN_TIMING_OPTIONS,
    "manual_control": const.STEP_MANUAL_CONTROL_OPTIONS,
    "workarounds": const.STEP_WORKAROUNDS_OPTIONS,
}

# Set "options" per step
for step_name, step_keys in STEP_OPTIONS.items():
    data = {}
    data_description = {}
    for k in step_keys:
        desc = const.DOCS[k]
        data[k] = k
        data_description[k] = desc
    # Add room_preset to init step
    if step_name == "init":
        data[const.CONF_ROOM_PRESET] = const.CONF_ROOM_PRESET
        data_description[const.CONF_ROOM_PRESET] = const.DOCS[const.CONF_ROOM_PRESET]
    if step_name in strings["options"]["step"]:
        strings["options"]["step"][step_name]["data"] = data
        strings["options"]["step"][step_name]["data_description"] = data_description
    else:
        strings["options"]["step"][step_name] = {
            "title": step_name,
            "description": "",
            "data": data,
            "data_description": data_description,
        }

# Set "services"
services_filename = Path("custom_components") / "adaptive_lighting" / "services.yaml"
with open(services_filename) as f:  # noqa: PTH123
    services = yaml.safe_load(f)
services_json = {}
for service_name, dct in services.items():
    services_json[service_name] = {
        "name": service_name,
        "description": dct["description"],
        "fields": {},
    }
    for field_name, field in dct["fields"].items():
        services_json[service_name]["fields"][field_name] = {
            "description": field["description"],
            "name": field_name,
        }
strings["services"] = services_json

# Write changes to strings.json
with strings_fname.open("w") as f:
    json.dump(strings, f, indent=2, ensure_ascii=False)
    f.write("\n")

# Sync changes from strings.json to en.json
with en_fname.open() as f:
    en = json.load(f)

en["config"]["step"]["user"] = strings["config"]["step"]["user"]
for step_name in STEP_OPTIONS:
    en.setdefault("options", {}).setdefault("step", {}).setdefault(step_name, {})
    src = strings["options"]["step"][step_name]
    tgt = en["options"]["step"][step_name]
    tgt["data"] = src["data"]
    tgt["data_description"] = src["data_description"]
en["services"] = services_json

with en_fname.open("w") as f:
    json.dump(en, f, indent=2, ensure_ascii=False)
    f.write("\n")
