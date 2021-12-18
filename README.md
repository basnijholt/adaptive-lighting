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

# Use cases
This fork is PERFECT if you, like I, have your smart phone's alarm synced up with Home Assistant. Simply have your phone call your home assistant alarm script/automation, then set the sunrise time to Python's now() and, optionally, the sunset time to ~12 hours in the future like so:

iphone_carly_wakeup:
  alias: iPhone Carly Wakeup
  sequence:
  - condition: state
    entity_id: input_boolean.carly_iphone_wakeup
    state: 'off'
  - service: input_datetime.set_datetime
    target:
      entity_id: input_datetime.carly_iphone_wakeup
    data:
      time: '{{ now().strftime("%H:%M:%S") }}'
  - service: input_boolean.turn_on
    target:
      entity_id: input_boolean.carly_iphone_wakeup
  - repeat:
      count: '{{ (states.switch    | map(attribute=''entity_id'')    | select(">","switch.adaptive_lighting_al_")    |
        select("<", "switch.adaptive_lighting_al_z")    | join(",")).split(",")|length
        }}'
      sequence:
      - service: adaptive_lighting.change_sunlight_settings
        data:
          entity_id: "{{ ((states.switch\n     | map(attribute='entity_id')\n    \
            \ | select(\">\",\"switch.adaptive_lighting_al_\")\n     | select(\"<\"\
            , \"switch.adaptive_lighting_al_z\")\n     | join(\",\")).split(\",\"\
            ))[repeat.index-1] }}"
          sunrise_time: '{{ now().strftime("%H:%M:%S") }}'
          sunset_time: '{{ (as_timestamp(now()) + 12*60*60) | timestamp_custom("%H:%M:%S")
            }}'
  - service: script.turn_on
    target:
      entity_id: script.run_wakeup_routine
  - service: input_boolean.turn_off
    target:
      entity_id:
      - input_boolean.carly_iphone_winddown
      - input_boolean.carly_iphone_bedtime
  - service: input_datetime.set_datetime
    target:
      entity_id: input_datetime.wakeup_time
    data:
      time: '{{ now().strftime("%H:%M:%S") }}'
  - service: script.adaptive_lighting_disable_sleep_mode
  mode: queued
  icon: mdi:weather-sunset
  max: 10

This script loops through all of my adaptive lighting switches and applies the new sunrise/sunset times on EACH switch.


# Plans/Goals
- I'm still having issues with the 'detect changes outside of HA' option in the original integration. If I don't find a fix soon I'm going to code something myself. Sometimes we turn off lights and they turn right back on `interval` seconds later. Wth??
- Have service calls default to every adaptive-lighting switch. Looping around a naming scheme to me seems very hacky and I'd love a way to leave the switch entity_id blank and the integration be smart enough to just friggin apply the settings to every switch... Maybe internally using group.set and a naming scheme?
- Have lights follow closer to the actual weather forecast for the day. i.e if it's snowy or cloudy outside, have the bulbs dim to 80% brightness and apply a colder color temperature to give a milky/foggy feel to the room.

# More Background Info
I actually have an AdaptiveLighting switch per every smart bulb group in my home. Home assistant doesn't measure the brightness in lumens (I mean how could they) so it just doesn't make sense to use the same color temperatures/brightnesses for every single bulb of my home. Unfortunately I ran into some hiccups trying to use any of the original service calls due to the integration taking a singular switch entity_id instead of allowing multiple.

This means I either needed to hard code ALL of my scripts for each bulb group I have (over 10 currently) and hate myself later whenever I have to rewrite most of the code whenever I add a new bulb group, or I was going to need to figure out a way to group multiple switches.

I first looked into the group.set command from home assistant. This would take a lot of the hard-coding out but it still wasn't quite as simple as I wanted it to be. The goal was to be able to use one service call to apply any global settings I wanted to all of my adaptive switches.

I eventually figured out a somewhat-functional method. Using templates I was actually able to select all adaptive light switches that followed a naming scheme, specifically 'switch.adaptive_lighting_al_[light_entity_id]'

