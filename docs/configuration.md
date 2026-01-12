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
<!-- from docs_gen import get_config_example_full -->
<!-- print(get_config_example_full()) -->
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

  - name: "Night Lights"
    lights:
      - light.hallway_night
      - light.bathroom_night
    min_brightness: 1
    max_brightness: 20
```

## Option Categories

### Brightness Settings

| Option | Description |
|--------|-------------|
| `min_brightness` | Minimum brightness (1-100%) |
| `max_brightness` | Maximum brightness (1-100%) |
| `brightness_mode` | How brightness changes (`default`, `linear`, `tanh`) |
| `brightness_mode_time_dark` | Ramp duration before/after sunrise/sunset |
| `brightness_mode_time_light` | Ramp duration after/before sunrise/sunset |

See [Brightness Modes](advanced/brightness-modes.md) for detailed explanations.

### Color Temperature Settings

| Option | Description |
|--------|-------------|
| `min_color_temp` | Warmest temperature in Kelvin |
| `max_color_temp` | Coldest temperature in Kelvin |
| `prefer_rgb_color` | Use RGB instead of color temperature |

### Sleep Mode Settings

| Option | Description |
|--------|-------------|
| `sleep_brightness` | Brightness in sleep mode (1-100%) |
| `sleep_color_temp` | Color temperature in sleep mode |
| `sleep_rgb_color` | RGB color for sleep mode |
| `sleep_transition` | Transition duration for sleep mode |
| `transition_until_sleep` | Gradually transition to sleep settings after sunset |

See [Sleep Mode](advanced/sleep-mode.md) for more details.

### Manual Control Settings

| Option | Description |
|--------|-------------|
| `take_over_control` | Detect manual changes and pause adaptation |
| `detect_non_ha_changes` | Detect changes made outside Home Assistant |
| `autoreset_control_seconds` | Auto-reset manual control after this many seconds |

See [Manual Control](advanced/manual-control.md) for detailed behavior.

### Timing Settings

| Option | Description |
|--------|-------------|
| `sunrise_time` | Fixed sunrise time (overrides actual) |
| `sunset_time` | Fixed sunset time (overrides actual) |
| `sunrise_offset` | Offset from actual sunrise in seconds |
| `sunset_offset` | Offset from actual sunset in seconds |
| `min_sunrise_time` / `max_sunrise_time` | Constrain virtual sunrise |
| `min_sunset_time` / `max_sunset_time` | Constrain virtual sunset |

### Transition Settings

| Option | Description |
|--------|-------------|
| `transition` | Duration for regular transitions (seconds) |
| `initial_transition` | Duration when lights first turn on |
| `interval` | How often to adapt lights (seconds) |
