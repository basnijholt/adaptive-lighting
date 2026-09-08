<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [🌞 Adaptive Lighting (CDiT fork)](#-adaptive-lighting-cdit-fork)
  - [Installation](#installation)
    - [HACS — custom repository](#hacs--custom-repository)
    - [Manual install](#manual-install)
  - [Setup](#setup)
  - [What each profile creates](#what-each-profile-creates)
    - [Switches (3)](#switches-3)
    - [Number entities (5) — live-tunable sliders](#number-entities-5--live-tunable-sliders)
    - [Sensor entities (3) — graphable outputs](#sensor-entities-3--graphable-outputs)
  - [Tuning live](#tuning-live)
  - [Services](#services)
    - [`adaptive_lighting.apply`](#adaptive_lightingapply)
    - [`adaptive_lighting.change_switch_settings`](#adaptive_lightingchange_switch_settings)
  - [Sun source](#sun-source)
  - [Development](#development)
  - [Sync with upstream](#sync-with-upstream)
  - [Credits](#credits)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/CaseyRo/adaptive-lighting?include_prereleases&style=for-the-badge)](https://github.com/CaseyRo/adaptive-lighting/releases)
[![Upstream](https://img.shields.io/badge/fork_of-basnijholt%2Fadaptive--lighting-blue?style=for-the-badge)](https://github.com/basnijholt/adaptive-lighting)
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-134-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

---

> # ⚠️ This is the CDiT fork
>
> This repository is the [CDiT](https://github.com/CaseyRo)-opinionated fork of
> [`basnijholt/adaptive-lighting`](https://github.com/basnijholt/adaptive-lighting).
> It is **not a drop-in replacement** for the upstream HACS integration.
>
> ## 🙏 Huge thanks to the upstream team
>
> **None of this exists without [@basnijholt](https://github.com/basnijholt)
> and the 130+ contributors** to the original Adaptive Lighting project. The
> curve math, the `light.turn_on` interception, the HACS plumbing, the
> Pyodide simulator, the long tail of bug fixes from running this on
> thousands of real homes — that's *their* work. This fork is a thin opinion
> on top of a deep, mature codebase. If you're looking for the canonical,
> well-maintained, multi-feature integration that supports *everyone's* use
> case, **use upstream.** This fork only exists because CDiT's house has a
> narrower setup and the upstream config dialog was hard to tune at speed
> for one household.
>
> **Please star the upstream repo:**
> [github.com/basnijholt/adaptive-lighting](https://github.com/basnijholt/adaptive-lighting).
> If you find a bug in core curve math, light intercept, or any feature
> CDiT didn't change, report it there — that's where it'll actually get
> fixed and helps everyone, not just one CDiT household.
>
> **Differences from upstream:**
>
> 1. **Sectioned config dialog** — six collapsible groups (Targets, Daytime curve,
>    Sun schedule, Light control, Advanced, Diagnostics) replace upstream's
>    flat 40-field form. Native HA selectors throughout; reload-on-save via
>    `OptionsFlowWithReload`.
> 2. **Entity-driven sun timing** — point `sunrise_entity` / `sunset_entity`
>    at any sensor with `device_class: timestamp`. Defaults to the built-in
>    `sensor.sun_next_rising` / `sensor.sun_next_setting`. Sun2 sensors
>    (`sensor.sun2_dawn`, `sensor.sun2_astro_dawn`, etc.) work without code
>    changes — see "Recommended companions" below.
> 3. **Synthetic tanh curve** — brightness and color temperature follow a
>    smooth tanh ramp anchored at the two sun events, with a half-width you can
>    tune live (5-120 min, default 30). No `brightness_mode` selector to fiddle
>    with.
> 4. **Fewer features, on purpose** — sleep mode, take-over-control, manual
>    sun-time overrides, `only_once`, and `adapt_only_on_bare_turn_on` are
>    **removed**. Manual overrides are expected to live at the
>    scene/automation layer instead. The integration creates **three switches
>    per profile**, not four (no sleep-mode switch).
> 5. **Strict version break** — existing upstream config entries WILL NOT load.
>    The integration rejects them with a clear "delete and recreate" message
>    instead of silently migrating. Bump major version, recreate your one
>    config entry, move on.
>
> **Recommended companions:**
>
> - [**Sun2**](https://github.com/pnbruckner/ha-sun2) (HACS) provides civil,
>   nautical, and astronomical twilight sensors. Point `sunrise_entity` at
>   `sensor.sun2_astro_dawn` for the smoothest fade from deep night to dawn,
>   or `sensor.sun2_dawn` for civil twilight. Optional but recommended.
>
> **Minimum Home Assistant version: `2026.1.0`** (declared in `hacs.json`).
>
> ## ✨ What's new in 2.1
>
> Each profile now exposes **five live-tunable sliders** as `number`
> entities you can drop on any Lovelace card:
>
> - `number.<profile>_min_brightness` — night-floor brightness (1–100 %)
> - `number.<profile>_max_brightness` — peak-day brightness (1–100 %)
> - `number.<profile>_min_color_temp` — warmest tone (1000–10000 K)
> - `number.<profile>_max_color_temp` — coolest tone (1000–10000 K)
> - `number.<profile>_ramp_half_width` — curve ramp half-width (5–120 min)
>
> **Slider position is the runtime truth.** Move a slider on the dashboard
> and the curve picks it up on the next tick — no integration reload, no
> restart. Position survives HA restarts via `RestoreNumber`.
>
> **Options dialog and sliders stay in sync.** Opening the options dialog
> seeds the four range fields from the current slider values (not the
> stale setup defaults). Saving the dialog resets the sliders to the
> just-saved values — explicit gesture wins.
>
> Drop them on a dashboard:
>
> ```yaml
> type: entities
> entities:
>   - number.dining_mvp_min_brightness
>   - number.dining_mvp_max_brightness
>   - number.dining_mvp_min_color_temp
>   - number.dining_mvp_max_color_temp
>   - number.dining_mvp_ramp_half_width
> ```
>
> Also in 2.1: **entity friendly names are now readable.** A profile named
> "Dining MVP" exposes "Dining MVP", "Dining MVP Brightness", "Dining MVP
> Color" — short enough to fit HA's tightest cards. Existing entity_ids
> are preserved by the entity registry; automations keep working.
>
> ## ✨ What's new in 2.2
>
> Each profile now exposes **three read-only `sensor` entities** that
> publish the curve's current outputs alongside the sun's actual elevation
> — graphable as numerics by HA's recorder, the History panel,
> `apexcharts-card`, and `mini-graph-card`:
>
> - `sensor.<profile>_output_brightness` — current target brightness (%)
> - `sensor.<profile>_output_color_temp` — current target color temp (K)
> - `sensor.<profile>_sun_elevation` — solar elevation from `sun.sun` (°)
>
> The existing master-switch attributes (`brightness_pct`,
> `color_temp_kelvin`, the synthetic `sun_position` in [-1, +1]) are
> unchanged — anything reading them today keeps working. The sensors are
> the *graphable* version of the same data.
>
> Drop them on a dashboard with `apexcharts-card` to see the curve over time:
>
> ```yaml
> type: custom:apexcharts-card
> graph_span: 24h
> series:
>   - entity: sensor.dining_mvp_output_brightness
>   - entity: sensor.dining_mvp_output_color_temp
>   - entity: sensor.dining_mvp_sun_elevation
> ```

---

# 🌞 Adaptive Lighting (CDiT fork)

A Home Assistant custom component that adapts light brightness and color
temperature to a sun-driven tanh curve. Each profile owns a set of lights
and exposes three switches, five live-tunable sliders, and three graphable
sensors per profile.

## Installation

### HACS — custom repository

This is the **CDiT fork** of Adaptive Lighting and is **not** in the HACS default list (the upstream `basnijholt/adaptive-lighting` is — install that if you want the original). To use this fork, add it as a HACS **custom repository**:

1. Make sure [HACS](https://hacs.xyz) is installed.
2. In Home Assistant: **HACS** → top-right **⋮** → **Custom repositories**.
3. **Repository:** `https://github.com/CaseyRo/adaptive-lighting` — **Type:** `Integration` — click **Add**.
4. Search HACS for **Adaptive Lighting (CDiT)**, open it, and click **Download**.
5. **Restart Home Assistant.**
6. **Settings → Devices & Services → Add Integration →** search **Adaptive Lighting**.

> Note: this fork uses the same `adaptive_lighting` domain as upstream, so do **not** install both at once.

### Manual install

1. Download the latest release, or copy this repo.
2. Copy `custom_components/adaptive_lighting/` into your Home Assistant `config/custom_components/`.
3. **Restart Home Assistant**, then add via **Settings → Devices & Services → Add Integration**.

## Setup

UI-only — there is no YAML schema in this fork. Existing
`adaptive_lighting:` blocks in `configuration.yaml` are ignored.

1. Settings → Devices & Services → **Add Integration** → **Adaptive Lighting**.
2. Name the profile (e.g., `Kitchen`).
3. Click ⚙️ Configure on the new entry to open the sectioned options dialog
   and pick lights, sun-time entities, and curve bounds.

A profile can be **edited** any time via the same ⚙️ Configure menu — saving
reloads the integration via `OptionsFlowWithReload` (no restart needed).

## What each profile creates

For a profile named `Kitchen`:

### Switches (3)

| Entity | Role |
|---|---|
| `switch.kitchen` | Master on/off — when off, no adaptation runs |
| `switch.kitchen_brightness` | Toggle brightness adaptation only |
| `switch.kitchen_color` | Toggle color-temperature adaptation only |

### Number entities (5) — live-tunable sliders

| Entity | Range | Step | Persist |
|---|---|---|---|
| `number.kitchen_min_brightness` | 1–100 % | 1 | RestoreNumber |
| `number.kitchen_max_brightness` | 1–100 % | 1 | RestoreNumber |
| `number.kitchen_min_color_temp` | 1000–10000 K | 100 | RestoreNumber |
| `number.kitchen_max_color_temp` | 1000–10000 K | 100 | RestoreNumber |
| `number.kitchen_ramp_half_width` | 5–120 min | 1 | RestoreNumber |

Slider position is the runtime truth — the curve reads from the entity on
every tick. No integration reload on slider change. Values survive HA
restarts. The options dialog re-seeds the four range values from the
entities on open and overwrites them on save (explicit gesture wins).

**Ramp half-width** sets how long the curve takes to transition at each sun
event: the ramp spans the event ± this value, so the total transition is
twice the slider (default 30 min = the classic 1-hour tanh window). It has
**no options-dialog field** — the entity is the only knob, by design: it's
meant to be driven from automation (e.g., a Node-RED seasonal flow that
widens summer dusks and tightens winter ones). One value drives both the
sunrise and sunset ramps.

### Sensor entities (3) — graphable outputs

| Entity | Unit | Source |
|---|---|---|
| `sensor.kitchen_output_brightness` | % | `self._settings["brightness_pct"]` |
| `sensor.kitchen_output_color_temp` | K | `self._settings["color_temp_kelvin"]` |
| `sensor.kitchen_sun_elevation` | ° | `sun.sun.attributes.elevation` |

All three are `state_class: measurement` so HA's recorder graphs them as
continuous numeric series. Drop them into `apexcharts-card`,
`mini-graph-card`, or the built-in History panel.

The master switch also exposes the curve's internal values as attributes
(`brightness_pct`, `color_temp_kelvin`, synthetic `sun_position` in
[-1, +1], etc.) — those are unchanged from prior versions for diagnostic
use.

## Tuning live

Three ways to change what the curve does — pick the right gesture for the
right scope:

| Gesture | Scope | Persistence |
|---|---|---|
| Drag a number slider on a dashboard | Live, this profile, these bounds | RestoreNumber (survives restart) |
| Open the options dialog and save | All profile settings | `entry.options` (canonical) |
| Toggle the master / adapt switches | On/off for this profile | RestoreEntity (survives restart) |

## Services

This fork exposes two services. The upstream
`adaptive_lighting.set_manual_control` service is **removed** (take-over-control
was dropped — see Differences from upstream).

### `adaptive_lighting.apply`

Apply this profile's current curve values to its lights immediately. Useful
in automations that turn on a scene and want AL to take over.

```yaml
service: adaptive_lighting.apply
data:
  entity_id: switch.kitchen
  lights:
    - light.kitchen_ceiling
  turn_on_lights: true   # also flip the lights on if currently off
  transition: 2
```

### `adaptive_lighting.change_switch_settings`

Change one or more of this profile's settings at runtime. The change
persists until the next options-flow save or HA restart.

```yaml
service: adaptive_lighting.change_switch_settings
data:
  entity_id: switch.kitchen
  use_defaults: current      # | factory | configuration
  min_brightness: 20         # any subset of options-flow fields
  max_color_temp: 4500
```

The full per-service argument list lives in `services.yaml` and is
rendered into the HA Developer Tools → Services UI.

## Sun source

The curve is anchored at two `device_class: timestamp` sensors —
`sunrise_entity` and `sunset_entity` — configured in the options dialog.

**Defaults**: HA's built-in `sensor.sun_next_rising` and
`sensor.sun_next_setting`. These are always present.

**Recommended**: install [Sun2](https://github.com/pnbruckner/ha-sun2) and
point at `sensor.sun2_dawn` (civil twilight) or `sensor.sun2_astro_dawn`
(astronomical twilight) for a smoother fade from deep night to dawn. The
integration reads `hass.states.get(<entity_id>).state` and parses the
timestamp; any sensor with `device_class: timestamp` works.

The new `sensor.<profile>_sun_elevation` reads from HA's built-in `sun.sun`
entity's `elevation` attribute — independent of which timestamp source you
picked for the curve.

## Development

This is a CDiT-internal fork; PRs from outside are not the workflow. If
you want to dig in:

| Task | Command |
|---|---|
| Boot a dev HA with the component loaded | `./scripts/develop` |
| Run the test suite | `uv run pytest` |
| Run a specific test | `uv run pytest tests/test_sensor_platform.py` |
| Lint | `./scripts/lint` |
| Validate active OpenSpec changes | `openspec validate <change-name> --strict` |

Architecture, conventions, OpenSpec workflow, and the upstream-sync recipe
are documented in [`CLAUDE.md`](CLAUDE.md). The `openspec/` tree holds the
proposal/design/spec/tasks artifacts for every non-trivial change; archived
changes under `openspec/changes/archive/` are the historical record.

## Sync with upstream

```bash
git fetch upstream
git merge upstream/main         # or rebase, depending on local policy
# resolve conflicts under custom_components/adaptive_lighting/
```

Remote setup:

```
origin    git@github.com:CaseyRo/adaptive-lighting.git   (this fork, read-write)
upstream  https://github.com/basnijholt/adaptive-lighting.git   (read-only)
```

## Credits

This fork is a thin opinion on top of
[@basnijholt](https://github.com/basnijholt)'s work and the 130+ upstream
contributors. The curve math, the `light.turn_on` interception, the HACS
plumbing — that's *their* work. If you've never starred the upstream repo,
do it now: [github.com/basnijholt/adaptive-lighting](https://github.com/basnijholt/adaptive-lighting).

See [`CHANGELOG.md`](CHANGELOG.md) for the canonical list of CDiT-fork
changes since forking from upstream.
