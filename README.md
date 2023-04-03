[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
![Version](https://img.shields.io/github/v/release/basnijholt/adaptive-lighting?style=for-the-badge)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-47-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

# 🌞 Adaptive Lighting: Enhance Your Home's Atmosphere with Smart, Sun-Synchronized Lighting 🌙

![](https://github.com/home-assistant/brands/raw/b4a168b9af282ef916e120d31091ecd5e3c35e66/core_integrations/adaptive_lighting/icon.png)

Adaptive Lighting is a custom component for Home Assistant that intelligently adjusts the brightness and color of your lights 💡 based on the sun's position, while still allowing for manual control. Try it out now by finding it in HACS (Home Assistant Community Store) and installing it!

By automatically adapting the settings of your lights throughout the day, Adaptive Lighting helps maintain your natural circadian rhythm 😴, which can lead to improved sleep, mood, and overall well-being. Experience cooler color temperatures at noon, gradually transitioning to warmer colors at sunset and sunrise.

In addition to its regular mode, Adaptive Lighting also offers a "sleep mode" 🌜 which sets your lights to minimal brightness and a very warm color, perfect for winding down at night.

[[ToC](#books-table-of-contents)]

## :bulb: Features

Adaptive Lighting provides four switches (using "living_room" as an example component name):

- `switch.adaptive_lighting_living_room`: Turn Adaptive Lighting on or off and view current light settings through its attributes.
- `switch.adaptive_lighting_sleep_mode_living_room`: Activate "sleep mode" 😴 and set custom sleep_brightness and sleep_color_temp.
- `switch.adaptive_lighting_adapt_brightness_living_room`: Enable or disable brightness adaptation 🔆 for supported lights.
- `switch.adaptive_lighting_adapt_color_living_room`: Enable or disable color adaptation 🌈 for supported lights.

### :control_knobs: Regain Manual Control

Adaptive Lighting is designed to automatically detect when you or another source (e.g., automation) manually changes light settings 🕹️.
When this occurs, the affected light is marked as "manually controlled," and Adaptive Lighting will not make further adjustments until the light is turned off and back on or reset using the `adaptive_lighting.set_manual_control` service call.
This feature is available when `take_over_control` is enabled.

Additionally, enabling detect_non_ha_changes allows Adaptive Lighting to detect all state changes, including those made outside of Home Assistant, by comparing the light's state to its previously used settings.
The `adaptive_lighting.manual_control` event is fired when a light is marked as "manually controlled," allowing for integration with automations 🤖.

## :books: Table of Contents

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

  - [:gear: Configuration](#gear-configuration)
    - [:memo: Options](#memo-options)
    - [:hammer_and_wrench: Services](#hammer_and_wrench-services)
      - [`adaptive_lighting.apply`](#adaptive_lightingapply)
      - [`adaptive_lighting.set_manual_control`](#adaptive_lightingset_manual_control)
      - [`adaptive_lighting.change_switch_settings`](#adaptive_lightingchange_switch_settings)
  - [:robot: Automation examples](#robot-automation-examples)
- [Additional Information](#additional-information)
- [:sos: Troubleshooting](#sos-troubleshooting)
  - [:exclamation: Common Problems & Solutions](#exclamation-common-problems--solutions)
    - [:bulb: Lights Not Responding or Turning On by Themselves](#bulb-lights-not-responding-or-turning-on-by-themselves)
      - [:signal_strength: WiFi Networks](#signal_strength-wifi-networks)
      - [:spider_web: Zigbee, Z-Wave, and Other Mesh Networks](#spider_web-zigbee-z-wave-and-other-mesh-networks)
    - [:rainbow: Light Colors Not Matching](#rainbow-light-colors-not-matching)
    - [:bulb: Bulb-Specific Issues](#bulb-bulb-specific-issues)
  - [:bar_chart: Graphs!](#bar_chart-graphs)
      - [:sunny: Sun Position](#sunny-sun-position)
      - [:thermometer: Color Temperature](#thermometer-color-temperature)
      - [:high_brightness: Brightness](#high_brightness-brightness)
      - [While using `adapt_until_sleep: true`](#while-using-adapt_until_sleep-true)
  - [:busts_in_silhouette: Contributors](#busts_in_silhouette-contributors)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## :gear: Configuration

Adaptive Lighting supports configuration through both YAML and the frontend (**Configuration** -> **Integrations** -> **Adaptive Lighting**, **Adaptive Lighting** -> **Options**), with identical option names in both methods.

```yaml
# Example configuration.yaml entry
adaptive_lighting:
  lights:
    - light.living_room_lights
```

Transform your home's atmosphere with Adaptive Lighting 🏠, and experience the benefits of intelligent, sun-synchronized lighting today!

### :memo: Options

All of the configuration options are listed below, along with their default values.
The YAML and frontend configuration methods support all of the options listed below.

<!-- START_CODE -->
<!-- from homeassistant.components.adaptive_lighting import _docs_helpers -->
<!-- print(_docs_helpers.generate_config_markdown_table()) -->
<!-- END_CODE -->

<!-- START_OUTPUT -->
<!-- THIS CONTENT IS AUTOMATICALLY GENERATED -->
| Variable name                  | Description                                                                                                                                                                     | Default        | Type                                 |
|:-------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------|:-------------------------------------|
| `lights`                       | List of light entities to be controlled by Adaptive Lighting (may be empty). 🌟                                                                                                  | `[]`           | list of `entity_id`s                 |
| `prefer_rgb_color`             | Whether to prefer RGB color adjustment over light color temperature when possible. 🌈                                                                                            | `False`        | `bool`                               |
| `include_config_in_attributes` | Show all options as attributes on the switch in Home Assistant when set to `true`. 📝                                                                                            | `False`        | `bool`                               |
| `initial_transition`           | Duration of the first transition when lights turn from `off` to `on` in seconds. ⏲️                                                                                             | `1`            | `float` 0-6553                       |
| `sleep_transition`             | Duration of transition when 'sleep mode' is toggled in seconds. 😴                                                                                                               | `1`            | `float` 0-6553                       |
| `transition`                   | Duration of transition when lights change, in seconds. 🕑                                                                                                                        | `45`           | `float` 0-6553                       |
| `transition_until_sleep`       | When enabled, Adaptive Lighting will treat sleep settings as the minimum, transitioning to these values after sunset. 🌙                                                         | `False`        | `bool`                               |
| `interval`                     | Frequency to adapt the lights, in seconds. 🔄                                                                                                                                    | `90`           | `int > 0`                            |
| `min_brightness`               | Minimum brightness percentage. 💡                                                                                                                                                | `1`            | `int` 1-100                          |
| `max_brightness`               | Maximum brightness percentage. 💡                                                                                                                                                | `100`          | `int` 1-100                          |
| `min_color_temp`               | Warmest color temperature in Kelvin. 🔥                                                                                                                                          | `2000`         | `int` 1000-10000                     |
| `max_color_temp`               | Coldest color temperature in Kelvin. ❄️                                                                                                                                         | `5500`         | `int` 1000-10000                     |
| `sleep_brightness`             | Brightness percentage of lights in sleep mode. 😴                                                                                                                                | `1`            | `int` 1-100                          |
| `sleep_rgb_or_color_temp`      | Use either `'rgb_color'` or `'color_temp'` in sleep mode. 🌙                                                                                                                     | `color_temp`   | one of `['color_temp', 'rgb_color']` |
| `sleep_color_temp`             | Color temperature in sleep mode (used when `sleep_rgb_or_color_temp` is `color_temp`) in Kelvin. 😴                                                                              | `1000`         | `int` 1000-10000                     |
| `sleep_rgb_color`              | RGB color in sleep mode (used when `sleep_rgb_or_color_temp` is 'rgb_color'). 🌈                                                                                                 | `[255, 56, 0]` | RGB color                            |
| `sunrise_time`                 | Set a fixed time (HH:MM:SS) for sunrise. 🌅                                                                                                                                      | `None`         | `str`                                |
| `max_sunrise_time`             | Set the latest virtual sunrise time (HH:MM:SS), allowing for earlier real sunrises. 🌅                                                                                           | `None`         | `str`                                |
| `sunrise_offset`               | Adjust sunrise time with a positive or negative offset in seconds. ⏰                                                                                                            | `0`            | `int`                                |
| `sunset_time`                  | Set a fixed time (HH:MM:SS) for sunset. 🌇                                                                                                                                       | `None`         | `str`                                |
| `min_sunset_time`              | Set the earliest virtual sunset time (HH:MM:SS), allowing for later real sunsets. 🌇                                                                                             | `None`         | `str`                                |
| `sunset_offset`                | Adjust sunset time with a positive or negative offset in seconds. ⏰                                                                                                             | `0`            | `int`                                |
| `only_once`                    | Adapt lights only when they are turned on (`true`) or keep adapting them (`false`). 🔄                                                                                           | `False`        | `bool`                               |
| `take_over_control`            | Disable Adaptive Lighting if another source calls `light.turn_on` while lights are on and being adapted. Note that this calls `homeassistant.update_entity` every `interval`! 🔒 | `True`         | `bool`                               |
| `detect_non_ha_changes`        | Detect non-`light.turn_on` state changes and stop adapting lights. Requires `take_over_control`. 🕵️                                                                             | `False`        | `bool`                               |
| `separate_turn_on_commands`    | Use separate `light.turn_on` calls for color and brightness, needed for some light types. 🔀                                                                                     | `False`        | `bool`                               |
| `send_split_delay`             | Wait time (milliseconds) between commands when using `separate_turn_on_commands`. Helps ensure correct handling. ⏲️                                                             | `0`            | `int` 0-10000                        |
| `adapt_delay`                  | Wait time (seconds) between light turn on and Adaptive Lighting applying changes. Helps avoid flickering. ⏲️                                                                    | `0`            | `float > 0`                          |
| `autoreset_control_seconds`    | Automatically reset the manual control after a number of seconds. Set to 0 to disable. ⏲️                                                                                       | `0`            | `int` 0-31536000                     |

<!-- END_OUTPUT -->

Full example:

```yaml
# Example configuration.yaml entry
adaptive_lighting:
- name: "default"
  lights: []
  prefer_rgb_color: false
  transition: 45
  initial_transition: 1
  interval: 90
  min_brightness: 1
  max_brightness: 100
  min_color_temp: 2000
  max_color_temp: 5500
  sleep_brightness: 1
  sleep_color_temp: 1000
  sunrise_time: "08:00:00"  # override the sunrise time
  sunrise_offset:
  sunset_time:
  sunset_offset: 1800  # in seconds or '00:15:00'
  take_over_control: true
  detect_non_ha_changes: false
  only_once: false

```

### :hammer_and_wrench: Services

#### `adaptive_lighting.apply`

`adaptive_lighting.apply` applies Adaptive Lighting settings to lights on demand.

<!-- START_CODE -->
<!-- from homeassistant.components.adaptive_lighting import _docs_helpers -->
<!-- print(_docs_helpers.generate_apply_markdown_table()) -->
<!-- END_CODE -->

<!-- START_OUTPUT -->
<!-- THIS CONTENT IS AUTOMATICALLY GENERATED -->
| Service data attribute   | Description                                                                          | Required   | Type                 |
|:-------------------------|:-------------------------------------------------------------------------------------|:-----------|:---------------------|
| `entity_id`              | The `entity_id` of the switch with the settings to apply. 📝                          | ✅          | list of `entity_id`s |
| `lights`                 | A light (or list of lights) to apply the settings to. 💡                              | ❌          | list of `entity_id`s |
| `transition`             | Duration of transition when lights change, in seconds. 🕑                             | ❌          | `float` 0-6553       |
| `adapt_brightness`       | Whether to adapt the brightness of the light. 🌞                                      | ❌          | bool                 |
| `adapt_color`            | Whether to adapt the color on supporting lights. 🌈                                   | ❌          | bool                 |
| `prefer_rgb_color`       | Whether to prefer RGB color adjustment over light color temperature when possible. 🌈 | ❌          | bool                 |
| `turn_on_lights`         | Whether to turn on lights that are currently off. 🔆                                  | ❌          | bool                 |

<!-- END_OUTPUT -->
#### `adaptive_lighting.set_manual_control`

`adaptive_lighting.set_manual_control` can mark (or unmark) whether a light is "manually controlled", meaning that when a light has `manual_control`, the light is not adapted.

<!-- START_CODE -->
<!-- from homeassistant.components.adaptive_lighting import _docs_helpers -->
<!-- print(_docs_helpers.generate_set_manual_control_markdown_table()) -->
<!-- END_CODE -->

<!-- START_OUTPUT -->
<!-- THIS CONTENT IS AUTOMATICALLY GENERATED -->
| Service data attribute   | Description                                                                                    | Required   | Type                 |
|:-------------------------|:-----------------------------------------------------------------------------------------------|:-----------|:---------------------|
| `entity_id`              | The `entity_id` of the switch in which to (un)mark the light as being `manually controlled`. 📝 | ✅          | list of `entity_id`s |
| `lights`                 | entity_id(s) of lights, if not specified, all lights in the switch are selected. 💡             | ❌          | list of `entity_id`s |
| `manual_control`         | Whether to add ('true') or remove ('false') the light from the 'manual_control' list. 🔒        | ❌          | bool                 |

<!-- END_OUTPUT -->
#### `adaptive_lighting.change_switch_settings`

`adaptive_lighting.change_switch_settings` (new in 1.7.0) Change any of the above configuration options of Adaptive Lighting (such as `sunrise_time` or `prefer_rgb_color`) with a service call directly from your script/automation.

| Service data attribute                                    | Required | Description                                                                                                                                                                                                                                                                                                  |
| --------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `use_defaults`                                            | ❌        | (default: `current` for current settings) Choose from `factory`, `configuration`, or `current` to reset variables not being set with this service call. `current` leaves them as they are, `configuration` resets to initial startup values, `factory` resets to default values listed in the documentation. |
| **all other keys** (except the ones in the table below ⚠️) | ❌        | See the table below for disallowed keys.                                                                                                                                                                                                                                                                     |

The following keys are disallowed:

| **DISALLOWED** service data | Description                                                                                     |
| --------------------------- | ----------------------------------------------------------------------------------------------- |
| `entity_id`                 | You cannot change the switch's `entity_id`, as it has already been registered.                  |
| `lights`                    | You may call `adaptive_lighting.apply` with your lights or create a new config instead.         |
| `name`                      | You can rename your switch's display name in Home Assistant's UI.                               |
| `interval`                  | The interval is used only once when the config loads. A config change and restart are required. |

## :robot: Automation examples

<details>
<summary>Reset the <code>manual_control</code> status of a light after an hour.</summary>

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

</details>

<details>
<summary>Toggle multiple Adaptive Lighting switches to "sleep mode" using an <code>input_boolean.sleep_mode</code>.</summary>

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

Set your sunrise and sunset time based on your alarm. The below script sets sunset_time exactly 12 hours after the custom sunrise time.

```yaml
iphone_carly_wakeup:
  alias: iPhone Carly Wakeup
  sequence:
    - condition: state
      entity_id: input_boolean.carly_iphone_wakeup
      state: "off"
    - service: input_datetime.set_datetime
      target:
        entity_id: input_datetime.carly_iphone_wakeup
      data:
        time: '{{ now().strftime("%H:%M:%S") }}'
    - service: input_boolean.turn_on
      target:
        entity_id: input_boolean.carly_iphone_wakeup
    - repeat:
        count: >
          {{ (states.switch
              | map(attribute="entity_id")
              | select(">","switch.adaptive_lighting_al_")
              | select("<", "switch.adaptive_lighting_al_z")
              | join(",")
             ).split(",") | length }}
        sequence:
          - service: adaptive_lighting.change_switch_settings
            data:
              entity_id: switch.adaptive_lighting_al_den_ceilingfan_lights
              sunrise_time: '{{ now().strftime("%H:%M:%S") }}'
              sunset_time: >
                {{ (as_timestamp(now()) + 12*60*60) | timestamp_custom("%H:%M:%S") }}
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

</details>

# Additional Information

For more details on adding the integration and setting options, refer to the [documentation of the PR](https://deploy-preview-14877--home-assistant-docs.netlify.app/integrations/adaptive_lighting/) and [this video tutorial on Reddit](https://www.reddit.com/r/homeassistant/comments/jabhso/ha_has_it_before_apple_has_even_finished_it_i/).

Adaptive Lighting was initially inspired by @claytonjn's [hass-circadian\_lighting](https://github.com/claytonjn/hass-circadian_lighting), but has since been entirely rewritten and expanded with new features.

# :sos: Troubleshooting

Encountering issues? Enable debug logging in your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.adaptive_lighting: debug
```

After the issue occurs, create a new issue report with the log (`/config/home-assistant.log`).

## :exclamation: Common Problems & Solutions

### :bulb: Lights Not Responding or Turning On by Themselves

Adaptive Lighting sends more commands to lights than a typical human user would. If your light control network is unhealthy, you may experience:

- Laggy manual commands (e.g., turning lights on or off).
- Unresponsive lights.
- Home Assistant reporting incorrect light states, causing Adaptive Lighting to inadvertently turn lights back on.

Most issues that appear to be caused by Adaptive Lighting are actually due to unrelated problems. Addressing these issues will significantly improve your Home Assistant experience.

#### :signal_strength: WiFi Networks

Ensure your light bulbs have a strong WiFi connection. If the signal strength is less than -70dBm, the connection may be weak and prone to dropping messages.

#### :spider_web: Zigbee, Z-Wave, and Other Mesh Networks

Mesh networks typically require powered devices to act as routers, relaying messages back to the central coordinator (the radio connected to Home Assistant). Philips lights usually function as routers, while Ikea, Sengled, and generic Tuya bulbs often do not. If devices become unresponsive or fail to respond to commands, Adaptive Lighting can exacerbate the issue. Use network maps (available in ZHA, zigbee2mqtt, deCONZ, and ZWaveJS UI) to evaluate your network health. Smart plugs can be an affordable way to add more routers to your network.

For most Zigbee networks, **using groups is essential for optimal performance**. For example, if you want to use Adaptive Lighting in a hallway with six bulbs, adding each bulb individually to the Adaptive Lighting configuration could overwhelm the network with commands. Instead, create a group in your Zigbee software (not a regular Home Assistant group) and add that single group to the Adaptive Lighting configuration. This sends a single broadcast command to adjust all bulbs, improving response times and keeping the bulbs in sync.

As a rule of thumb, if you always control lights together (e.g., bulbs in a ceiling fixture), they should be in a Zigbee group. Expose only the group (not individual bulbs) in Home Assistant Dashboards and external systems like Google Home or Apple HomeKit.

### :rainbow: Light Colors Not Matching

Bulbs from different manufacturers or models may have varying color temperature specifications. For instance, if you have two Adaptive Lighting configurations—one with only Philips Hue White Ambiance bulbs and another with a mix of Philips Hue White Ambiance and Sengled bulbs—the Philips Hue bulbs may appear to have different color temperatures despite having identical settings.

To resolve this:

1.  Include only bulbs of the same make and model in a single Adaptive Lighting configuration.
2.  Rearrange bulbs so that different color temperatures are not visible simultaneously.

### :bulb: Bulb-Specific Issues

Certain bulbs may have issues with long light transition commands:

- [Sengled Z01-A19NAE26](https://www.zigbee2mqtt.io/devices/Z01-A19NAE26.html#sengled-z01-a19nae26): If Adaptive Lighting sends a long transition time (like the default 45 seconds), and the bulb is turned off during that time, it may turn back on after approximately 10 seconds to continue the transition command. Since the bulb is turning itself on, there will be no obvious trigger in Home Assistant or other logs indicating the cause of the light turning on. To fix this, set a much shorter transition time, such as 1 second.
- Additionally, these bulbs may perform poorly in enclosed "dome" style ceiling lights, particularly when hot. While most LEDs (even non-smart ones) state in the fine print that they do not support working in enclosed fixtures, in practice, more expensive bulbs like Philips Hue generally perform better. To resolve this issue, move the problematic bulbs to open-air fixtures.

## :bar_chart: Graphs!
These graphs were generated using the values calculated by the Adaptive Lighting sensor/switch(es).

#### :sunny: Sun Position
![cl_percent|690x131](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/6/5/657ff98beb65a94598edeb4bdfd939095db1a22c.PNG)

#### :thermometer: Color Temperature
![cl_color_temp|690x129](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/9/59e84263cbecd8e428cb08777a0413672c48dfcd.PNG)

#### :high_brightness: Brightness
![cl_brightness|690x130](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/8/58ebd994b62a8b1abfb3497a5288d923ff4e2330.PNG)

#### While using `adapt_until_sleep: true`
![image](https://user-images.githubusercontent.com/2219836/228949675-f9699624-8abc-466c-bb04-250ce0f495b8.png)


## :busts_in_silhouette: Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="http://www.nijho.lt/"><img src="https://avatars.githubusercontent.com/u/6897215?v=4?s=100" width="100px;" alt="Bas Nijholt"/><br /><sub><b>Bas Nijholt</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=basnijholt" title="Code">💻</a> <a href="#maintenance-basnijholt" title="Maintenance">🚧</a> <a href="https://github.com/basnijholt/adaptive-lighting/issues?q=author%3Abasnijholt" title="Bug reports">🐛</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/wrt54g"><img src="https://avatars.githubusercontent.com/u/85389871?v=4?s=100" width="100px;" alt="Sven Serlier"/><br /><sub><b>Sven Serlier</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=wrt54g" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/willpuckett"><img src="https://avatars.githubusercontent.com/u/12959477?v=4?s=100" width="100px;" alt="Will Puckett"/><br /><sub><b>Will Puckett</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=willpuckett" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/vapescherov"><img src="https://avatars.githubusercontent.com/u/9620482?v=4?s=100" width="100px;" alt="vapescherov"/><br /><sub><b>vapescherov</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=vapescherov" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/travisp"><img src="https://avatars.githubusercontent.com/u/165698?v=4?s=100" width="100px;" alt="Travis Pew"/><br /><sub><b>Travis Pew</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=travisp" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/sindrebroch"><img src="https://avatars.githubusercontent.com/u/10772085?v=4?s=100" width="100px;" alt="Sindre Broch"/><br /><sub><b>Sindre Broch</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=sindrebroch" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Shulyaka"><img src="https://avatars.githubusercontent.com/u/2741408?v=4?s=100" width="100px;" alt="Denis Shulyaka"/><br /><sub><b>Denis Shulyaka</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Shulyaka" title="Code">💻</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/RubenKelevra"><img src="https://avatars.githubusercontent.com/u/614929?v=4?s=100" width="100px;" alt="@RubenKelevra"/><br /><sub><b>@RubenKelevra</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=RubenKelevra" title="Documentation">📖</a> <a href="https://github.com/basnijholt/adaptive-lighting/commits?author=RubenKelevra" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Repsionu"><img src="https://avatars.githubusercontent.com/u/46962963?v=4?s=100" width="100px;" alt="Jüri Rebane"/><br /><sub><b>Jüri Rebane</b></sub></a><br /><a href="#translation-Repsionu" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/quantumlemur"><img src="https://avatars.githubusercontent.com/u/229782?v=4?s=100" width="100px;" alt="quantumlemur"/><br /><sub><b>quantumlemur</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=quantumlemur" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Oekn5w"><img src="https://avatars.githubusercontent.com/u/38046255?v=4?s=100" width="100px;" alt="Michael Kirsch"/><br /><sub><b>Michael Kirsch</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Oekn5w" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://nicholai.dev/"><img src="https://avatars.githubusercontent.com/u/7280931?v=4?s=100" width="100px;" alt="Nicholai Nissen"/><br /><sub><b>Nicholai Nissen</b></sub></a><br /><a href="#translation-Nicholaiii" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/myhrmans"><img src="https://avatars.githubusercontent.com/u/14261388?v=4?s=100" width="100px;" alt="Martin Myhrman"/><br /><sub><b>Martin Myhrman</b></sub></a><br /><a href="#translation-myhrmans" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/mpeterson"><img src="https://avatars.githubusercontent.com/u/11870?v=4?s=100" width="100px;" alt="Michel Peterson"/><br /><sub><b>Michel Peterson</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=mpeterson" title="Code">💻</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/MangoScango"><img src="https://avatars.githubusercontent.com/u/7623678?v=4?s=100" width="100px;" alt="MangoScango"/><br /><sub><b>MangoScango</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=MangoScango" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Lynilia"><img src="https://avatars.githubusercontent.com/u/89228568?v=4?s=100" width="100px;" alt="Lynilia"/><br /><sub><b>Lynilia</b></sub></a><br /><a href="#translation-Lynilia" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/LukaszP2"><img src="https://avatars.githubusercontent.com/u/44735995?v=4?s=100" width="100px;" alt="LukaszP2"/><br /><sub><b>LukaszP2</b></sub></a><br /><a href="#translation-LukaszP2" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/jowgn"><img src="https://avatars.githubusercontent.com/u/24966042?v=4?s=100" width="100px;" alt="Joscha Wagner"/><br /><sub><b>Joscha Wagner</b></sub></a><br /><a href="#translation-jowgn" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/josecarlosfernandez"><img src="https://avatars.githubusercontent.com/u/624242?v=4?s=100" width="100px;" alt="skdzzz"/><br /><sub><b>skdzzz</b></sub></a><br /><a href="#translation-josecarlosfernandez" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/itssimon"><img src="https://avatars.githubusercontent.com/u/1176585?v=4?s=100" width="100px;" alt="Simon Gurcke"/><br /><sub><b>Simon Gurcke</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=itssimon" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="http://hypfer.de/"><img src="https://avatars.githubusercontent.com/u/974410?v=4?s=100" width="100px;" alt="Sören Beye"/><br /><sub><b>Sören Beye</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Hypfer" title="Code">💻</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="http://medium.com/@hudsonbrendon"><img src="https://avatars.githubusercontent.com/u/5201888?v=4?s=100" width="100px;" alt="Hudson Brendon"/><br /><sub><b>Hudson Brendon</b></sub></a><br /><a href="#translation-hudsonbrendon" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/gvssr"><img src="https://avatars.githubusercontent.com/u/61377476?v=4?s=100" width="100px;" alt="Gabriel Visser"/><br /><sub><b>Gabriel Visser</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=gvssr" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/glebsterx"><img src="https://avatars.githubusercontent.com/u/8779304?v=4?s=100" width="100px;" alt="Gleb"/><br /><sub><b>Gleb</b></sub></a><br /><a href="#translation-glebsterx" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/ghost"><img src="https://avatars.githubusercontent.com/u/10137?v=4?s=100" width="100px;" alt="Deleted user"/><br /><sub><b>Deleted user</b></sub></a><br /><a href="#translation-ghost" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://omg.dje.li/"><img src="https://avatars.githubusercontent.com/u/103232?v=4?s=100" width="100px;" alt="Avi Miller"/><br /><sub><b>Avi Miller</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Djelibeybi" title="Documentation">📖</a> <a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Djelibeybi" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/denysdovhan"><img src="https://avatars.githubusercontent.com/u/3459374?v=4?s=100" width="100px;" alt="Denys Dovhan"/><br /><sub><b>Denys Dovhan</b></sub></a><br /><a href="#translation-denysdovhan" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="http://davidstenbeck.com/"><img src="https://avatars.githubusercontent.com/u/3330933?v=4?s=100" width="100px;" alt="David Stenbeck"/><br /><sub><b>David Stenbeck</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Davst" title="Documentation">📖</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/danaues"><img src="https://avatars.githubusercontent.com/u/24459240?v=4?s=100" width="100px;" alt="Kevin Addeman"/><br /><sub><b>Kevin Addeman</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=danaues" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/covid10"><img src="https://avatars.githubusercontent.com/u/71146231?v=4?s=100" width="100px;" alt="covid10"/><br /><sub><b>covid10</b></sub></a><br /><a href="#translation-covid10" title="Translation">🌍</a> <a href="https://github.com/basnijholt/adaptive-lighting/commits?author=covid10" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/chishm"><img src="https://avatars.githubusercontent.com/u/18148723?v=4?s=100" width="100px;" alt="Michael Chisholm"/><br /><sub><b>Michael Chisholm</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=chishm" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/blueshiftlabs"><img src="https://avatars.githubusercontent.com/u/1445520?v=4?s=100" width="100px;" alt="Justin Paupore"/><br /><sub><b>Justin Paupore</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=blueshiftlabs" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/bedaes"><img src="https://avatars.githubusercontent.com/u/8410205?v=4?s=100" width="100px;" alt="bedaes"/><br /><sub><b>bedaes</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=bedaes" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/awashingmachine"><img src="https://avatars.githubusercontent.com/u/79043726?v=4?s=100" width="100px;" alt="awashingmachine"/><br /><sub><b>awashingmachine</b></sub></a><br /><a href="#translation-awashingmachine" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/claytonjn"><img src="https://avatars.githubusercontent.com/u/3850252?v=4?s=100" width="100px;" alt="Clayton Nummer"/><br /><sub><b>Clayton Nummer</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=claytonjn" title="Code">💻</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/robert-crandall"><img src="https://avatars.githubusercontent.com/u/86014438?v=4?s=100" width="100px;" alt="Robert Crandall"/><br /><sub><b>Robert Crandall</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=robert-crandall" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://mattforster.ca/"><img src="https://avatars.githubusercontent.com/u/3375444?v=4?s=100" width="100px;" alt="Matt Forster"/><br /><sub><b>Matt Forster</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=matt-forster" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://www.dfki.de/en/web/about-us/employee/person/maho10"><img src="https://avatars.githubusercontent.com/u/64665067?v=4?s=100" width="100px;" alt="Mark Niemeyer"/><br /><sub><b>Mark Niemeyer</b></sub></a><br /><a href="#translation-Mark-Niemeyer" title="Translation">🌍</a> <a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Mark-Niemeyer" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://www.linkedin.com/in/elliottplack/"><img src="https://avatars.githubusercontent.com/u/1827881?v=4?s=100" width="100px;" alt="Elliott Plack"/><br /><sub><b>Elliott Plack</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=talllguy" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/ngommers"><img src="https://avatars.githubusercontent.com/u/82467671?v=4?s=100" width="100px;" alt="ngommers"/><br /><sub><b>ngommers</b></sub></a><br /><a href="#translation-ngommers" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/deviantintegral"><img src="https://avatars.githubusercontent.com/u/255023?v=4?s=100" width="100px;" alt="Andrew Berry"/><br /><sub><b>Andrew Berry</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=deviantintegral" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/brebtatv"><img src="https://avatars.githubusercontent.com/u/10747062?v=4?s=100" width="100px;" alt="Tomáš Valigura"/><br /><sub><b>Tomáš Valigura</b></sub></a><br /><a href="#translation-brebtatv" title="Translation">🌍</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/th3w1zard1"><img src="https://avatars.githubusercontent.com/u/2219836?v=4?s=100" width="100px;" alt="Benjamin Auquite"/><br /><sub><b>Benjamin Auquite</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=th3w1zard1" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/skycarl"><img src="https://avatars.githubusercontent.com/u/43375685?v=4?s=100" width="100px;" alt="Skyler Carlson"/><br /><sub><b>Skyler Carlson</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=skycarl" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/firstof9"><img src="https://avatars.githubusercontent.com/u/1105672?v=4?s=100" width="100px;" alt="Chris"/><br /><sub><b>Chris</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=firstof9" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/raman325"><img src="https://avatars.githubusercontent.com/u/7243222?v=4?s=100" width="100px;" alt="Raman Gupta"/><br /><sub><b>Raman Gupta</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=raman325" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/igiannakas"><img src="https://avatars.githubusercontent.com/u/59056762?v=4?s=100" width="100px;" alt="igiannakas"/><br /><sub><b>igiannakas</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=igiannakas" title="Code">💻</a></td>
    </tr>
  </tbody>
  <tfoot>
    <tr>
      <td align="center" size="13px" colspan="7">
        <img src="https://raw.githubusercontent.com/all-contributors/all-contributors-cli/1b8533af435da9854653492b1327a23a4dbd0a10/assets/logo-small.svg">
          <a href="https://all-contributors.js.org/docs/en/bot/usage">Add your contributions</a>
        </img>
      </td>
    </tr>
  </tfoot>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->
