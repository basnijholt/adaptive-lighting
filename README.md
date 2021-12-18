[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![Version](https://img.shields.io/github/v/release/basnijholt/adaptive-lighting)

# Adaptive Lighting component for Home Assistant

![](https://github.com/home-assistant/brands/raw/b4a168b9af282ef916e120d31091ecd5e3c35e66/core_integrations/adaptive_lighting/icon.png)

Go to https://github.com/basnijholt/adaptive-lighting for the original project and instructions.

This is a very simple fork designed for my own personal system, but you are welcome to use this if you'd like.

I work very odd hours that require me to wake up at a different time everyday, so I was looking for a way to adapt my lights throughout the day based on whenever my Home Assistant alarm runs. Unfortunately after a lot of searching it seemed like this simple feature didn't exist anywhere, so I decided to make it myself. I know next to nothing about python so my priorities were:
- Getting the damn thing to work
- Trying my best to 'add' the feature instead of rewrite the entire code, therefore allowing me to merge future updates into this fork.
- Useability & Flexibility.

### New Services

`adaptive_lighting.change_sunlight_settings` Changes any sunlight settings on the specified switch.

| Service data attribute    | Description                                                                                |
|---------------------------|--------------------------------------------------------------------------------------------|
| `entity_id`               | The `entity_id` of the switch with the settings to apply.                                  |
| `transition`              | The number of seconds for the transition.                                                  |
| `use_config_defaults`     | Any setting in this service call that isn't EXPLICITLY defined will either default back to the config (True) or the current values (False) |
| `use_actual_sunrise_time` | Erase manual handling of the sunrise time (if any) and calculates the actual sunrise       |
| `use_actual_sunset_time`  | Erase manual handling of the sunset time (if any) and calculates the actual sunset         |
| `min_brightness`          | The minimum percent of brightness to set the lights to.                                    |
| `max_brightness`          | The maximum percent of brightness to set the lights to.                                    |
| `min_color_temp`          | The warmest color temperature to set the lights to, in Kelvin.                             |
| `max_color_temp`          | The coldest color temperature to set the lights to, in Kelvin.                             |
| `sleep_brightness`        | Brightness of lights while the sleep mode is enabled.                                      |
| `sleep_color_temp`        | Color temperature of lights while the sleep mode is enabled.                               |
| `sunrise_time`            | Override the sunrise time with a fixed time.	                                             |
| `sunrise_offset`          | Change the sunrise time with a positive or negative offset.                                |
| `sunset_time`             | Override the sunset time with a fixed time.                                                |
| `sunset_offset`           | Change the sunset time with a positive or negative offset.                                 |

# Maintainers

- @th3w1zard1

Go support the original project! @basnijholt https://github.com/basnijholt/adaptive-lighting
