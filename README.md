[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
![Version](https://img.shields.io/github/v/release/basnijholt/adaptive-lighting?style=for-the-badge)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-42-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

# Automatically adapt the brightness and color of lights based on the sun position and take over manual control

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

`adaptive_lighting.change_switch_settings` Changes any attribute of a switch without requiring a reload of the integration.
Service data is the same as the config flow.
### Options
| option                      | description                                                                                                                                                                                                                   | required | default        | type    |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------------- | ------- |
| `name`                      | The name to use when displaying this switch.                                                                                                                                                                                  | False    | default        | string  |
| `lights`                    | List of light entities for Adaptive Lighting to control (may be empty).                                                                                                                                                       | False    | list           | []      |
| `prefer_rgb_color`          | Whether to use RGB color adjustment instead of native light color temperature.                                                                                                                                                | False    | False          | boolean |
| `initial_transition`        | How long the first transition is when the lights go from `off` to `on`.                                                                                                                                                       | False    | 1              | time    |
| `sleep_transition`          | How long the transition is when when "sleep mode" is toggled                                                                                                                                                                  | False    | 1              | time    |
| `transition`                | How long the transition is when the lights change, in seconds.                                                                                                                                                                | False    | 45             | integer |
| `interval`                  | How often to adapt the lights, in seconds.                                                                                                                                                                                    | False    | 90             | integer |
| `min_brightness`            | The minimum percent of brightness to set the lights to.                                                                                                                                                                       | False    | 1              | integer |
| `max_brightness`            | The maximum percent of brightness to set the lights to.                                                                                                                                                                       | False    | 100            | integer |
| `min_color_temp`            | The warmest color temperature to set the lights to, in Kelvin.                                                                                                                                                                | False    | 2000           | integer |
| `max_color_temp`            | The coldest color temperature to set the lights to, in Kelvin.                                                                                                                                                                | False    | 5500           | integer |
| `sleep_brightness`          | Brightness of lights while the sleep mode is enabled.                                                                                                                                                                         | False    | 1              | integer |
| `sleep_rgb_or_color_temp`   | Use either 'rgb_color' or 'color_temp' when in sleep mode.                                                                                                                                                                    | False    | 'color_temp'   | string  |
| `sleep_rgb_color`           | List of three numbers between 0-255, indicating the RGB color in sleep mode (only used when sleep_rgb_or_color_temp is 'rgb_color').                                                                                          | False    | `[255, 56, 0]` | list    |
| `sleep_color_temp`          | Color temperature of lights while the sleep mode is enabled (only used when sleep_rgb_or_color_temp is 'color_temp').                                                                                                         | False    | 1000           | integer |
| `sunrise_time`              | Override the sunrise time with a fixed time.                                                                                                                                                                                  | False    | None           | time    |
| `max_sunrise_time`          | Make the virtual sun always rise at at most a specific time while still allowing for even earlier times based on the real sun                                                                                                 | False    | None           | time    |
| `sunrise_offset`            | Change the sunrise time with a positive or negative offset.                                                                                                                                                                   | False    | 0              | time    |
| `sunset_time`               | Override the sunset time with a fixed time.                                                                                                                                                                                   | False    | None           | time    |
| `min_sunset_time`           | Make the virtual sun always set at at least a specific time while still allowing for even later times based on the real sun                                                                                                   | False    | None           | time    |
| `sunset_offset`             | Change the sunset time with a positive or negative offset.                                                                                                                                                                    | False    | 0              | time    |
| `only_once`                 | Whether to keep adapting the lights (false) or to only adapt the lights as soon as they are turned on (true).                                                                                                                 | False    | False          | boolean |
| `take_over_control`         | If another source calls `light.turn_on` while the lights are on and being adapted, disable Adaptive Lighting.                                                                                                                 | False    | True           | boolean |
| `detect_non_ha_changes`     | Whether to detect state changes and stop adapting lights, even not from `light.turn_on`. Needs `take_over_control` to be enabled. Note that by enabling this option, it calls 'homeassistant.update_entity' every 'interval'! | False    | False          | boolean |
| `separate_turn_on_commands` | Whether to use separate `light.turn_on` calls for color and brightness, needed for some types of lights                                                                                                                       | False    | False          | boolean |
| `send_split_delay`          | Wait between commands (milliseconds), when separate_turn_on_commands is used. May ensure that both commands are handled by the bulb correctly.                                                                                | False    | 0              | integer |
| `adapt_delay`               | Wait time in seconds between light turn on, and Adaptive Lights applying changes to the light state. May avoid flickering.                                                                                                    | False    | 0              | integer |

# Use cases
This fork is PERFECT if you, like I, have your smart phone's alarm synced up with Home Assistant. Simply have your phone call your home assistant alarm script/automation, then set the sunrise time to Python's now() and, optionally, the sunset time to ~12 hours in the future like so:

```
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
```
This script loops through all of my adaptive lighting switches and applies the new sunrise/sunset times on EACH switch.

# Plans/Goals
- I'm still having issues with the 'detect changes outside of HA' option in the original integration. If I don't find a fix soon I'm going to code something myself. Sometimes we turn off lights and they turn right back on `interval` seconds later. Wth??
- Have service calls default to every adaptive-lighting switch. Looping around a naming scheme to me seems very hacky and I'd love a way to leave the switch entity_id blank and the integration be smart enough to just friggin apply the settings to every switch... Maybe internally using group.set and a naming scheme?
- Have lights follow closer to the actual weather forecast for the day. i.e if it's snowy or cloudy outside, have the bulbs dim to 80% brightness and apply a colder color temperature to give a milky/foggy feel to the room.
- Mark the time a light has been set to manual control, for easily automating a reset after an allotted amount of time

# More Background Info
I actually have an AdaptiveLighting switch per every smart bulb group in my home. Home assistant doesn't measure the brightness in lumens (I mean how could they) so it just doesn't make sense to use the same color temperatures/brightnesses for every single bulb of my home. Unfortunately I ran into some hiccups trying to use any of the original service calls due to the integration taking a singular switch entity_id instead of allowing multiple.

This means I either needed to hard code ALL of my scripts for each bulb group I have (over 10 currently) and hate myself later whenever I have to rewrite most of the code whenever I add a new bulb group, or I was going to need to figure out a way to group multiple switches.

I first looked into the group.set command from home assistant. This would take a lot of the hard-coding out but it still wasn't quite as simple as I wanted it to be. The goal was to be able to use one service call to apply any global settings I wanted to all of my adaptive switches.

I eventually figured out a somewhat-functional method. Using templates I was actually able to select all adaptive light switches that followed a naming scheme, specifically 'switch.adaptive_lighting_al_[light_entity_id]'

It's apparently possible to manually add an adaptive-lighting integration via the config file, so that's how I did it. Add to home assistant configuration.yaml:
adaptive_lighting: !include adaptive_lighting.yaml

And then create adaptive-lighting.yaml and fill it in with your preferences. Here's part of mine.

```
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
  ```
  
  You can then create several scripts:
  
  ```
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
```

### Services

`adaptive_lighting.**apply**` applies Adaptive Lighting settings to lights on demand.

| Service data attribute | Optional | Description                                                                                  |
| ---------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `entity_id`            | no       | The `entity_id` of the switch with the settings to apply.                                    |
| `lights`               | yes      | A light (or list of lights) to apply the settings to.                                        |
| `transition`           | yes      | The number of seconds for the transition.                                                    |
| `adapt_brightness`     | yes      | Whether to change the brightness of the light or not.                                        |
| `adapt_color`          | yes      | Whether to adapt the color on supporting lights.                                             |
| `prefer_rgb_color`     | yes      | Whether to prefer RGB color adjustment over of native light color temperature when possible. |
| `turn_on_lights`       | yes      | Whether to turn on lights that are currently off.                                            |

`adaptive_lighting.set_manual_control` can mark (or unmark) whether a light is "manually controlled", meaning that when a light has `manual_control`, the light is not adapted.

| Service data attribute | Optional | Description                                                                                         |
| ---------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `entity_id`            | no       | The `entity_id` of the switch in which to (un)mark the light as being "manually controlled".        |
| `lights`               | yes      | entity_id(s) of lights, if not specified, all lights in the switch are selected.                    |
| `manual_control`       | yes      | Whether to add ('true') or remove ('false') the light from the 'manual_control' list, default: true |


## Automation examples

Reset the `manual_control` status of a light after an hour.
```yaml
- alias: "Adaptive lighting: reset manual_control after 1 hour"
  mode: parallel
  trigger:
    platform: event
    event_type: adaptive_lighting.manual_control
  variables:
    light: "{{ trigger.event.data.entity_id }}"
    switch: "{{ trigger.event.data.switch }}"
  action:
    - delay: "01:00:00"
    - condition: template
      value_template: "{{ light in state_attr(switch, 'manual_control') }}"
    - service: adaptive_lighting.set_manual_control
      data:
        entity_id: "{{ switch }}"
        lights: "{{ light }}"
        manual_control: false
```

Toggle multiple Adaptive Lighting switches to "sleep mode" using an `input_boolean.sleep_mode`.

```yaml
- alias: "Adaptive lighting: toggle 'sleep mode'"
  trigger:
    - platform: state
      entity_id: input_boolean.sleep_mode
    - platform: homeassistant
      event: start  # in case the states aren't properly restored
  variables:
    sleep_mode: "{{ states('input_boolean.sleep_mode') }}"
  action:
    service: "switch.turn_{{ sleep_mode }}"
    entity_id:
      - switch.adaptive_lighting_sleep_mode_living_room
      - switch.adaptive_lighting_sleep_mode_bedroom
```

Custom automation for detecting manual control events

```
alias: "[Adaptive Lighting] State Changed -> Set manual control DEV"
description: ""
trigger:
  - platform: event
    event_type: state_changed
condition:
  - condition: template
    value_template: "{{ domain == \"light\" }}"
  - condition: template
    value_template: "{{ newstate == \"on\" }}"
  - condition: template
    value_template: "{{ oldstate == \"on\" }}"
  - condition: template
    value_template: "{{ context_parent_id == none }}"
  - condition: template
    value_template: "{{ context_user_id == none }}"
  - condition: template
    value_template: "{{ \"adapt_lgt_\" not in context_id }}"
  - condition: or
    conditions:
      - condition: template
        value_template: "{{ (new_color_temp|float(0) - old_color_temp|float(0))|abs >= 20 }}"
      - condition: template
        value_template: "{{ (new_brightness|float(0) -  old_brightness|float(0))|abs >= 25 }}"
action:
  - service: system_log.write
    data:
      message: >-
        Monitor Adaptive Lighting ({{ light }}/{{ newlight }}/{{ oldlight }})
        changed by {{ context_user_id }}/{{ context_id }}/{{ context_parent_id
        }}. Brightness ({{ old_brightness }}-> {{ new_brightness }}). Color Temp
        ({{ old_color_temp }}-> {{ new_color_temp }})
      level: warning
  - service: adaptive_lighting.set_manual_control
    data:
      entity_id: "{{ \"switch.adaptive_lighting_al_\" ~ light[6:] }}"
      lights: "{{ light }}"
      manual_control: true
mode: parallel
max: 100
variables:
  light: "{{ trigger.event.data.entity_id | default }}"
  newlight: "{{ trigger.event.data.new_state.entity_id | default }}"
  oldlight: "{{ trigger.event.data.old_state.entity_id | default }}"
  domain: "{{ trigger.event.data.new_state.domain | default }}"
  newstate: "{{ trigger.event.data.new_state.state | default }}"
  oldstate: "{{ trigger.event.data.old_state.state | default }}"
  context_user_id: |-
    {% if trigger.event.data.new_state != None %}
      {{ trigger.event.data.new_state.context.user_id | default }}
    {% else %}
      {{ None }}
    {% endif %}
  context_id: |-
    {% if trigger.event.data.new_state != None %}
      {{ trigger.event.data.new_state.context.id | default }}
    {% else %}
      {{ None }}
    {% endif %}
  context_parent_id: |-
    {% if trigger.event.data.new_state != None %}
      {{ trigger.event.data.new_state.context.parent_id | default }}
    {% else %}
      {{ None }}
    {% endif %}
  new_brightness: |-
    {% if trigger.event.data.new_state != None %}
      {{ trigger.event.data.new_state.attributes.brightness | default }}
    {% else %}
      {{ None }}
    {% endif %}
  old_brightness: |-
    {% if trigger.event.data.old_state != None %}
      {{ trigger.event.data.old_state.attributes.brightness | default }}
    {% else %}
      {{ None }}
    {% endif %}
  new_color_temp: |-
    {% if trigger.event.data.new_state != None %}
      {{ trigger.event.data.new_state.attributes.color_temp | default }}
    {% else %}
      {{ None }}
    {% endif %}
  old_color_temp: |-
    {% if trigger.event.data.old_state != None %}
      {{ trigger.event.data.old_state.attributes.color_temp | default }}
    {% else %}
      {{ None }}
    {% endif %}
```

Using templates you can loop through all of your Adaptive Lighting switches since they're following the same naming scheme, thus removing the hard-coding problem and allowing yourself to benefit from all future updates to the integration!


## Graphs!
These graphs were generated using the values calculated by the Adaptive Lighting sensor/switch(es).

#### Sun Position:
![cl_percent|690x131](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/6/5/657ff98beb65a94598edeb4bdfd939095db1a22c.PNG)

#### Color Temperature:
![cl_color_temp|690x129](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/9/59e84263cbecd8e428cb08777a0413672c48dfcd.PNG)

#### Brightness:
![cl_brightness|690x130](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/8/58ebd994b62a8b1abfb3497a5288d923ff4e2330.PNG)



Go support the original project! @basnijholt https://github.com/basnijholt/adaptive-lighting
