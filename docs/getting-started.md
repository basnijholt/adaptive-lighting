---
icon: lucide/rocket
---

# Getting Started

This guide will help you install and configure Adaptive Lighting for the first time.

## Prerequisites

- [Home Assistant](https://www.home-assistant.io/) 2024.12.0 or newer
- [HACS](https://hacs.xyz/) (Home Assistant Community Store) installed

## Installation

### Via HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on **Integrations**
3. Click the **+ Explore & Download Repositories** button
4. Search for "Adaptive Lighting"
5. Click **Download**
6. Restart Home Assistant

Or use this button to open HACS directly:

[![Open your Home Assistant instance and open the Adaptive Lighting integration inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=basnijholt&repository=adaptive-lighting&category=integration)

### Manual Installation

1. Download the latest release from [GitHub](https://github.com/basnijholt/adaptive-lighting/releases)
2. Extract the `adaptive_lighting` folder to your `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

Choose one of two configuration methods:

=== "Via UI"

    1. Go to **Settings** → **Devices & Services**
    2. Click **+ Add Integration**
    3. Search for "Adaptive Lighting"
    4. Follow the setup wizard to name your Adaptive Lighting instance
    5. Find Adaptive Lighting and click **Configure**
    6. Select your lights and adjust the settings

    No `adaptive_lighting:` entry is needed in `configuration.yaml`.

=== "Via YAML"

    Instances configured through YAML must be edited in YAML.

    ```yaml
    adaptive_lighting:
      - name: "Living Room"
        lights:
          - light.living_room_ceiling
          - light.living_room_lamp
        min_brightness: 20
        max_brightness: 100
        min_color_temp: 2200
        max_color_temp: 5500
    ```

    Restart Home Assistant after changing the YAML configuration.

## Basic YAML Configuration Example

Here's a simple configuration to get you started:

```yaml
adaptive_lighting:
  - name: "Main Lights"
    lights:
      - light.living_room
      - light.bedroom
      - light.kitchen
    transition: 30
    min_brightness: 10
    max_brightness: 100
    min_color_temp: 2000
    max_color_temp: 5500
```

## Verifying Installation

After configuration, you should see new switches in Home Assistant:

- `switch.adaptive_lighting_main_lights`
- `switch.adaptive_lighting_sleep_mode_main_lights`
- `switch.adaptive_lighting_adapt_brightness_main_lights`
- `switch.adaptive_lighting_adapt_color_main_lights`

Turn on `switch.adaptive_lighting_main_lights` to start adapting your lights!

## Next Steps

- [Configuration Reference](configuration.md) - Explore all available options
- [Services](services.md) - Learn about service calls for automations
- [Automation Examples](automation-examples.md) - See real-world automation recipes
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
