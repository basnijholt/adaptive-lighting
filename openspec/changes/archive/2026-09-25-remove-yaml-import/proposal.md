## Why

The README says setup is UI-only and that `adaptive_lighting:` blocks in `configuration.yaml` are ignored, but the code still carried the upstream YAML import path: a full `CONFIG_SCHEMA`, an `async_setup` that imported each YAML block as a config entry, `async_step_import`, a `yaml_managed` abort in the options flow, and a `hass.config.entry_updated` listener (registered on every entry setup and never removed) that ran `homeassistant.check_config`. Code and docs disagreed, and the listener leaked.

## What Changes

- Delete the YAML import path: the YAML `CONFIG_SCHEMA` and its helpers, `async_setup`, `reload_configuration_yaml` and its bus listener, `async_step_import`, the `yaml_managed` options-flow abort and the `no_data` / `yaml_managed` strings.
- `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`: a YAML block now gets HA's standard "set up from the UI" warning instead of a silent import.
- Remove the options-flow requirement that YAML-managed entries abort.

## Capabilities

### Modified Capabilities

- `options-flow`: the YAML-managed abort requirement is removed.

## Impact

`__init__.py`, `config_flow.py`, `const.py`, `strings.json`, `translations/en.json`, `tests/test_config_flow.py`. No config-entry version change: UI entries are untouched.
