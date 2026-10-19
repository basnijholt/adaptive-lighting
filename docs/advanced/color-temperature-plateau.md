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

## Fixed evening times

The plateau options above are measured from solar noon, so the evening moves with the seasons. To get the same evening every day of the year, set two optional **local** times instead:

| Option | Default | Description |
|--------|---------|-------------|
| `color_temp_fixed_plateau_end` | unset | Local time until which the color temperature stays at `max_color_temp` |
| `color_temp_fixed_descent_end` | unset | Local time at which the color temperature has descended to `min_color_temp` |
| `color_temp_fixed_plateau_kelvin` | unset | Optional temperature (K) held until `color_temp_fixed_plateau_end` instead of `max_color_temp` |

```yaml
adaptive_lighting:
  - name: kitchen
    min_color_temp: 2700
    max_color_temp: 4000
    color_temp_fixed_plateau_end: "21:00:00"   # 4000 K until 21:00
    color_temp_fixed_descent_end: "23:00:00"   # smooth descent to 2700 K at 23:00
```

### Evening plateau lower than the daytime maximum

By default the evening holds `max_color_temp`. To keep a high daytime maximum but a calmer evening, set `color_temp_fixed_plateau_kelvin` (between `min_color_temp` and `max_color_temp`):

```yaml
adaptive_lighting:
  - name: kitchen
    min_color_temp: 2700
    max_color_temp: 5500
    color_temp_fixed_plateau_end: "21:00:00"
    color_temp_fixed_descent_end: "23:00:00"
    color_temp_fixed_plateau_kelvin: 4000   # 5500 K by day, 4000 K until 21:00
```

The morning and the middle of the day are unchanged and still reach `max_color_temp` (`color_temp_plateau_morning` and `color_temp_plateau_evening` keep their meaning, see the next points). After the daytime maximum the color temperature descends along the regular afternoon curve to `color_temp_fixed_plateau_kelvin`, **reaches it exactly and holds it for the last hour before `color_temp_fixed_plateau_end`** whatever the season, then descends to `min_color_temp` as described below.

- When the regular curve gets to the target by itself at least one hour before the plateau end (typically in winter), it is used unchanged. Otherwise (summer, or a late `sunset_offset`) the same curve is traversed faster so that the target is reached one hour before the plateau end; there is no step anywhere and the slope is zero where the descent starts.
- On a short afternoon the hold is shortened to half of the time between solar noon and the plateau end. If the plateau end is less than one hour after solar noon the target is ignored for that day (the maximum is held until the plateau end, as without the option), because there is no room to ramp down. In summer a long `color_temp_plateau_evening` that would not leave room for the descent may be shortened (the maximum is then held for less than that duration).
- The option needs both times, must lie between `min_color_temp` and `max_color_temp` (also checked when those change), and a value equal to `max_color_temp` is the same as leaving it unset. Unset keeps the exact previous behavior. Like every color temperature, the value is applied in steps of 5 K (4003 gives 4005).

The options are available in the UI (advanced section), in YAML and in `adaptive_lighting.change_switch_settings`. When they are unset, which is the default, nothing changes.

- Only the color temperature is affected. The brightness, the sleep mode (which keeps priority) and the morning curve are unchanged. `color_temp_plateau_evening` is superseded by these times while they are set, except that it still shapes the afternoon curve towards `color_temp_fixed_plateau_kelvin`.
- The color temperature follows the default curve until solar noon (and stays at `max_color_temp`, or `color_temp_fixed_plateau_kelvin` if set, from then until `color_temp_fixed_plateau_end`), then descends with a smooth cosine easing, then stays at `min_color_temp` until sunset or later.
- Validation: both times must be set together, they must differ, `color_temp_fixed_plateau_end` must be 12:00 or later, and the descent must last at most 12 hours. `color_temp_fixed_descent_end` may be after midnight (for example 23:00 → 01:00). In YAML or the UI an invalid pair is rejected; through the service it raises an error; in a stored configuration it is ignored with an error in the log.
- The times are wall-clock times of the Home Assistant time zone. On a day with a DST change inside the window, the real duration of the descent is one hour shorter or longer, but the curve stays continuous.
- The window is anchored on the last solar noon and cut at the next sunrise: it ends at `color_temp_fixed_descent_end` or at that sunrise, whichever comes first, so the color temperature is never higher than the morning curve at sunrise. If solar noon is later than `color_temp_fixed_plateau_end`, the descent starts at noon; if the window does not fit between noon and the next sunrise, the default curve is used for that day.
- Between sunset and `color_temp_fixed_descent_end` the fixed curve replaces the night value (so winter evenings stay at `max_color_temp` after sunset). After `color_temp_fixed_descent_end` the default night behavior resumes. With `adapt_until_sleep` this means a step from `min_color_temp` to the night gradient at that moment.
