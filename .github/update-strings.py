"""Update strings.json and en.json from const.py."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import homeassistant.helpers.config_validation as cv
import yaml

sys.path.append(str(Path(__file__).parent.parent))

from custom_components.adaptive_lighting import const

folder = Path("custom_components") / "adaptive_lighting"
strings_fname = folder / "strings.json"
en_fname = folder / "translations" / "en.json"
translation_fnames = (folder / "translations").glob("*.json")
with strings_fname.open() as f:
    strings = json.load(f)


def _partition_options(values):
    """Partition option translations into basic and advanced dictionaries."""
    basic = {
        key: values[key]
        for key, _, _ in const.VALIDATION_TUPLES
        if key in const.BASIC_OPTIONS and key in values
    }
    advanced = {
        key: values[key]
        for key, _, _ in const.VALIDATION_TUPLES
        if key not in const.BASIC_OPTIONS and key in values
    }
    return basic, advanced


def _migrate_translation_options(step):
    """Move translated advanced options under the advanced section."""
    sections = step.setdefault("sections", {})
    advanced = sections.setdefault("advanced", {})
    for key in ("data", "data_description"):
        values = {**advanced.get(key, {}), **step.get(key, {})}
        step[key], advanced[key] = _partition_options(values)


# Set "options"
data = {}
data_description = {}
for k, _, typ in const.VALIDATION_TUPLES:
    desc = const.DOCS[k]
    if len(desc) > 40 and typ not in (bool, cv.entity_ids):
        data[k] = k
        data_description[k] = desc
    else:
        data[k] = f"{k}: {desc}"
basic_data, advanced_data = _partition_options(data)
basic_descriptions, advanced_descriptions = _partition_options(data_description)
options_step = strings["options"]["step"]["init"]
options_step["data"] = basic_data
options_step["data_description"] = basic_descriptions
options_step["sections"] = {
    "advanced": {
        "name": "Advanced settings",
        "description": "Additional settings for fine-tuning Adaptive Lighting.",
        "data": advanced_data,
        "data_description": advanced_descriptions,
    },
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
en["options"]["step"]["init"] = deepcopy(options_step)
en["services"] = services_json

with en_fname.open("w") as f:
    json.dump(en, f, indent=2, ensure_ascii=False)
    f.write("\n")

# Keep translated labels and descriptions when moving advanced options into a section.
for translation_fname in translation_fnames:
    if translation_fname == en_fname:
        continue
    with translation_fname.open() as f:
        translation = json.load(f)
    if "options" not in translation:
        continue
    _migrate_translation_options(translation["options"]["step"]["init"])
    with translation_fname.open("w") as f:
        json.dump(translation, f, indent=2, ensure_ascii=False)
        f.write("\n")
