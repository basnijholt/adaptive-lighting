---
icon: lucide/sliders-horizontal
---

# Intensity

Intensity blends the adaptive settings toward a configured endpoint, without leaving adaptive mode. It provides a room-wide "mood" level that still tracks the sun.

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
| `100` (default) | The adaptive values, unchanged; interpolation is skipped. |
| `0` | The floor. |
| in between | A scaled adaptive curve — the sun still moves the lights at every setting. |

Between 0 and 100, the light keeps following the sun with a smaller range. At 0, the target stays at the endpoint. Both brightness and color are blended, subject to the profile's adaptation switches and each light's manual-control status and supported color modes.

Changing the dial re-adapts eligible, already-on lights immediately rather than waiting for the next `interval`, even with `only_once` enabled. It does not turn lights on or clear manual control. While the main switch is off, it stores the value for later. The value survives a restart and is restored before startup adaptation; `only_once` still prevents startup adaptation.

## Choosing the Floor

The floor is set per configuration with `intensity_floor`:

| `intensity_floor` | 0% gives | Use it when |
|-------------------|----------|-------------|
| `sleep` (default) | `sleep_brightness` and the configured sleep color | You want 0% to match [sleep mode](sleep-mode.md). RGB sleep colors are used on color-capable lights; CT-only lights use `sleep_color_temp`. |
| `minimum` | `min_brightness` / `min_color_temp` | You want the dial to stay inside the range the adaptive curve already uses. |

`minimum` never takes a light below what Adaptive Lighting would have done at its darkest anyway. The trade is that it does less and less as the evening goes on, and **color stops moving after sunset** — the adaptive color temperature is already `min_color_temp` there, so the floor and the value being interpolated from are the same number.

The `sleep` endpoint can go below `min_brightness`. It dims and warms the light only when the sleep settings are dimmer and warmer than the current adaptive target. If you configured a brighter or cooler sleep setting, lowering intensity instead moves toward that setting. Intensity 0 means the configured endpoint, not off.

## `transition_until_sleep` Overrides the Floor

With [`transition_until_sleep`](sleep-mode.md) enabled, the adaptive color after sunset moves toward the sleep color. When sleep is warmer than `min_color_temp`, using the minimum endpoint could make dial-down cool the light during that period.

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

`change_switch_settings` preserves intensity, including when resetting settings to factory or configuration defaults. Set the number to 100 to restore the unmodified adaptive curve. Automations watching `brightness_pct` see the blended target, so changing intensity can trigger their brightness thresholds.

## Why Not Just Scale `min_brightness` and `max_brightness`?

An `input_number` helper and `change_switch_settings` automation can reproduce this brightness curve by replacing each original bound `B` with `floor + (B - floor) * intensity / 100`. Both bounds keep following the sun; this does not freeze the target. The automation needs the original bounds and must keep them in sync when the profile is retuned. Ordinary color-temperature bounds can be transformed similarly, but this alone does not reproduce sleep-RGB blending.

The dial reads the configuration's own numbers, so there is nothing to keep in sync, and it moves color along with brightness.
