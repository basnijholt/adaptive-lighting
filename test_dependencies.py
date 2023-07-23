from collections import defaultdict

deps = defaultdict(list)
components, packages = [], []

with open("core/requirements_test_all.txt") as f:
    lines = f.readlines()

for line in lines:
    line = line.strip()

    if line.startswith("# homeassistant."):
        if components and packages:
            for component in components:
                deps[component].extend(packages)
            components, packages = [], []
        components.append(line.split("# homeassistant.")[1])
    elif components and line:
        packages.append(line)

# The last batch of components and packages
if components and packages:
    for component in components:
        deps[component].extend(packages)

required = [
    "components.recorder",
    "components.mqtt",
    "components.zeroconf",
    "components.http",
    "components.stream",
    "components.conversation",  # only available after HA≥2023.2
    "components.cloud",
]
to_install = [package for r in required for package in deps[r]]

print(" ".join(to_install))
