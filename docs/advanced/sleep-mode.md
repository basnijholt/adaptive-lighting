---
icon: lucide/moon
---

# Sleep Mode

Sleep mode is a special operating mode that sets your lights to minimal brightness and very warm color, perfect for winding down at night without disrupting your circadian rhythm.

## Activating Sleep Mode

Each Adaptive Lighting configuration creates a sleep mode switch:

```
switch.adaptive_lighting_sleep_mode_<name>
```

Turn it on to activate sleep mode:

```yaml
service: switch.turn_on
target:
  entity_id: switch.adaptive_lighting_sleep_mode_living_room
```

## Configuration Options

Sleep mode is configured through the main Adaptive Lighting configuration. See the [Configuration](../configuration.md) page for the full options table. The sleep-related options are:

| Option | Default | Description |
|--------|---------|-------------|
| `sleep_brightness` | 1 | Brightness percentage in sleep mode |
| `sleep_rgb_or_color_temp` | `color_temp` | Use `rgb_color` or `color_temp` in sleep mode |
| `sleep_color_temp` | 1000 | Color temperature in Kelvin for sleep mode |
| `sleep_rgb_color` | `[255, 56, 0]` | RGB color for sleep mode |
| `sleep_transition` | 1 | Transition duration in seconds |
| `transition_until_sleep` | false | Gradually transition to sleep settings after sunset |

## Automation Examples

See [Automation Examples](../automation-examples.md) for sleep mode automation recipes, including:

- Toggle sleep mode using an `input_boolean`
- Set sunrise/sunset based on alarm time
