---
icon: lucide/settings
---

# Configuration

Adaptive Lighting supports configuration through both YAML and the Home Assistant UI, with identical option names in both methods.

## Basic Configuration

The minimal configuration requires only adding the integration to your `configuration.yaml`:

```yaml
adaptive_lighting:
```

You can then configure everything through the UI at **Settings** → **Devices & Services** → **Adaptive Lighting** → **Configure**.

## YAML Configuration

For YAML configuration, you can specify lights and options directly:

```yaml
adaptive_lighting:
  - name: "Living Room"
    lights:
      - light.living_room_ceiling
      - light.living_room_lamp
```

## All Options

All configuration options are listed below with their default values. These options work identically in both YAML and the UI.

<!-- CODE:START -->
<!-- import sys; sys.path.insert(0, 'custom_components/adaptive_lighting') -->
<!-- from _docs_helpers import generate_config_markdown_table -->
<!-- print(generate_config_markdown_table()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## Full Configuration Example

<!-- CODE:START -->
<!-- import sys; sys.path.insert(0, 'custom_components/adaptive_lighting') -->
<!-- from docs_gen import readme_section -->
<!-- print(readme_section("config-example-full", strip_heading=False)) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## Multiple Configurations

You can create multiple Adaptive Lighting configurations for different areas or use cases:

```yaml
adaptive_lighting:
  - name: "Daytime Spaces"
    lights:
      - light.living_room
      - light.kitchen
      - light.office
    min_brightness: 30
    max_brightness: 100

  - name: "Bedroom"
    lights:
      - light.bedroom_ceiling
      - light.bedroom_lamp
    min_brightness: 5
    max_brightness: 80
    sleep_brightness: 1
    sleep_color_temp: 1000
```

## Related Topics

- [Brightness Modes](advanced/brightness-modes.md) - Detailed explanation of brightness calculation modes
- [Sleep Mode](advanced/sleep-mode.md) - Sleep mode configuration
- [Manual Control](advanced/manual-control.md) - How manual control detection works
