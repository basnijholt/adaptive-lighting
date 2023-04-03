from pathlib import Path
import sys

import yaml

sys.path.append(str(Path(__file__).parent.parent))

from custom_components.adaptive_lighting import const  # noqa: E402

services_filename = "custom_components/adaptive_lighting/services.yaml"
with open(services_filename) as f:
    services = yaml.safe_load(f)

for service_name, dct in services.items():
    if service_name == "set_manual_control":
        alternative_docs = const.DOCS_MANUAL_CONTROL
    elif service_name == "apply":
        alternative_docs = const.DOCS_APPLY
    else:
        alternative_docs = const.DOCS

    for field_name, field in dct["fields"].items():
        if alternative_docs is not None and field_name in alternative_docs:
            description = alternative_docs[field_name]
        else:
            description = const.DOCS[field_name]
        field["description"] = description

with open(services_filename, "w") as f:
    yaml.dump(services, f, sort_keys=False, width=1000)
