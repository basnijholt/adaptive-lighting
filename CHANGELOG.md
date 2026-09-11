# Changelog — CDiT Adaptive Lighting fork

All notable CDiT-fork changes are documented here. The upstream
`basnijholt/adaptive-lighting` changelog is in upstream's release notes; this
file covers only changes specific to this fork.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

---

## Standing on the shoulders of giants

This fork builds on **[basnijholt/adaptive-lighting](https://github.com/basnijholt/adaptive-lighting)** —
years of work by [@basnijholt](https://github.com/basnijholt) and 130+
contributors. The curve math, light intercept, HACS distribution, simulator
webapp, and the long tail of edge cases the original handles correctly all
come from that codebase. This fork is a narrow set of opinions layered on a
deep, mature foundation; the credit for *making this idea work at all*
belongs upstream.

If you're not specifically a CDiT-style single-household installation, please
prefer the upstream integration — it's better-maintained, supports more use
cases, and has the entire community behind it. Issues with core curve math
or light handling belong on the upstream tracker, where they reach the
maintainers who can actually fix them for everyone.

---

## [2.5.0-cdit.1] — 2026-06-07

### Added

- **Live ramp half-width** (`add-runtime-ramp-width`) — `number.<profile>_ramp_half_width`,
  a 5–120 minute slider replacing the previously fixed 30-minute tanh ramp. The
  curve re-derives on change; no reload needed.

## [2.4.1-cdit.1] — 2026-06-07

### Fixed

- **Sun-event day-anchoring** — the curve collapsed to its minimum during summer
  afternoons because the two sun events were being anchored to the wrong day.

## [2.4.0-cdit.1] — 2026-06-05

### Changed

- **Range sliders renamed** to lower/upper, with friendlier defaults for a newly
  created profile.
- Ruff is fully green across the fork; lint no longer carries inherited errors.

## [2.3.1-cdit.1] — 2026-05-31

### Fixed

- New-group defaults, and section collapse defaults in the options flow.

### Removed

- The `main`-to-`master` sync workflow, upstream cruft — this fork uses `main`.

## [2.3.0-cdit.1] — 2026-05-31

Released as `v2.3.0-cdit.1`; there was never a `v2.2.0` tag, so the entries
below (originally drafted under 2.2.0) shipped here.

### Added

- **Ambient-lux gate** (`add-lux-target`) — a reduce-only brightness gate
  driven by an optional lux sensor, plus a `lux_reduction` sensor reporting
  the reduction as a percentage rather than the retained factor.
- **Fork identity** — own HACS name, own version badge, explicit upstream link.

### Fixed

- Options-flow conditional reveal, and saving with an empty lux sensor.


### Added

- **Three read-only `sensor` entities per profile** — `output_brightness`
  (%), `output_color_temp` (K), `sun_elevation` (°). They expose the
  curve's current target outputs alongside HA's built-in `sun.sun`
  elevation as graphable numerics with `state_class: measurement`, so
  the History panel, `apexcharts-card`, and `mini-graph-card` chart
  them natively. The existing master-switch attributes (`brightness_pct`,
  `color_temp_kelvin`, the synthetic `sun_position` in [-1, +1]) are
  unchanged.
- **Push-based sensor updates** via a per-entry dispatcher signal fired
  by the master switch after each curve tick. No polling, no duplicate
  curve math — sensors are pure readers of a runtime cache the master
  switch publishes to.
- **`sun_elevation` is sourced from `sun.sun.attributes.elevation`** on
  every curve tick. If `sun.sun` is missing or the attribute is absent
  (rare; can happen during very early HA startup), the sensor renders
  as `unknown` for that tick — the other two sensors continue updating
  normally.
- **Fifth live-tunable `number` entity: `ramp_half_width`** (5–120 min) —
  completes the runtime curve-control set alongside the four range bounds
  (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`).
  It tunes the tanh ramp half-width around each sun event live and persists
  via `RestoreNumber`; unlike the four range fields it is not surfaced in the
  options dialog. Shipped earlier without a changelog entry — recorded here
  for completeness.

### Changed

- **`manifest.json` version bumped to `2.2.0-cdit.1`.** Minor bump; no
  breaking config-entry changes — existing 2.1 entries upgrade in place
  and gain the three new sensor entities on next setup.

### Migration

No user action required. Restart HA after upgrade and the three new
sensors appear under each profile's device page. Add them to a Lovelace
card or `apexcharts-card` to start graphing.

---

## [2.1.0-cdit.1] — 2026-05-16

### Added

- **Four live-tunable `number` entities per profile** — `min_brightness`,
  `max_brightness`, `min_color_temp`, `max_color_temp`. Drop the four
  sliders onto any Lovelace card to tune the curve from the dashboard
  without opening the options dialog. Slider position persists across
  Home Assistant restarts via `RestoreNumber`.
- **Curve math reads the runtime values from the entities on every tick**
  (with a fallback to `entry.options` when an entity is unavailable, e.g.,
  during early-setup races). Slider changes take effect on the next
  curve evaluation — no integration reload, no restart.
- **Options-flow opens with current slider values, not stale options**
  — if you tweaked the slider on the dashboard, the dialog shows the
  current value, not the value you typed in at setup. Saving the dialog
  resets the sliders to the just-saved values (explicit gesture wins).

### Changed

- **Entity friendly names use HA's `has_entity_name` composition.** For a
  profile named "Dining MVP" you now see "Dining MVP", "Dining MVP
  Brightness", "Dining MVP Color" on the dashboard instead of "Adaptive
  Lighting Adapt Brightness dining_mvp_lights" (which truncated to
  "Adaptive Lighting Adapt Br…"). Existing entity_ids are preserved by
  the entity registry — automations and scripts referencing them keep
  working.
- **`manifest.json` version bumped to `2.1.0-cdit.1`.** Minor bump; no
  breaking config-entry changes — existing 2.0 entries upgrade in place
  and gain the four new number entities on next setup.

### Migration

No user action required for existing 2.0 installs — restart HA after the
upgrade and the four new entities appear under each profile's device
page, seeded with that profile's current options values.

---

## [2.0.0-cdit.1] — Unreleased

The first major CDiT release. **Breaking change**: existing upstream config
entries will not load — see "Upgrading" below.

### Added

- **Sectioned options dialog** rendered via HA's `section()` helper. Six
  groups (Targets, Daytime curve, Sun schedule, Light control, Advanced,
  Diagnostics) replace the upstream 40-field flat form.
- **Native HA selectors throughout** — `NumberSelector` (slider for
  brightness 1–100 %, box for color temp 1000–10000 K), `EntitySelector`
  (typed to `domain=sensor, device_class=timestamp` for sun events,
  `domain=light, multiple=True` for the light list), `BooleanSelector`.
- **Conditional field visibility** — `send_split_delay` only appears when
  its driver `separate_turn_on_commands` is enabled.
- **Entity-driven sun timing** — two new options `sunrise_entity` and
  `sunset_entity` accept any sensor with `device_class: timestamp`. Defaults
  to the built-in `sensor.sun_next_rising` / `sensor.sun_next_setting`.
  Plug in Sun2 (`sensor.sun2_dawn`, `sensor.sun2_astro_dawn`, etc.) without
  any code changes.
- **Synthetic tanh brightness/color-temp curve** with a hardcoded 30-minute
  ramp half-width around each sun event. Tunable in `const.py` via
  `RAMP_HALF_WIDTH_SECONDS` (currently `1800`).
- **`OptionsFlowWithReload`** — saving options reloads the integration
  cleanly without a manual reload.
- **Strict version-break guard** — `async_setup_entry` raises
  `ConfigEntryError` with a clear message when a config entry's version is
  older than the current major.
- **Sleep-switch tombstone cleanup** — on first load after upgrade,
  orphan `switch.adaptive_lighting_sleep_mode_*` entities owned by this
  integration are removed from the entity registry and logged at `INFO`.
- **Plain-language strings** — every label, description, and abort message
  rewritten to read like a sentence a human wrote, not engineer shorthand.
  Sections get a one-sentence framer at the top.

### Changed

- **`DEFAULT_MIN_BRIGHTNESS`**: `1` → `5`. 1 % reads as off on most bulbs;
  5 % is the dim-but-visible floor.
- **`DEFAULT_MIN_COLOR_TEMP`**: `2000 K` → `2200 K`. Less sodium-vapor
  orange; warmer-lamp tone.
- **Master switch icon**: `mdi:theme-light-dark` → `mdi:weather-sunny-alert`.
- **`adapt_color` switch icon**: `mdi:sun-thermometer` → `mdi:invert-colors`.
- **`adapt_brightness` switch icon**: `mdi:brightness-4` →
  `mdi:brightness-percent`.
- **Minimum Home Assistant version**: pinned to `2025.1.0` in
  `manifest.json`.
- **Manifest metadata** — `codeowners`, `documentation`, and `issue_tracker`
  now point to `CaseyRo/adaptive-lighting`.

### Removed

**21 configuration fields**, **1 entity**, **1 service**, all part of
upstream features that the CDiT fork does not use.

- **Sleep mode cluster** (6 fields + 1 entity):
  `sleep_brightness`, `sleep_rgb_or_color_temp`, `sleep_color_temp`,
  `sleep_rgb_color`, `sleep_transition`, `transition_until_sleep`. The
  `switch.adaptive_lighting_sleep_mode_<name>` entity is no longer created.
  Each profile now provides **three switches** (master, adapt_color,
  adapt_brightness) instead of four.
- **Manual sun timing** (8 fields):
  `sunrise_time`, `min_sunrise_time`, `max_sunrise_time`, `sunrise_offset`,
  `sunset_time`, `min_sunset_time`, `max_sunset_time`, `sunset_offset`.
  Replaced by the two `*_entity` options above.
- **Brightness curve shape** (3 fields):
  `brightness_mode`, `brightness_mode_time_dark`,
  `brightness_mode_time_light`. The curve is now always a tanh ramp.
- **Take-over-control cluster** (4 fields):
  `take_over_control`, `take_over_control_mode`, `detect_non_ha_changes`,
  `autoreset_control_seconds`. Manual overrides are expected to live at
  the scene/automation layer.
- **Anti-AL flags** (2 fields):
  `only_once`, `adapt_only_on_bare_turn_on`. If you don't want continuous
  adaptation on a light, don't run AL on that light.
- **Service**:
  `adaptive_lighting.set_manual_control` no longer exists. The dependent
  state machine in `switch.py` and `AdaptiveLightingManager` remains as
  dead code in this release; follow-up cleanup will delete it.

### Migration / upgrading from upstream

1. Update via HACS (or copy `custom_components/adaptive_lighting/` over your
   existing install).
2. Restart Home Assistant.
3. The existing config entry shows as "failed to load" with the message
   "Adaptive Lighting v2 (CDiT fork) is incompatible with the existing
   config entry."
4. Delete the failed entry: **Settings → Devices & Services → Adaptive
   Lighting → ⋮ → Delete**.
5. Add a fresh entry: **Settings → Devices & Services → Add Integration →
   Adaptive Lighting**.
6. Open the new entry's **Configure** dialog and walk through the six
   sections.
7. (Optional) Install [Sun2](https://github.com/pnbruckner/ha-sun2) via
   HACS and point `sunrise_entity` / `sunset_entity` at one of its sensors.

### Internal

- `color_and_brightness.py`: rewritten. `SunLightSettings` is now a pure
  curve-math dataclass with 5 fields. Sun event timestamps are passed in
  as arguments by the caller (which reads them from HA entities) rather
  than computed via `astral`.
- `config_flow.py`: rewritten. ~250 LOC instead of 175 LOC, but each
  section, selector factory, and conditional is now isolated and testable.
- `__init__.py`: adds version-check + tombstone-cleanup guards at the
  top of `async_setup_entry`.
- Total integration code shrank by **~400 LOC** despite the new schema
  builder.

### Known limitations

- `AdaptiveLightingManager` (in `switch.py`) still contains the
  manual-control bookkeeping infrastructure. The branches that would
  populate it are now dead code (the relevant `AdaptiveSwitch` attributes
  are bridge stubs hardcoded to `False`), but the bookkeeping dicts and
  helper methods remain. Cleanup is deferred to a follow-up change.
- Locale files other than `en.json` are out of sync with the new schema
  and may render English strings until they are re-translated. Out of
  scope for this release.
- `astral` is still a transitive dependency. The curve-evaluation path
  no longer imports it, so pruning is just a `pyproject.toml` edit when
  the package as a whole stops using it.
