---
icon: lucide/thermometer-sun
---

# Color Temperature Plateau

By default the color temperature follows the sun position: it rises from `min_color_temp` at sunrise to `max_color_temp` at solar noon, and falls back to `min_color_temp` at sunset. The light therefore only *touches* `max_color_temp` at a single instant.

`color_temp_plateau_morning` and `color_temp_plateau_evening` hold `max_color_temp` for a while around solar noon, while still ramping smoothly from and to `min_color_temp` at sunrise and sunset. Both are independent, in seconds, and default to `0` (the unchanged default curve).

| Option | Default | Description |
|--------|---------|-------------|
| `color_temp_plateau_morning` | `0` | Seconds *before* solar noon that the color temperature already stays at `max_color_temp` |
| `color_temp_plateau_evening` | `0` | Seconds *after* solar noon that the color temperature stays at `max_color_temp` |

## How it works

The ramp is the same curve as without a plateau, but compressed into the time between sunrise (or sunset) and the start (or end) of the plateau. The color temperature is therefore continuous, has no jump at the edge of the plateau, and still equals `min_color_temp` exactly at the (offset) sunrise and sunset.

- A plateau is measured from the same "noon" as the rest of the integration: solar noon, or the middle between sunrise and sunset when `sunrise_time`/`sunset_time` (or their min/max variants) are set. Sunrise and sunset offsets move the far end of the ramp; without fixed times, the anchor stays at solar noon.
- Configuration accepts durations from 0 to 12 hours (43200 seconds); values outside that range are rejected. At runtime, each plateau is further limited to 90% of the time between noon and sunrise/sunset, so that a ramp of at least 10% of that time always remains.
- Only the color temperature is affected. The brightness, the sleep mode, and the color after sunset (including `adapt_until_sleep`) are unchanged.

## Example

```yaml
adaptive_lighting:
  - name: kitchen
    min_color_temp: 2700
    max_color_temp: 4000
    sunset_offset: 7200            # 2 hours
    color_temp_plateau_morning: 3600   # at 4000 K from 1 hour before noon
    color_temp_plateau_evening: 14400  # stays at 4000 K until 4 hours after noon
```

The same options can be changed at runtime with `adaptive_lighting.change_switch_settings`.
