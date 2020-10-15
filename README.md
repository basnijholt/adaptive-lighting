# Adaptive Lighting component

Try out this code by adding https://github.com/basnijholt/adaptive-lighting to your custom repos in HACS and install it!

See the documentation at https://deploy-preview-14877--home-assistant-docs.netlify.app/integrations/adaptive_lighting/

See [this video on Reddit](https://www.reddit.com/r/homeassistant/comments/jabhso/ha_has_it_before_apple_has_even_finished_it_i/) to see how to add the integration and set the options.

# Having problems?
Please enable debug logging by putting this in `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.adaptive_lighting: debug
```
and after the problem occurs please create an issue with the log.


### Graphs!
These graphs were generated using the values calculated by the Adaptive Lighting sensor/switch(es).

##### Sun Position:
![cl_percent|690x131](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/6/5/657ff98beb65a94598edeb4bdfd939095db1a22c.PNG)

##### Color Temperature:
![cl_color_temp|690x129](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/9/59e84263cbecd8e428cb08777a0413672c48dfcd.PNG)

##### Brightness:
![cl_brightness|690x130](https://community-home-assistant-assets.s3.dualstack.us-west-2.amazonaws.com/original/3X/5/8/58ebd994b62a8b1abfb3497a5288d923ff4e2330.PNG)
