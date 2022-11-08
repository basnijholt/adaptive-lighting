[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-23-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->
![Version](https://img.shields.io/github/v/release/basnijholt/adaptive-lighting?style=for-the-badge)

# Adaptive Lighting component for Home Assistant

![](https://github.com/home-assistant/brands/raw/b4a168b9af282ef916e120d31091ecd5e3c35e66/core_integrations/adaptive_lighting/icon.png)

_Try out this code by adding https://github.com/basnijholt/adaptive-lighting to your custom repos in [HACS (Home Assistant Community Store)](https://hacs.xyz/) and install it!_


The `adaptive_lighting` platform changes the settings of your lights throughout the day.
It uses the position of the sun to calculate the color temperature and brightness that is most fitting for that time of the day.
Scientific research has shown that this helps to maintain your natural circadian rhythm (your biological clock) and might lead to improved sleep, mood, and general well-being.

In practical terms, this means that after the sun sets, the brightness of your lights will decrease to a certain minimum brightness, while the color temperature will be at its coolest color temperature at noon, after which it will decrease and reach its warmest color at sunset.
Around sunrise, the opposite will happen.

Additionally, the integration provides a way to define and set your lights in "sleep mode".
When "sleep mode" is enabled, the lights will be at a minimal brightness and have a very warm color.

The integration creates 4 switches (in this example the component's name is `"living_room"`):
1. `switch.adaptive_lighting_living_room`, which turns the Adaptive Lighting integration on or off. It has several attributes that show the current light settings.
2. `switch.adaptive_lighting_sleep_mode_living_room`, which when activated, turns on "sleep mode" (you can set a specific `sleep_brightness` and `sleep_color_temp`).
3. `switch.adaptive_lighting_adapt_brightness_living_room`, which sets whether the integration should adapt the brightness of the lights (if supported by the light).
4. `switch.adaptive_lighting_adapt_color_living_room`, which sets whether the integration should adapt the color of the lights (if supported by the light).

## Taking back control

Although having your lights automatically adapt is great most of the time, there might be times at which you want to set the lights to a different color/brightness and keep it that way.
For this purpose, the integration (when `take_over_control` is enabled) automatically detects whether someone (e.g., person toggling the light switch) or something (automation) changes the lights.
If this happens *and* the light is already on, the light that was changed gets marked as "manually controlled" and the Adaptive Lighting component will stop adapting that light until it turns off and on again (or if you use the service call `adaptive_lighting.set_manual_control`).
This mechanism works by listening to all `light.turn_on` calls that change the color or brightness and by noting that the component did not make the call.
Additionally, there is an option to detect all state changes (when `detect_non_ha_changes` is enabled), so also changes to the lights that were not made by a `light.turn_on` call (e.g., through an app or via something outside of Home Assistant.)
It does this by comparing a light's state to Adaptive Lighting's previously used settings.
Whenever a light gets marked as "manually controlled", an `adaptive_lighting.manual_control` event is fired, such that one can use this information in automations.

## Configuration

This integration is both fully configurable through YAML _and_ the frontend. (**Configuration** -> **Integrations** -> **Adaptive Lighting**, **Adaptive Lighting** -> **Options**)
Here, the options in the frontend and in YAML have the same names.

```yaml
# Example configuration.yaml entry
adaptive_lighting:
  lights:
    - light.living_room_lights
```

### Options
| option                    | description                                                                                                                                                                                                                   | required | default        | type    |
|---------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| -------- | -------------- | ------- |
| name                      | The name to use when displaying this switch.                                                                                                                                                                                  | False    | default        | string  |
| lights                    | List of light entities for Adaptive Lighting to control (may be empty).                                                                                                                                                       | False    | list           | []      |
| prefer_rgb_color          | Whether to use RGB color adjustment instead of native light color temperature.                                                                                                                                                | False    | False          | boolean |
| initial_transition        | How long the first transition is when the lights go from `off` to `on`.                                                                                                                                                       | False    | 1              | time    |
| sleep_transition          | How long the transition is when when "sleep mode" is toggled                                                                                                                                                                  | False    | 1              | time    |
| transition                | How long the transition is when the lights change, in seconds.                                                                                                                                                                | False    | 45             | integer |
| interval                  | How often to adapt the lights, in seconds.                                                                                                                                                                                    | False    | 90             | integer |
| min_brightness            | The minimum percent of brightness to set the lights to.                                                                                                                                                                       | False    | 1              | integer |
| max_brightness            | The maximum percent of brightness to set the lights to.                                                                                                                                                                       | False    | 100            | integer |
| min_color_temp            | The warmest color temperature to set the lights to, in Kelvin.                                                                                                                                                                | False    | 2000           | integer |
| max_color_temp            | The coldest color temperature to set the lights to, in Kelvin.                                                                                                                                                                | False    | 5500           | integer |
| sleep_brightness          | Brightness of lights while the sleep mode is enabled.                                                                                                                                                                         | False    | 1              | integer |
| sleep_rgb_or_color_temp   | Use either 'rgb_color' or 'color_temp' when in sleep mode.                                                                                                                                                                    | False    | 'color_temp'   | string  |
| sleep_rgb_color           | List of three numbers between 0-255, indicating the RGB color in sleep mode (only used when sleep_rgb_or_color_temp is 'rgb_color').                                                                                          | False    | `[255, 56, 0]` | list    |
| sleep_color_temp          | Color temperature of lights while the sleep mode is enabled (only used when sleep_rgb_or_color_temp is 'color_temp').                                                                                                         | False    | 1000           | integer |
| sunrise_time              | Override the sunrise time with a fixed time.                                                                                                                                                                                  | False    | time           |         |
| max_sunrise_time          | Make the virtual sun always rise at at most a specific time while still allowing for even earlier times based on the real sun                                                                                                 | False    | time           |         |
| sunrise_offset            | Change the sunrise time with a positive or negative offset.                                                                                                                                                                   | False    | 0              | time    |
| sunset_time               | Override the sunset time with a fixed time.                                                                                                                                                                                   | False    | time           |         |
| min_sunset_time           | Make the virtual sun always set at at least a specific time while still allowing for even later times based on the real sun                                                                                                   | False    | time           |         |
| sunset_offset             | Change the sunset time with a positive or negative offset.                                                                                                                                                                    | False    | 0              | time    |
| only_once                 | Whether to keep adapting the lights (false) or to only adapt the lights as soon as they are turned on (true).                                                                                                                 | False    | False          | boolean |
| take_over_control         | If another source calls `light.turn_on` while the lights are on and being adapted, disable Adaptive Lighting.                                                                                                                 | False    | True           | boolean |
| detect_non_ha_changes     | Whether to detect state changes and stop adapting lights, even not from `light.turn_on`. Needs `take_over_control` to be enabled. Note that by enabling this option, it calls 'homeassistant.update_entity' every 'interval'! | False    | False          | boolean |
| separate_turn_on_commands | Whether to use separate `light.turn_on` calls for color and brightness, needed for some types of lights                                                                                                                       | False    | False          | boolean |
| adapt_delay               | Wait time in seconds between light turn on, and Adaptive Lights applying changes to the light state. May avoid flickering.                                                                                                    | False    | 0              | integer |

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

### Services

`adaptive_lighting.**apply**` applies Adaptive Lighting settings to lights on demand.

| Service data attribute | Optional | Description                                                                                  |
| ---------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `entity_id`            | no       | The `entity_id` of the switch with the settings to apply.                                    |
| `lights`               | no       | A light (or list of lights) to apply the settings to.                                        |
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

# Other

See the documentation of the PR at https://deploy-preview-14877--home-assistant-docs.netlify.app/integrations/adaptive_lighting/ and [this video on Reddit](https://www.reddit.com/r/homeassistant/comments/jabhso/ha_has_it_before_apple_has_even_finished_it_i/) to see how to add the integration and set the options.

This integration was originally based of the great work of @claytonjn https://github.com/claytonjn/hass-circadian_lighting, but has been 100% rewritten and extended with new features.

# Having problems?
Please enable debug logging by putting this in `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.adaptive_lighting: debug
```
and after the problem occurs please create an issue with the log (`/config/home-assistant.log`).


### Graphs!
These graphs were generated using the values calculated by the Adaptive Lighting sensor/switch(es).

##### Sun Position:
![cl_percent|690x131](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/6/5/657ff98beb65a94598edeb4bdfd939095db1a22c.PNG)

##### Color Temperature:
![cl_color_temp|690x129](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/9/59e84263cbecd8e428cb08777a0413672c48dfcd.PNG)

##### Brightness:
![cl_brightness|690x130](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/8/58ebd994b62a8b1abfb3497a5288d923ff4e2330.PNG)

## Contributors

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
      <td align="center" valign="top" width="14.28%"><a href="https://robertheaton.com/"><img src="https://avatars.githubusercontent.com/u/1565857?v=4?s=100" width="100px;" alt="Rob Heaton"/><br /><sub><b>Rob Heaton</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=robert" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Repsionu"><img src="https://avatars.githubusercontent.com/u/46962963?v=4?s=100" width="100px;" alt="Jüri Rebane"/><br /><sub><b>Jüri Rebane</b></sub></a><br /><a href="#translation-Repsionu" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/quantumlemur"><img src="https://avatars.githubusercontent.com/u/229782?v=4?s=100" width="100px;" alt="quantumlemur"/><br /><sub><b>quantumlemur</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=quantumlemur" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Oekn5w"><img src="https://avatars.githubusercontent.com/u/38046255?v=4?s=100" width="100px;" alt="Michael Kirsch"/><br /><sub><b>Michael Kirsch</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Oekn5w" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://nicholai.dev/"><img src="https://avatars.githubusercontent.com/u/7280931?v=4?s=100" width="100px;" alt="Nicholai Nissen"/><br /><sub><b>Nicholai Nissen</b></sub></a><br /><a href="#translation-Nicholaiii" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/myhrmans"><img src="https://avatars.githubusercontent.com/u/14261388?v=4?s=100" width="100px;" alt="Martin Myhrman"/><br /><sub><b>Martin Myhrman</b></sub></a><br /><a href="#translation-myhrmans" title="Translation">🌍</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/mpeterson"><img src="https://avatars.githubusercontent.com/u/11870?v=4?s=100" width="100px;" alt="Michel Peterson"/><br /><sub><b>Michel Peterson</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=mpeterson" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/matt"><img src="https://avatars.githubusercontent.com/u/2709?v=4?s=100" width="100px;" alt="Matthew Mohrman"/><br /><sub><b>Matthew Mohrman</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=matt" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/MangoScango"><img src="https://avatars.githubusercontent.com/u/7623678?v=4?s=100" width="100px;" alt="MangoScango"/><br /><sub><b>MangoScango</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=MangoScango" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/Lynilia"><img src="https://avatars.githubusercontent.com/u/89228568?v=4?s=100" width="100px;" alt="Lynilia"/><br /><sub><b>Lynilia</b></sub></a><br /><a href="#translation-Lynilia" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/LukaszP2"><img src="https://avatars.githubusercontent.com/u/44735995?v=4?s=100" width="100px;" alt="LukaszP2"/><br /><sub><b>LukaszP2</b></sub></a><br /><a href="#translation-LukaszP2" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/jowgn"><img src="https://avatars.githubusercontent.com/u/24966042?v=4?s=100" width="100px;" alt="Joscha Wagner"/><br /><sub><b>Joscha Wagner</b></sub></a><br /><a href="#translation-jowgn" title="Translation">🌍</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/josecarlosfernandez"><img src="https://avatars.githubusercontent.com/u/624242?v=4?s=100" width="100px;" alt="skdzzz"/><br /><sub><b>skdzzz</b></sub></a><br /><a href="#translation-josecarlosfernandez" title="Translation">🌍</a></td>
    </tr>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/itssimon"><img src="https://avatars.githubusercontent.com/u/1176585?v=4?s=100" width="100px;" alt="Simon Gurcke"/><br /><sub><b>Simon Gurcke</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=itssimon" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="http://hypfer.de/"><img src="https://avatars.githubusercontent.com/u/974410?v=4?s=100" width="100px;" alt="Sören Beye"/><br /><sub><b>Sören Beye</b></sub></a><br /><a href="https://github.com/basnijholt/adaptive-lighting/commits?author=Hypfer" title="Code">💻</a></td>
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
