# Circadian Lighting [[Home Assistant](https://www.home-assistant.io/) Component]
## Stay healthier and sleep better by syncing your lights with natural daylight to maintain your circadian rhythm!

![Circadian Light Rhythm|690x287](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/f/5fe7a780e9f8905fea4d1cbb66cdbe35858a6e36.jpg)

Circadian Lighting slowly synchronizes your color changing lights with the regular naturally occurring color temperature of the sky throughout the day. This gives your environment a more natural feel, with cooler hues during the midday and warmer tints near twilight and dawn.

In addition, Circadian Lighting can set your lights to a nice cool white at 1% in “Sleep” mode, which is far brighter than starlight but won’t reset your circadian rhythm or break down too much rhodopsin in your eyes.


<details><summary>Expand for articles explaining the benefits of maintaining a natural Circadian rhythm</summary>
  
* [Circadian Rhythms - National Institute of General Medical Sciences](https://www.nigms.nih.gov/Education/Pages/Factsheet_CircadianRhythms.aspx)
* [Circadian Rhythms Linked to Aging and Well-Being | Psychology Today](https://www.psychologytoday.com/us/blog/the-athletes-way/201306/circadian-rhythms-linked-aging-and-well-being)
* [Maintaining a daily rhythm is important for mental health, study suggests - CNN](https://www.cnn.com/2018/05/15/health/circadian-rhythm-mood-disorder-study/index.html)
* [How Nobel Winning Circadian Rhythm Research Benefits Pregnancy](https://www.healthypregnancy.com/how-nobel-prize-winning-circadian-rhythms-research-benefits-a-healthy-pregnancy/)
* [Body Clock & Sleep - National Sleep Foundation](https://sleepfoundation.org/sleep-topics/sleep-drive-and-your-body-clock)
* [How our body’s circadian clocks affect our health beyond sleep](https://www.theverge.com/2018/6/12/17453398/sleep-circadian-code-satchin-panda-clock-health-science)

</details>

### Visit the [Wiki](https://github.com/claytonjn/hass-circadian_lighting/wiki) for more information.
<hr>

## Basic Installation/Configuration Instructions:

#### Installation:
Install `custom_component` files automatically using [HACS](https://github.com/claytonjn/hass-circadian_lighting/wiki/Installation-Instructions#hacs) or [Custom Updater](https://github.com/claytonjn/hass-circadian_lighting/wiki/Installation-Instructions#custom-updater), or install [Manually](https://github.com/claytonjn/hass-circadian_lighting/wiki/Installation-Instructions#manual-installation).

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

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

<hr>

### Graphs!
These graphs were generated using the values calculated by the Circadian Lighting sensor/switch(es).

##### Sun Position:
![cl_percent|690x131](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/6/5/657ff98beb65a94598edeb4bdfd939095db1a22c.PNG)

##### Color Temperature:
![cl_colortemp|690x129](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/9/59e84263cbecd8e428cb08777a0413672c48dfcd.PNG)

##### Brightness:
![cl_brightness|690x130](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/8/58ebd994b62a8b1abfb3497a5288d923ff4e2330.PNG)
