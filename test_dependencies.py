with open("core/requirements_test_all.txt") as f:
    lines = f.readlines()

components = []
packages = []
deps = {}
for i, line in enumerate(lines):
    line = line.strip()
    if line.startswith("# homeassistant."):
        component = line.split("# homeassistant.")[1]
        components.append(component)
    elif components and line:
        packages.append(line)
    else:
        for component in components:
            for package in packages:
                deps.setdefault(component, []).append(package)
        components = []
        packages = []

required = [
    "components.recorder",
    "components.mqtt",
    "components.zeroconf",
    "components.http",
]
to_install = []
for r in required:
    to_install.extend(deps[r])
print(" ".join(to_install))
