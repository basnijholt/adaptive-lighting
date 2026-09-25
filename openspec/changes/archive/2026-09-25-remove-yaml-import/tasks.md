## 1. Remove the YAML import path

- [x] 1.1 Delete YAML `CONFIG_SCHEMA`, `_all_unique_names`, `async_setup`, `reload_configuration_yaml` and the `hass.config.entry_updated` listener; add `cv.config_entry_only_config_schema`
- [x] 1.2 Delete `async_step_import` and the `yaml_managed` abort in the options flow
- [x] 1.3 Delete `_DOMAIN_SCHEMA`, `_yaml_validation_tuples`, `maybe_coerce`
- [x] 1.4 Drop `no_data` / `yaml_managed` strings and the yaml_managed test
- [x] 1.5 Tests, ruff and CI (hassfest, HACS, pytest) green
