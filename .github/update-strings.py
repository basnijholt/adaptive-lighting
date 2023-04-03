import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from custom_components.adaptive_lighting import const  # noqa: E402

strings_fname = "custom_components/adaptive_lighting/strings.json"
with open(strings_fname) as f:
    strings = json.load(f)

data = {k: f"{k}: {const.DOCS[k]}" for k, _, _ in const.VALIDATION_TUPLES}
strings["options"]["step"]["init"]["data"] = data

with open(strings_fname, "w") as f:
    json.dump(strings, f, indent=2, ensure_ascii=False)
    f.write("\n")
