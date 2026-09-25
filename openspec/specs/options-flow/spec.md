# options-flow Specification

## Purpose
TBD - created by archiving change cdit-config-redesign. Update Purpose after archive.

## Requirements

### Requirement: Options dialog presents fields in named collapsible sections

The integration options dialog SHALL group its configurable fields into seven named sections, rendered using Home Assistant's `section()` schema helper. Section names and field membership SHALL match the layout below.

| Section | Default state | Fields |
|---|---|---|
| Targets | expanded | `lights` |
| Daytime curve | expanded | `min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`, `prefer_rgb_color` |
| Sun schedule | expanded | `sunrise_entity`, `sunset_entity` |
| Ambient lux | collapsed | `lux_sensor`, `target_lux` |
| Light control | expanded | `intercept`, `multi_light_intercept` |
| Advanced | collapsed | `interval`, `transition`, `initial_transition`, `adapt_delay`, `separate_turn_on_commands`, `send_split_delay`, `skip_redundant_commands` |
| Diagnostics | collapsed | `include_config_in_attributes` |

#### Scenario: User opens options dialog on a UI-managed entry

- **WHEN** the user navigates to Settings → Devices & Services → Adaptive Lighting → Configure
- **THEN** the form SHALL render seven sections in the order: Targets, Daytime curve, Sun schedule, Ambient lux, Light control, Advanced, Diagnostics
- **AND** the Ambient lux, Advanced, and Diagnostics sections SHALL be rendered in their collapsed state
- **AND** the Targets, Daytime curve, Sun schedule, and Light control sections SHALL be rendered expanded

#### Scenario: Each section contains only the fields specified for it

- **WHEN** the user expands any section in the options dialog
- **THEN** the fields shown in that section SHALL exactly match the field list in the table above for that section
- **AND** no field SHALL appear in more than one section

### Requirement: Conditional fields hide when their driver makes them irrelevant

Fields whose configuration is meaningful only under a specific value of another field ("driver") SHALL be omitted from the rendered schema when the driver value makes them inapplicable. When the driver value changes, the form SHALL be re-submitted to re-render with the updated field set.

The conditional pairs are:
- `send_split_delay` is conditional on `separate_turn_on_commands` being `true`.
- `target_lux` is conditional on `lux_sensor` being a non-empty string.

#### Scenario: send_split_delay hidden when transport mode disables it

- **WHEN** the user opens the options dialog with `separate_turn_on_commands` set to `false`
- **THEN** the Advanced section SHALL NOT include the `send_split_delay` field

#### Scenario: send_split_delay revealed when transport mode enables it

- **WHEN** the user toggles `separate_turn_on_commands` to `true` and submits the form
- **THEN** the options dialog SHALL re-render with `send_split_delay` present in the Advanced section
- **AND** the field SHALL accept values in the range 0–10000 milliseconds

#### Scenario: target_lux hidden when no lux sensor is selected

- **WHEN** the user opens the options dialog with `lux_sensor` set to `""` (empty)
- **THEN** the Ambient lux section SHALL show only the `lux_sensor` entity selector
- **AND** `target_lux` SHALL NOT appear

#### Scenario: target_lux revealed when lux sensor is selected

- **WHEN** the user selects a `lux_sensor` entity and submits the form
- **THEN** the options dialog SHALL re-render with `target_lux` present in the Ambient lux section
- **AND** the field SHALL accept values in the range 1–10000 lux

### Requirement: Sun event timing is read from configurable HA entities

The integration SHALL read sunrise and sunset event timestamps from two user-configured HA sensor entities exposed in the options dialog as `sunrise_entity` and `sunset_entity`. Both fields SHALL use an entity selector strictly typed to `domain: sensor` and `device_class: timestamp`. The integration SHALL NOT compute sun events from `astral` or any other internal sun-position library when both entities are configured.

#### Scenario: Default sun entities point to the built-in sun integration

- **WHEN** the user creates a new Adaptive Lighting config entry
- **THEN** `sunrise_entity` SHALL default to `sensor.sun_next_rising`
- **AND** `sunset_entity` SHALL default to `sensor.sun_next_setting`

#### Scenario: Selector filters to timestamp sensors only

- **WHEN** the user opens the entity picker for `sunrise_entity` or `sunset_entity`
- **THEN** only entities with `domain == "sensor"` and `device_class == "timestamp"` SHALL appear in the picker
- **AND** entities of domain `input_datetime` SHALL NOT appear

#### Scenario: Curve math reads from the configured entity

- **WHEN** the user sets `sunrise_entity` to `sensor.sun2_dawn` and saves
- **THEN** subsequent brightness curve calculations SHALL use the timestamp value of `sensor.sun2_dawn` as the morning sun event
- **AND** no call to `astral` SHALL occur in the curve evaluation path for this config entry

### Requirement: Brightness and color temperature follow a synthetic tanh curve

For each config entry, the integration SHALL synthesize the daytime brightness and color-temperature values using a hyperbolic-tangent curve anchored at the timestamps from `sunrise_entity` and `sunset_entity`, with a half-width `W` at each event. `W` SHALL be read at evaluation time from the profile's ramp half-width runtime entity as defined in the `runtime-range-controls` capability (default 30 minutes, falling back to `RAMP_HALF_WIDTH_SECONDS = 1800` when the entity is unavailable). The brightness value at time `t` SHALL follow:

