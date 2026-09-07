---
icon: lucide/sliders-horizontal
---

# Intensity

Intensity scales how far the adaptive settings travel from their floor, without leaving adaptive mode. It is the option to reach for when you want a dimmer room that still tracks the sun — a "mood" level, rather than a fixed brightness.

## The Dial

Each Adaptive Lighting configuration creates a number entity:

```
number.adaptive_lighting_<name>_intensity
```

Set it like any other number:

```yaml
service: number.set_value
target:
  entity_id: number.adaptive_lighting_living_room_intensity
data:
  value: 60
```

The value is a percentage, and it interpolates:

```
output = floor_value + (adaptive_value - floor_value) × intensity / 100
```

| Intensity | Result |
|-----------|--------|
| `100` (default) | The adaptive values, unchanged. The dial costs nothing until you move it. |
| `0` | The floor. |
| in between | A scaled adaptive curve — the sun still moves the lights at every setting. |

The key property is that the lights stay adaptive at every value. Intensity does not freeze a light at a level; it moves the whole curve closer to the floor and keeps following the sun from there. Both brightness and color are scaled together.

Changing the dial re-adapts the lights immediately rather than waiting for the next `interval`, and the value survives a restart.

## Choosing the Floor

The floor is set per configuration with `intensity_floor`:

| `intensity_floor` | 0% gives | Use it when |
|-------------------|----------|-------------|
| `sleep` (default) | `sleep_brightness` / `sleep_color_temp` | You want the dial to reach as low as the configuration goes. 0% then matches [sleep mode](sleep-mode.md). |
| `minimum` | `min_brightness` / `min_color_temp` | You want the dial to stay inside the range the adaptive curve already uses. |

`minimum` never takes a light below what Adaptive Lighting would have done at its darkest anyway. The trade is that it does less and less as the evening goes on, and **color stops moving after sunset** — the adaptive color temperature is already `min_color_temp` there, so the floor and the value being interpolated from are the same number.

`sleep` keeps the dial useful at every hour, because the sleep settings sit below the adaptive curve at all times.

## `transition_until_sleep` Overrides the Floor

With [`transition_until_sleep`](sleep-mode.md) enabled, the adaptive color temperature after sunset descends *below* `min_color_temp` towards `sleep_color_temp`. A `min_color_temp` floor would then sit **above** the adaptive value, and turning the dial down would make the light *cooler* — the opposite of what a dimmer should do.

For that reason the `sleep` floor is forced whenever `transition_until_sleep` is on, whatever `intensity_floor` says. The switch's `intensity_floor` attribute reports the floor actually in use, so you can see when this applies:

```yaml
{{ state_attr('switch.adaptive_lighting_living_room', 'intensity_floor') }}
```

## Interaction With Sleep Mode

Sleep mode ignores the dial entirely. Its output already *is* the sleep value, so scaling towards the floor would be a no-op with the default floor and misleading with the other. Sleep mode behaves identically whatever the intensity is set to.

## Attributes

The main switch exposes both values:

| Attribute | Meaning |
|-----------|---------|
| `intensity` | The current dial value, 0-100. |
| `intensity_floor` | The floor in use, `sleep` or `minimum`, after the `transition_until_sleep` override. |

## Why Not Just Scale `min_brightness` and `max_brightness`?

Rescaling the brightness band from an automation works, but it hardcodes each configuration's band in the automation. Retuning a light in Adaptive Lighting then silently puts the two out of step, and the automation has to be updated in parallel forever. It also leaves color untouched unless you cap `max_color_temp` separately.

The dial reads the configuration's own numbers, so there is nothing to keep in sync, and it moves color along with brightness.
