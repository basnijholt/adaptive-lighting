from pathlib import Path
import sys

import yaml

sys.path.append(str(Path(__file__).parent.parent))

from custom_components.adaptive_lighting import const  # noqa: E402

services_filename = "custom_components/adaptive_lighting/services.yaml"
with open(services_filename) as f:
    services = yaml.safe_load(f)

for service_name, dct in services.items():
    for field_name, field in dct["fields"].items():
        field["description"] = const.DOCS[field_name]

with open(services_filename, "w") as f:
    yaml.dump(services, f, sort_keys=False, width=1000)