- `t ≤ t_sunrise − W`: value = configured minimum
- `t_sunrise − W < t < t_sunrise + W`: value = tanh-interpolated minimum → maximum
- `t_sunrise + W ≤ t ≤ t_sunset − W`: value = configured maximum
- `t_sunset − W < t < t_sunset + W`: value = tanh-interpolated maximum → minimum
- `t ≥ t_sunset + W`: value = configured minimum

The same curve shape SHALL be applied to color temperature using `min_color_temp` and `max_color_temp` as the curve bounds. Both channels SHALL use the same `W` within a single evaluation.

The four bound values (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) SHALL be read at evaluation time from the four runtime range entities defined in the `runtime-range-controls` capability, with fallback to `entry.options[CONF_*]` when an entity is unavailable. The curve evaluation SHALL NOT read these four values directly from `entry.options` during normal operation.

#### Scenario: Brightness is at minimum well before sunrise

- **WHEN** the current time is more than `W` before the `sunrise_entity` timestamp
- **THEN** the computed brightness SHALL equal the current value of `number.adaptive_lighting_<name>_min_brightness`

#### Scenario: Brightness is exactly at the midpoint at the sunrise event

- **WHEN** the current time equals the `sunrise_entity` timestamp
- **THEN** the computed brightness SHALL equal `(current_min_brightness + current_max_brightness) / 2`
- **WHERE** `current_min_brightness` and `current_max_brightness` are the current states of the corresponding number entities

#### Scenario: Brightness is at maximum during the day

- **WHEN** the current time is between `sunrise_entity + W` and `sunset_entity − W`
- **THEN** the computed brightness SHALL equal the current value of `number.adaptive_lighting_<name>_max_brightness`

#### Scenario: Color temperature follows the same curve shape

- **WHEN** the current time is at any point on the curve
- **THEN** the computed color temperature SHALL follow the same tanh interpolation between the current values of `number.adaptive_lighting_<name>_min_color_temp` and `_max_color_temp` as the brightness curve does between the two brightness entities

#### Scenario: Bound values are taken from runtime entities, not from entry.options

- **GIVEN** `entry.options[CONF_MIN_BRIGHTNESS]` is 5
- **AND** `number.adaptive_lighting_<name>_min_brightness` is at 30
- **WHEN** the curve is evaluated at a time before `sunrise_entity − W`
- **THEN** the computed brightness SHALL equal 30 (the entity state), not 5 (`entry.options`)

#### Scenario: Curve width follows the ramp half-width entity

- **GIVEN** the profile's ramp half-width entity is at 60
- **WHEN** the curve is evaluated 45 minutes before the `sunset_entity` timestamp
- **THEN** the computed brightness SHALL lie strictly between the configured minimum and maximum (inside the widened down-ramp)
- **AND** with the entity at 30 the same instant would have produced the configured maximum (outside the default-width ramp)

### Requirement: All configurable fields use native HA selectors

Every field in the options dialog SHALL be rendered using a class from `homeassistant.helpers.selector`. The integration SHALL NOT use bare voluptuous primitive types (such as `vol.Coerce(int)` or custom `int_between`) as schema values for user-facing fields. Each field type SHALL be backed by the selector specified below.

| Field type | Selector |
|---|---|
| Numeric range (brightness, color temp) | `NumberSelector` with explicit `min`, `max`, `step`, `unit_of_measurement`, `mode=SLIDER` |
| Duration (seconds) | `NumberSelector` with `unit_of_measurement="s"`, `mode=BOX` |
| Duration (milliseconds) | `NumberSelector` with `unit_of_measurement="ms"`, `mode=BOX` |
| Boolean | `BooleanSelector` |
| Entity (lights) | `EntitySelector` with `domain="light"`, `multiple=True` |
| Entity (sun events) | `EntitySelector` with `domain="sensor"`, `device_class="timestamp"` |
| Entity (lux sensor) | `EntitySelector` with `domain="sensor"`, `device_class="illuminance"` |
| Lux target | `NumberSelector` with `min=1`, `max=10000`, `step=10`, `unit_of_measurement="lx"`, `mode=BOX` |

#### Scenario: Brightness ranges render as sliders

- **WHEN** the user opens the options dialog
- **THEN** `min_brightness` and `max_brightness` SHALL render as slider controls with range 1–100 and step 1
- **AND** both fields SHALL display the unit "%"

#### Scenario: Color temperature ranges render with explicit unit

- **WHEN** the user opens the options dialog
- **THEN** `min_color_temp` and `max_color_temp` SHALL render as numeric inputs with range 1000–10000 and step 100
- **AND** both fields SHALL display the unit "K"

#### Scenario: Booleans render as toggles

- **WHEN** the user opens the options dialog
- **THEN** every boolean field (`prefer_rgb_color`, `intercept`, `multi_light_intercept`, `separate_turn_on_commands`, `skip_redundant_commands`, `include_config_in_attributes`) SHALL render as a toggle switch control