It's apparently possible to manually add an adaptive-lighting integration via the config file, so that's how I did it. Add to home assistant configuration.yaml:
adaptive_lighting: !include adaptive_lighting.yaml

And then create adaptive-lighting.yaml and fill it in with your preferences. Here's part of mine.

- name: "al_bedroom_ceilingfan_lights"
  lights: light.bedroom_ceilingfan_lights
  prefer_rgb_color: false
  transition: 45
  initial_transition: 1
  interval: 90
  min_brightness: 35
  max_brightness: 100
  min_color_temp: 2000
  max_color_temp: 5500
  sleep_brightness: 1
  sleep_color_temp: 1000
  take_over_control: true
  detect_non_ha_changes: false
  only_once: false
- name: "al_den_ceilingfan_lights"
  lights: light.den_ceilingfan_lights
  prefer_rgb_color: false
  transition: 45
  initial_transition: 1
  interval: 90
  min_brightness: 35
  max_brightness: 100
  min_color_temp: 2000
  max_color_temp: 5500
  sleep_brightness: 1
  sleep_color_temp: 1000
  take_over_control: true
  detect_non_ha_changes: false
  only_once: false
- name: "al_linkind_dimmer_bulb"
  lights: light.linkind_dimmer_bulb
  prefer_rgb_color: false
  transition: 45
  initial_transition: 0
  interval: 90
  min_brightness: 45
  max_brightness: 100
  sleep_brightness: 8
  take_over_control: true
  detect_non_ha_changes: false
  only_once: false
  
  You can then create several scripts:
  
  adaptive_lighting_set_manual_control:
  alias: 'Adaptive Lighting: Set Manual Control'
  sequence:
  - choose:
    - conditions:
      - condition: template
        value_template: '{{ lights is string }}'
      sequence:
      - service: switch.turn_off
        target:
          entity_id: '{{ "switch.adaptive_lighting_al" ~ lights[6:] }}'
    - conditions:
      - condition: template
        value_template: '{{ lights is mapping }}'
      sequence:
      - service: switch.turn_off
        target:
          entity_id: '{{ "switch.adaptive_lighting_al" ~ lights[6:]|join(",switch.adaptive_lighting_al")
            }}'
    default:
    - service: switch.turn_off
      target:
        entity_id: "{{ states.switch\n   | map(attribute='entity_id')\n   | select(\"\
          >\", \"switch.adaptive_lighting_al_\")\n   | select(\"<\", \"switch.adaptive_lighting_al_z\"\
          )\n   | join(\",\") }}"
  mode: single

adaptive_lighting_disable_sleep_mode:
  alias: 'Adaptive Lighting: Disable Sleep Mode'
  sequence:
  - choose:
    - conditions:
      - condition: template
        value_template: '{{ lights is string }}'
      sequence:
      - service: switch.turn_off
        target:
          entity_id: '{{ "switch.adaptive_lighting_sleep_mode_al_" ~ lights[6:] }}'
    - conditions:
      - condition: template
        value_template: '{{ lights is mapping }}'
      sequence:
      - service: switch.turn_off
        target:
          entity_id: '{{ "switch.adaptive_lighting_sleep_mode_al_" ~ lights[6:]|join(",switch.adaptive_lighting_sleep_mode_al_")
            }}'
    default:
    - service: switch.turn_off
      target:
        entity_id: "{{ states.switch\n   | map(attribute='entity_id')\n   | select(\"\
          >\", \"switch.adaptive_lighting_sleep_mode_al_\")\n   | select(\"<\", \"\
          switch.adaptive_lighting_sleep_mode_al_z\")\n   | join(\",\") }}"
  - condition: template
    value_template: '{{ force == true }}'
  - service: script.adaptive_lighting_apply
    data:
      lights: lights
  mode: single

Using templates you can loop through all of your Adaptive Lighting switches since they're following the same naming scheme, thus removing the hard-coding problem and allowing yourself to benefit from all future updates to the integration!

# Maintainers

- @th3w1zard1

Go support the original project! @basnijholt https://github.com/basnijholt/adaptive-lighting
