"""Update strings.json and en.json from const.py."""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from custom_components.adaptive_lighting import const  # noqa: E402

folder = Path("custom_components") / "adaptive_lighting"
strings_fname = folder / "strings.json"
en_fname = folder / "translations" / "en.json"
with strings_fname.open() as f:
    strings = json.load(f)

data = {k: f"{k}: {const.DOCS[k]}" for k, _, _ in const.VALIDATION_TUPLES}
strings["options"]["step"]["init"]["data"] = data

with strings_fname.open("w") as f:
    json.dump(strings, f, indent=2, ensure_ascii=False)
    f.write("\n")


# Sync changes from strings.json to en.json
with en_fname.open() as f:
    en = json.load(f)

en["config"]["step"]["user"] = strings["config"]["step"]["user"]
en["options"]["step"]["init"]["data"] = data

with en_fname.open("w") as f:
    json.dump(en, f, indent=2, ensure_ascii=False)
    f.write("\n")