#### Scenario: Lux sensor selector filters to illuminance sensors only

- **WHEN** the user opens the entity picker for `lux_sensor`
- **THEN** only entities with `domain == "sensor"` and `device_class == "illuminance"` SHALL appear in the picker
- **AND** temperature sensors, humidity sensors, and other non-illuminance sensors SHALL NOT appear

#### Scenario: Target lux renders as a number box with lux unit

- **WHEN** the user expands the Ambient lux section with a lux sensor configured
- **THEN** `target_lux` SHALL render as a numeric box input with range 1–10000, step 10
- **AND** the field SHALL display the unit "lx"

### Requirement: Ambient lux section shows the sensor's current reading

When a `lux_sensor` is configured and its state is numeric, the Ambient lux section description SHALL include the sensor's current reading via `description_placeholders`. This helps the user calibrate their `target_lux` to their actual space.

#### Scenario: Current lux reading shown in section description

- **GIVEN** `lux_sensor` is set to `sensor.office_illuminance`
- **AND** that sensor's current state is `"340"`
- **WHEN** the user opens the options dialog
- **THEN** the Ambient lux section description SHALL include the text "340 lx"

#### Scenario: No reading shown when sensor is not configured

- **GIVEN** `lux_sensor` is empty (not configured)
- **WHEN** the user opens the options dialog
- **THEN** the Ambient lux section description SHALL NOT include any lux reading number

#### Scenario: Fallback when sensor is unavailable

- **GIVEN** `lux_sensor` is configured but its state is `"unavailable"`
- **WHEN** the user opens the options dialog
- **THEN** the Ambient lux section description SHALL show a dash or "unavailable" in place of a numeric reading

### Requirement: Saving options reloads the integration via OptionsFlowWithReload

The options flow class SHALL extend `homeassistant.config_entries.OptionsFlowWithReload`. Saving changes through the options dialog SHALL trigger an integration reload without the integration manually calling `hass.config_entries.async_reload()`. Custom `async_unload_entry` plumbing for reload purposes SHALL NOT exist in the integration.

#### Scenario: Saving valid options reloads the integration

- **WHEN** the user changes any field in the options dialog and submits the form
- **THEN** the integration's `async_unload_entry` and `async_setup_entry` SHALL be invoked exactly once each as part of the reload
- **AND** the user SHALL NOT see a "restart Home Assistant" prompt

#### Scenario: Reload preserves entity registry identity

- **WHEN** the integration reloads after a save
- **THEN** the entity IDs of the AL device's switches SHALL remain unchanged
- **AND** no duplicate entities SHALL appear in the entity registry

### Requirement: Incompatible config entry versions fail to load with a clear error

The integration's `manifest.json` SHALL declare a major `version` that increments on every breaking config-schema change. On `async_setup_entry`, the integration SHALL reject any config entry whose stored `version` is older than the current major and SHALL raise `ConfigEntryError` with a user-facing message instructing the user to recreate the entry. No silent migration of dropped fields SHALL occur.

#### Scenario: Loading an upstream config entry on first upgrade

- **WHEN** Home Assistant attempts to set up a config entry whose `version` is 1 and the current integration version is 2
- **THEN** `async_setup_entry` SHALL raise `ConfigEntryError` with a message that names the incompatibility and instructs the user to delete and recreate the entry
- **AND** the integration SHALL NOT silently drop or migrate any fields from the old entry

#### Scenario: Loading a current-version entry succeeds

- **WHEN** Home Assistant attempts to set up a config entry whose `version` matches the current integration version
- **THEN** `async_setup_entry` SHALL complete without error

### Requirement: Sleep-mode switch entities left behind by upstream are auto-removed

On `async_setup_entry`, the integration SHALL scan the entity registry for entities whose `unique_id` matches the historical sleep-mode switch pattern owned by this integration's config entry and SHALL remove each match via `entity_registry.async_remove`. Each removal SHALL be logged at `INFO` level with the entity ID. The cleanup SHALL be idempotent: subsequent setups of the same entry SHALL find no matches and SHALL no-op.

#### Scenario: First load after upgrade removes the orphan sleep switch

- **WHEN** Home Assistant sets up a config entry on first launch after the version bump
- **AND** the entity registry contains a `switch.adaptive_lighting_sleep_mode_<name>` entity owned by this config entry
- **THEN** that entity SHALL be removed from the entity registry
- **AND** an `INFO` log entry SHALL be emitted naming the removed entity ID

#### Scenario: Subsequent loads find nothing to remove

- **WHEN** the integration has already removed the orphan sleep switch on a prior setup
- **AND** Home Assistant sets up the same config entry again
- **THEN** the entity registry scan SHALL find no matching entities
- **AND** no `INFO` log entry about sleep-switch removal SHALL be emitted

#### Scenario: Cleanup does not touch entities owned by other integrations

- **WHEN** the integration runs the sleep-switch cleanup
- **AND** another integration owns a similarly named entity (e.g., a user-created `switch.adaptive_lighting_sleep_mode_demo` template switch)
- **THEN** that foreign entity SHALL NOT be removed from the entity registry
