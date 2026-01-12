---
icon: lucide/moon
---

# Sleep Mode

Sleep mode is a special operating mode that sets your lights to minimal brightness and very warm color, perfect for winding down at night without disrupting your circadian rhythm.

## Overview

When sleep mode is activated, Adaptive Lighting overrides normal sun-based calculations with fixed sleep settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `sleep_brightness` | 1% | Very dim lighting |
| `sleep_color_temp` | 1000K | Very warm (candlelight) |
| `sleep_rgb_color` | `[255, 56, 0]` | Deep orange/red |
| `sleep_transition` | 1 second | Quick transition |

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

### sleep_brightness

Sets the brightness level during sleep mode (1-100%).

```yaml
adaptive_lighting:
  - name: "Bedroom"
    lights:
      - light.bedroom
    sleep_brightness: 1  # Barely visible
```

### sleep_rgb_or_color_temp

Choose whether to use color temperature or RGB color in sleep mode:

| Value | Description |
|-------|-------------|
| `color_temp` | Use `sleep_color_temp` (default) |
| `rgb_color` | Use `sleep_rgb_color` |

### sleep_color_temp

The color temperature in Kelvin during sleep mode (when using `color_temp` mode).

```yaml
adaptive_lighting:
  - name: "Bedroom"
    lights:
      - light.bedroom
    sleep_rgb_or_color_temp: color_temp
    sleep_color_temp: 1000  # Very warm
```

### sleep_rgb_color

The RGB color during sleep mode (when using `rgb_color` mode). Useful for bulbs that don't support very low color temperatures.

```yaml
adaptive_lighting:
  - name: "Bedroom"
    lights:
      - light.bedroom
    sleep_rgb_or_color_temp: rgb_color
    sleep_rgb_color: [255, 56, 0]  # Deep orange/red
```

### sleep_transition

The transition duration when entering or exiting sleep mode.

```yaml
adaptive_lighting:
  - name: "Bedroom"
    lights:
      - light.bedroom
    sleep_transition: 10  # Slow 10-second transition
```

### transition_until_sleep

When enabled, Adaptive Lighting treats sleep settings as the minimum values and gradually transitions to them after sunset. This creates a natural wind-down effect.

```yaml
adaptive_lighting:
  - name: "Evening wind-down"
    lights:
      - light.living_room
    transition_until_sleep: true
    sleep_brightness: 10
    sleep_color_temp: 2000
```

## Automation Examples

### Enable Sleep Mode at Bedtime

```yaml
automation:
  - alias: "Bedtime - enable sleep mode"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id:
            - switch.adaptive_lighting_sleep_mode_bedroom
            - switch.adaptive_lighting_sleep_mode_hallway
```

### Sync with Input Boolean

```yaml
input_boolean:
  sleep_mode:
    name: "Sleep Mode"
    icon: mdi:sleep

automation:
  - alias: "Toggle sleep mode switches"
    trigger:
      - platform: state
        entity_id: input_boolean.sleep_mode
    action:
      - service: "switch.turn_{{ states('input_boolean.sleep_mode') }}"
        target:
          entity_id:
            - switch.adaptive_lighting_sleep_mode_bedroom
            - switch.adaptive_lighting_sleep_mode_living_room
```

### Disable Sleep Mode at Wake Time

```yaml
automation:
  - alias: "Morning - disable sleep mode"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id:
            - switch.adaptive_lighting_sleep_mode_bedroom
            - switch.adaptive_lighting_sleep_mode_living_room
```

### Motion-Activated Night Light

```yaml
automation:
  - alias: "Hallway night light"
    trigger:
      - platform: state
        entity_id: binary_sensor.hallway_motion
        to: "on"
    condition:
      - condition: time
        after: "22:00:00"
        before: "06:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.adaptive_lighting_sleep_mode_hallway
      - service: light.turn_on
        target:
          entity_id: light.hallway
      - wait_for_trigger:
          - platform: state
            entity_id: binary_sensor.hallway_motion
            to: "off"
            for: "00:02:00"
      - service: light.turn_off
        target:
          entity_id: light.hallway
```

## Best Practices

1. **Use very low brightness** (1-5%) for true sleep mode
2. **Use warm colors** (1000-2000K) to minimize blue light exposure
3. **Consider RGB mode** if your bulbs can't achieve very warm temperatures
4. **Set up automations** to automatically enable/disable sleep mode
5. **Use `transition_until_sleep`** for a gradual evening wind-down
