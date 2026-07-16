---
icon: lucide/thermometer
---

# Custom Color Temperature Curve

By default, Adaptive Lighting reaches `min_color_temp` (fully warm) exactly
at sunset. In winter, when sunset happens as early as 5:30 PM, this can make
your lights turn fully warm well before you're ready to wind down for the
night.

The `color_temp_mode: custom` option lets you decouple "fully warm" from
"sunset": lights reach an intermediate `sunset_color_temp` at sunset, hold
there, and only finish ramping down to `min_color_temp` at a time you
choose — either a fixed clock time or a delay after sunset.

## How It Works

With `color_temp_mode: custom`:

- **At sunset**, color temperature reaches `sunset_color_temp` (instead of `min_color_temp`).
- **From sunset to the completion point**, it ramps down linearly from `sunset_color_temp` to `min_color_temp`.
- **After the completion point**, it stays at `min_color_temp` for the rest of the night.
- **Mornings are unaffected** — the sunrise ramp still runs between `min_color_temp` and `max_color_temp` as usual.

The completion point is set with one of:

| Option | Description |
|--------|-------------|
| `sunset_color_temp_delay` | Duration in seconds after sunset. Takes priority if set to a value > 0. |
| `sunset_color_temp_time` | A fixed clock time (`HH:MM:SS`). Used only if `sunset_color_temp_delay` is `0`. |

If neither is set, the curve completes immediately at sunset (equivalent to setting `min_color_temp` as `sunset_color_temp`).

!!! note
    `color_temp_mode: custom` overrides `transition_until_sleep` for color
    temperature — it always finishes at `min_color_temp` for the night.
    `transition_until_sleep` still applies normally to brightness.

## Example: Hold Until 9 PM

Matches the motivating case: an early winter sunset (5:30 PM) that only
partially warms the lights, finishing the transition to fully warm by 9 PM.

```yaml
adaptive_lighting:
  - name: "Living Room"
    lights:
      - light.living_room
    min_color_temp: 2000
    max_color_temp: 5500
    color_temp_mode: custom
    sunset_color_temp: 3000    # only reach a "medium warm" 3000K at sunset
    sunset_color_temp_time: "21:00:00"  # finish ramping to 2000K by 9 PM
```

## Example: Fixed Delay Instead of a Clock Time

```yaml
adaptive_lighting:
  - name: "Living Room"
    lights:
      - light.living_room
    color_temp_mode: custom
    sunset_color_temp: 3000
    sunset_color_temp_delay: 5400  # finish 90 minutes after sunset
```

See the [Configuration](../configuration.md) page for the full options table.
