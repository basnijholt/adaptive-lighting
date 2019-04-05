# Circadian Lighting [[Home Assistant](https://www.home-assistant.io/) Component]
## Stay healthier and sleep better by syncing your lights with natural daylight to maintain your circadian rhythm!

![Circadian Light Rhythm|690x287](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/f/5fe7a780e9f8905fea4d1cbb66cdbe35858a6e36.jpg)

Circadian Lighting slowly synchronizes your color changing lights with the regular naturally occuring color temperature of the sky throughout the day. This gives your environment a more natural feel, with cooler hues during the midday and warmer tints near twilight and dawn.

In addition, Circadian Lighting can set your lights to a nice cool white at 1% in “Sleep” mode, which is far brighter than starlight but won’t reset your circadian rhythm or break down too much rhodopsin in your eyes.


<details><summary>Expand for articles explaining the benefits of maintaining a natural Circadian rhythm</summary>
* [Circadian Rhythms - National Institute of General Medical Sciences](https://www.nigms.nih.gov/Education/Pages/Factsheet_CircadianRhythms.aspx)
* [Circadian Rhythms Linked to Aging and Well-Being | Psychology Today](https://www.psychologytoday.com/us/blog/the-athletes-way/201306/circadian-rhythms-linked-aging-and-well-being)
* [Maintaining a daily rhythm is important for mental health, study suggests - CNN](https://www.cnn.com/2018/05/15/health/circadian-rhythm-mood-disorder-study/index.html)
* [How Nobel Winning Circadian Rhythm Research Benefits Pregnancy](https://www.healthypregnancy.com/how-nobel-prize-winning-circadian-rhythms-research-benefits-a-healthy-pregnancy/)
* [Body Clock & Sleep - National Sleep Foundation](https://sleepfoundation.org/sleep-topics/sleep-drive-and-your-body-clock)
</details>

### Visit the [Wiki](https://github.com/claytonjn/hass-circadian_lighting/wiki) for more information.
<hr>

## Basic Installation/Configuration Instructions:

#### Files - ALL THREE REQUIRED!
* [config/custom_components/circadian_lighting/\_\_init__.py](https://raw.githubusercontent.com/claytonjn/hass-circadian_lighting/master/custom_components/circadian_lighting/__init__.py)
* [config/custom_components/circadian_lighting/sensor.py](https://raw.githubusercontent.com/claytonjn/hass-circadian_lighting/master/custom_components/circadian_lighting/sensor.py)
* [config/custom_components/circadian_lighting/switch.py](https://raw.githubusercontent.com/claytonjn/hass-circadian_lighting/master/custom_components/circadian_lighting/switch.py)

#### Component Configuration:
```yaml
# Example configuration.yaml entry
circadian_lighting:
```
[_Advanced Configuration_](https://github.com/claytonjn/hass-circadian_lighting/wiki/Advanced-Configuration#component-configuration-variables)

#### Switch Configuration:
```yaml
# Example configuration.yaml entry
switch:
  - platform: circadian_lighting
    lights_ct:
      - light.desk
      - light.lamp
```
Switch configuration variables:
* **name** (_Optional_): The name to use when displaying this switch.
* **lights_ct** (_Optional_): array: List of light entities which should be set in mireds.
* **lights_rgb** (_Optional_): array: List of light entities which should be set in RGB.
* **lights_xy** (_Optional_): array: List of light entities which should be set in XY.
* **lights_brightness** (_Optional_): array: List of light entities which should only have brightness adjusted.

[_Advanced Configuration_](https://github.com/claytonjn/hass-circadian_lighting/wiki/Advanced-Configuration#switch-configuration-variables)
