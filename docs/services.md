---
icon: lucide/zap
---

# Services

Adaptive Lighting provides three services for programmatic control, allowing you to integrate with automations and scripts.

## adaptive_lighting.apply

Applies the current Adaptive Lighting settings to lights on demand. Useful for forcing an immediate update or applying settings to lights that aren't in the regular adaptation cycle.

### Parameters

<!-- CODE:START -->
<!-- import sys; sys.path.insert(0, 'custom_components/adaptive_lighting') -->
<!-- from _docs_helpers import generate_apply_markdown_table -->
<!-- print(generate_apply_markdown_table()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

### Example Usage

```yaml
# Apply current settings to specific lights
service: adaptive_lighting.apply
data:
  entity_id: switch.adaptive_lighting_living_room
  lights:
    - light.floor_lamp
    - light.desk_lamp
  turn_on_lights: false
```

```yaml
# Force apply with custom transition
service: adaptive_lighting.apply
data:
  entity_id: switch.adaptive_lighting_bedroom
  transition: 5
  adapt_brightness: true
  adapt_color: true
```

---

## adaptive_lighting.set_manual_control

Marks or unmarks a light as "manually controlled". When a light is marked as manually controlled, Adaptive Lighting will not adjust it until the manual control flag is cleared.

### Parameters

<!-- CODE:START -->
<!-- import sys; sys.path.insert(0, 'custom_components/adaptive_lighting') -->
<!-- from _docs_helpers import generate_set_manual_control_markdown_table -->
<!-- print(generate_set_manual_control_markdown_table()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

### Example Usage

```yaml
# Remove manual control from a light (resume adaptation)
service: adaptive_lighting.set_manual_control
data:
  entity_id: switch.adaptive_lighting_living_room
  lights:
    - light.floor_lamp
  manual_control: false
```

```yaml
# Mark a light as manually controlled (pause adaptation)
service: adaptive_lighting.set_manual_control
data:
  entity_id: switch.adaptive_lighting_living_room
  lights:
    - light.floor_lamp
  manual_control: true
```

```yaml
# Only pause brightness adaptation, continue color adaptation
service: adaptive_lighting.set_manual_control
data:
  entity_id: switch.adaptive_lighting_living_room
  lights:
    - light.floor_lamp
  manual_control: brightness
```

---

## adaptive_lighting.change_switch_settings

<!-- CODE:START -->
<!-- import sys; sys.path.insert(0, 'custom_components/adaptive_lighting') -->
<!-- from docs_gen import readme_section -->
<!-- print(readme_section("change-switch-settings")) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

### Example Usage

```yaml
# Temporarily change color temperature range
service: adaptive_lighting.change_switch_settings
data:
  entity_id: switch.adaptive_lighting_living_room
  min_color_temp: 2500
  max_color_temp: 4000
```

```yaml
# Override sunrise time for the day
service: adaptive_lighting.change_switch_settings
data:
  entity_id: switch.adaptive_lighting_bedroom
  sunrise_time: "07:00:00"
  use_defaults: current
```

```yaml
# Reset to configuration defaults
service: adaptive_lighting.change_switch_settings
data:
  entity_id: switch.adaptive_lighting_living_room
  use_defaults: configuration
```

---

## Events

Adaptive Lighting also fires events that you can use in automations.

### adaptive_lighting.manual_control

Fired when a light is marked as "manually controlled" due to a detected manual change.

**Event Data:**

| Attribute | Description |
|-----------|-------------|
| `entity_id` | The light that was marked as manually controlled |
| `switch` | The Adaptive Lighting switch entity |

### Example Automation

```yaml
automation:
  - alias: "Log manual control events"
    trigger:
      platform: event
      event_type: adaptive_lighting.manual_control
    action:
      - service: notify.mobile_app
        data:
          title: "Adaptive Lighting"
          message: "{{ trigger.event.data.entity_id }} was manually controlled"
```

See [Automation Examples](automation-examples.md) for more use cases.
