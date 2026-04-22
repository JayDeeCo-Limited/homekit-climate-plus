# homekit_climate_plus — PRD

**Status:** v0.5.0 released. v1.0 stabilisation in progress (HACS default-store PR pending). This document is kept aligned with the shipped implementation; see [`CHANGELOG.md`](CHANGELOG.md) for per-release detail and [`docs/VENDORING.md`](docs/VENDORING.md) for the vendored-code resync policy.

## 1. Context & Problem

Home Assistant's HomeKit Bridge maps a `climate` entity to a HomeKit `HeaterCooler`-style accessory. That accessory exposes:

- Target temperature
- Heat / Cool / Off mode
- A single continuous `RotationSpeed` slider (0–100) for fan speed

What it **does not expose cleanly**:

- Named fan modes (`Auto`, `Silence`, `1`–`5` …) whose names fall outside HA's hard-coded `{low, middle, medium, high}` predefined set — the whole Fanv2 service is skipped.
- Swing modes (`Off`, `Vertical`, `Horizontal`, `3D`) whose names fall outside HA's `{on, both, horizontal, vertical}` set — the SwingMode characteristic is skipped.
- Preset modes (`away`, `eco`, `boost`) — no HomeKit surface at all.
- Secondary sensors (humidity, battery) — must be exposed on separate bridge accessories.

The standard workaround: create a template `fan.` entity proxying `climate.set_fan_mode`, expose both climate and fan to HomeKit as **two separate tiles**. This fragments the UX — one AC becomes a climate tile **and** a fan tile in Apple Home, with no correlation between them.

The underlying HomeKit Accessory Protocol (HAP) supports **linked services** — multiple services grouped under one accessory — and Homebridge AC plugins use this routinely. HA's built-in HomeKit Bridge does not, for climate entities.

## 2. Goal

Ship a HACS-installable custom component **`homekit_climate_plus`** that exposes HA climate entities to HomeKit via its **own self-contained bridge** — one rich HomeKit accessory per climate entity, with fan speed and swing-mode controls inside the same tile, plus companion preset-switch accessories and linked humidity / battery sensors. One climate tile, every primary control inside it; presets as explicitly-labelled sibling tiles for maximum Apple Home clarity. Zero patches or shims to HA core.

## 3. Non-Goals

- Not replacing HA's HomeKit Bridge — **run alongside** it. Users keep their existing bridge for non-climate entities.
- Not modifying, monkey-patching, or shim-ing HA core code at runtime.
- Not modifying the HAP spec, iOS Home app, or any Apple proprietary surface.
- Not writing new climate integrations (Daikin, Mitsubishi, etc.) — we consume existing `climate.*` entities.
- Not out-of-scope entity domains: media_player, cover, light. The integration is strictly for `climate.*`.

## 4. User Stories

- As an HA user with a Daikin AC (or any other climate entity whose fan/swing modes fall outside HA's predefined names), I pair the `homekit_climate_plus` bridge in Apple Home and see **one** AC accessory with fan speeds and swing inside, plus labelled preset-switch tiles next to it.
- As an HA user with a Mitsubishi / Fujitsu / ecobee / Nest climate entity, I get the same experience without device-specific code.
- As a HACS user, I install the integration and set it up either from **Settings → Devices & Services → Add Integration** or by dropping a YAML block into `configuration.yaml`.
- As a homelab power user, I can still override per-entity behaviour (fan-mode percent mapping, swing/preset toggles, linked sensors) in YAML.
- As a user on an HA monthly release, I don't worry about this plugin silently breaking — it has minimal runtime coupling to HA internals (only a small set of `homekit.const` / `homekit.iidmanager` / `homekit.models` imports that have been stable for years).

## 5. Architecture

### 5.1 Self-contained HomeKit bridge

`homekit_climate_plus` runs its own pyhap-based HomeKit bridge **inside the HA process**, independent of HA's built-in `homekit` integration.

```
iOS Apple Home app
    │
    ├─── HA HomeKit Bridge (stock)        — lights, switches, covers, sensors
    └─── homekit_climate_plus Bridge      — climate entities only
```

The user pairs the new bridge in Apple Home as a **second HomeKit bridge**, a one-time setup. Climate entities are excluded from the stock bridge (via its domain filter) and included in ours.

**Why this is robust:**

- No runtime patching of HA internals. We don't reach into HA core code paths.
- We own the whole surface: accessory lifecycle, characteristic wiring, bridge configuration, mDNS advertisement.
- HA core refactors to public `climate.*` APIs can still break us; our exposure to `homeassistant.components.homekit.*` internals is intentionally small and documented.
- All the code we ship is code we control. Vendored-in pieces are versioned in the repo — no silent drift.

### 5.2 Vendored code from home-assistant/core

To avoid reimplementing known-good work, we **vendor** the climate-accessory and supporting bridge code from HA's `homekit` integration (Apache 2.0, attribution preserved):

- `type_thermostats.py` — HA's `Thermostat` accessory class (the base we subclass)
- `accessories.py` — `HomeAccessory`, `HomeBridge`, `HomeDriver`, `HomeIIDManager` base classes
- `util.py` — temperature / state helpers used by the accessory classes

Files live under `custom_components/homekit_climate_plus/vendored/` with per-file attribution in `vendored/ATTRIBUTION.md` pointing at the exact upstream commit. The sync policy, allowed modifications, and re-sync procedure are documented in [`docs/VENDORING.md`](docs/VENDORING.md).

Brand assets ship in-tree at `custom_components/homekit_climate_plus/brand/{icon,icon@2x,logo,logo@2x}.png` and are served via HA 2026.3+'s brand-proxy API — no submission to `home-assistant/brands` is required for custom integrations.

### 5.3 Extended accessory class

On top of the vendored `Thermostat` class, `HeaterCoolerPlus` in `custom_components/homekit_climate_plus/type_thermostats.py` does three things the base class doesn't:

1. **Auto-detects fan modes that fall outside HA's predefined set** and builds a Fanv2 service with `Active`, `RotationSpeed`, and (where applicable) `SwingMode`. The mapping from fan-mode name to 1–100 slider position is auto-distributed (`round((i + 1) * 100 / N)`) unless a manual `fan_mode_mapping` is supplied.
2. **Auto-detects swing modes outside HA's predefined set** and attaches `SwingMode` to the same Fanv2 service. The "off" swing mode is the first entry lower-casing to `"off"`; the "on" swing mode is the first non-off entry.
3. **Optionally links a humidity sensor** as a separate `HumiditySensor` service on the same accessory. Battery linking comes for free from the vendored `HomeAccessory` base class when `linked_battery_sensor` is set.

A pyhap service cannot have characteristics added after creation — `configure_char` looks up an existing characteristic, it does not add one. So `HeaterCoolerPlus` decides upfront which of `{rotation speed, swing mode}` it needs and builds the Fanv2 once with the whole set.

### 5.4 Preset switches as standalone accessories

Early implementation attempted to expose preset modes as linked Switch services inside the main climate accessory. Apple Home renders repeated linked Switches of the same type as unlabelled "Switch 1 / 2 / 3" entries with no way to tell them apart. The shipped design instead registers one **standalone `PresetSwitchAccessory`** per non-`none` preset as a sibling on the same bridge:

- Each preset accessory gets its own `AccessoryInformation` service and a distinctive display name (e.g. `Air Conditioner — Away`).
- Toggling the switch calls `climate.set_preset_mode` with the preset name; toggling off reverts to the entity's `none` preset. Mutual exclusion is enforced by the HA-side state-update path — after any preset change, all sibling switches re-sync their `On` characteristic.
- Entities without a `none` preset (case-insensitive) get no preset switches. Turning a switch off would have no defined destination preset; we'd rather skip than guess.

### 5.5 Bridge lifecycle

`custom_components/homekit_climate_plus/bridge.py` owns the pyhap AccessoryDriver + Bridge lifecycle:

- Port defaults to `21065` but is user-configurable. Users with multiple HA-spawned HomeKit bridges (stock, accessory-mode TVs, sprinkler controllers) often need to pick a free port manually; there's no automatic probing.
- **Stable MAC address**: HA's `HomeDriver` initialises pyhap's `AccessoryDriver.state` with `EMPTY_MAC` (`00:00:00:00:00:00`). Left alone, every bridge advertises that, and iOS mis-routes `/pair-verify` requests based on shared identifiers. `HomeKitClimatePlusBridge` stamps a deterministic SHA-256-derived locally-administered MAC on `driver.state` before `async_start`.
- **Stable AIDs**: accessory IDs are derived from a SHA-256 of a structural key (`climate:<entity_id>` for climate accessories, `preset:<entity_id>:<preset>` for preset switches), not a running counter. Apple Home caches aid → display-name mapping; changing the AID of an accessory across restarts makes iOS show stale names.
- Pairing state and allocated IIDs persist under `.storage/homekit_climate_plus.<slug>` and `.storage/homekit.homekit_climate_plus_<slug>.iids`.
- Accessory registration is deferred until `EVENT_HOMEASSISTANT_STARTED` so `hass.states.get(entity_id)` has values for every climate entity — building them earlier silently skips any entity whose platform hasn't reached `add_entities` yet.
- pyhap's `AccessoryDriver` construction and `add_accessory` calls run in a worker thread (`hass.async_add_executor_job`) — both read on-disk state synchronously, which trips HA's event-loop watchdog when done inline.
- On `EVENT_HOMEASSISTANT_STOP`, the driver is stopped cleanly and the mDNS advertisement withdrawn.

### 5.6 Config schema

```yaml
homekit_climate_plus:
  name: Climate Bridge        # shown in Apple Home during pairing
  port: 21065                 # optional; any free TCP port
  pin: "739-42-618"           # optional; auto-generated if omitted
                              # (format XXX-XX-XXX; pyhap rejects banned
                              # codes like 12345678 or repeated digits)
  entity_config:
    climate.daikin_ac: {}
    climate.bedroom_ac:
      linked_swing_mode: false
    climate.lounge_heatpump:
      fan_mode_mapping:
        Auto: 14
        Silence: 28
        "1": 43
        "2": 57
        "3": 71
        "4": 86
        "5": 100
      linked_humidity_sensor: sensor.lounge_humidity
      linked_battery_sensor: sensor.lounge_heatpump_battery
```

With an empty `{}`, every supported feature is auto-configured from the entity's own attributes. Per-entity keys:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `linked_swing_mode` | bool | `true` | Attach a `SwingMode` characteristic on the Fanv2 service |
| `linked_preset_modes` | bool | `true` | Register one standalone Switch accessory per non-`none` preset |
| `fan_mode_mapping` | dict | auto-distributed | Override the default even-distribution of fan-mode names across the 1–100 HomeKit slider |
| `linked_humidity_sensor` | entity id | — | Link an external humidity sensor as a HomeKit HumiditySensor service |
| `linked_battery_sensor` | entity id | — | Link a battery-level sensor (handled by the vendored HomeAccessory base) |

### 5.7 UI config flow

`config_flow.py` exposes a standard Home Assistant **Add Integration** flow. The YAML path auto-imports into a matching config entry with source `import`, so YAML and UI users converge on the same `async_setup_entry` runtime. The **Configure** button on an existing entry opens a single-step options flow that edits the list of climate entities on the bridge — advanced per-entity settings (swing / preset toggles, linked sensors, fan-mode mapping) remain in YAML.

### 5.8 State sync

- **HA → HomeKit**: `async_track_state_change_event` on climate entity + any linked sensor. The base `HomeAccessory`'s state-tracking machinery drives the primary `Thermostat` service; `HeaterCoolerPlus.async_update_state` pushes our extra characteristics (rotation speed, swing, active) after calling `super()`.
- **HomeKit → HA**: per-characteristic `setter_callback` dispatches `climate.set_fan_mode`, `climate.set_swing_mode`, `climate.set_preset_mode`, or `climate.turn_off` depending on which characteristic was written.

## 6. Repository Layout

```
homekit-climate-plus/
├── custom_components/homekit_climate_plus/
│   ├── __init__.py                # async_setup / async_setup_entry / async_unload_entry
│   ├── manifest.json              # integration metadata (config_flow: true)
│   ├── const.py                   # DOMAIN, config keys, defaults
│   ├── config_flow.py             # UI config flow + options flow
│   ├── bridge.py                  # pyhap Bridge + stable-MAC + stable-AID
│   ├── type_thermostats.py        # HeaterCoolerPlus, PresetSwitchAccessory
│   ├── util.py                    # fan-mode mapping helpers
│   ├── brand/                     # in-tree brand icons (HA 2026.3+ proxy)
│   │   ├── icon.png               # 256×256
│   │   ├── icon@2x.png            # 512×512
│   │   ├── logo.png
│   │   └── logo@2x.png
│   ├── translations/
│   │   └── en.json
│   └── vendored/
│       ├── ATTRIBUTION.md         # Apache 2.0 per-file attribution + SHA
│       ├── __init__.py
│       ├── accessories.py         # copied from home-assistant/core
│       ├── type_thermostats.py    # copied from home-assistant/core
│       └── util.py                # copied from home-assistant/core
├── docs/
│   └── VENDORING.md               # vendored-code resync policy
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_setup.py
│   └── test_util.py
├── hacs.json                      # HACS metadata
├── .github/
│   └── workflows/
│       ├── hassfest.yaml          # home-assistant/actions/hassfest
│       ├── hacs.yaml              # hacs/action@main
│       └── pytest.yaml
├── LICENSE                        # MIT (our code)
├── NOTICE                         # Apache 2.0 notice for vendored HA code
├── README.md
├── CHANGELOG.md
├── PRD.md                         # this file
└── .gitignore
```

## 7. Release Status

- ✅ **v0.1.0** — Self-contained pyhap bridge + `HeaterCoolerPlus` with linked Fanv2 rotation-speed for arbitrary fan-mode names. YAML config. Repo scaffold + hassfest/HACS/pytest CI.
- ✅ **v0.4.0** — Swing mode, preset-switch accessories, linked humidity + battery sensors. Stable MAC and stable AIDs. Deferred-start / executor-wrapped driver init. All critical live-deployment gotchas resolved.
- ✅ **v0.5.0** — UI config flow + options flow, YAML auto-import, in-tree brand assets, `docs/VENDORING.md`, `async_setup_entry` refactor.
- 🟡 **v1.0 (in progress)** — HACS default-store submission pending maintainer review; vendored-code upstream re-sync on the next HA monthly release per `docs/VENDORING.md` cadence.

## 8. Testing Strategy

- **Unit tests** (`tests/test_util.py`): pure-Python coverage of fan-mode mapping and reverse-lookup helpers. Pytest collection deliberately stays clear of the HA `homekit` import chain (which needs `turbojpeg` / `libjpeg-turbo` / `ffmpeg` at import time) via lazy imports in `__init__.py`.
- **Integration tests** (future): pyhap bridge lifecycle against a mock HA instance, asserting accessory structure.
- **Manual hardware tests**: Daikin BRP069 + HA core daikin integration, via iOS Home, Controller for HomeKit, and Eve. Full pairing round-trip and per-characteristic interaction tested on every non-trivial change.
- **CI gates** (every commit + daily cron): hassfest, HACS validation, pytest.

## 9. Compatibility Matrix

| Thing | Requirement |
|---|---|
| Home Assistant | >= 2025.1 (built against 2026.4.3) |
| Python | whatever HA ships (3.12 for 2025.1, 3.13 for 2025.11+, 3.14 for 2026.x) |
| HACS | >= 2.0 |
| pyhap | `HAP-python >= 5.0.0` (matches HA 2026.4.3's pinned version) |
| iOS Home | 16+ |
| Controller for HomeKit | 7+ |
| Eve | 7+ |

## 10. Risks & Open Questions

1. **Vendored-code upstream drift** — HA will keep evolving `type_thermostats.py` and friends. Mitigation: `docs/VENDORING.md` documents scope, allowed modifications, and the resync procedure.
2. **HomeKit pair re-registration** — significant accessory-signature changes (new services, changed MAC, new aids) may make iOS show stale data or force a re-pair. Stable MAC and stable AIDs minimise this; new features that add services do not force a re-pair because pyhap bumps `c#` and iOS re-fetches the list.
3. **Duplicate exposure** — if the stock HomeKit bridge still has `climate` in its domain filter while this integration is running, climate entities appear on both bridges. The README documents how to exclude; we do not actively detect this at startup.
4. **Bridge port collision** — pyhap fails fast with `OSError: [Errno 98] address in use` if the configured port is already bound. In practice users running multiple HA HomeKit bridges (stock + accessory-mode for TVs / cameras / sprinklers) commonly have a handful of adjacent ports in use; pick a free one. 21064 is stock's default; accessory-mode bridges typically climb from there.
5. **Apple Home label rendering for linked sub-services** — Apple Home does not reliably honour `Name` characteristics on repeated linked services of the same type. This is why preset switches are standalone accessories rather than linked sub-services; it would come back if we ever added more same-type characteristics inside a single accessory.
6. **iOS Home rendering of Fanv2 inside HeaterCooler** — the fan-speed slider currently renders as a continuous bar inside the climate tile. Named-mode rendering in Apple Home is a platform limitation, not something this integration can solve.

## 11. Reference Material

- `homeassistant/components/homekit/type_thermostats.py` (HA core) — source for vendoring
- `homeassistant/components/homekit/accessories.py` (HA core) — source for vendoring
- `homeassistant/components/homekit/util.py` (HA core) — source for vendoring
- `pyhap/service.py` — `Service.add_linked_service()` API
- `pyhap/characteristic.py` — `Characteristic.set_value()` for state push
- `pyhap/accessory_driver.py` — `AccessoryDriver` bridge startup pattern
- HAP Specification — "Fanv2 Service" and "HeaterCooler Service" sections
- Homebridge plugin `homebridge-daikin-local` — reference implementation of the linked-service pattern
- [`docs/VENDORING.md`](docs/VENDORING.md) — vendored-code policy and resync procedure

## 12. Success Criteria

- [x] HACS-installable from a custom repository URL
- [x] Runs its own HomeKit bridge, independent of HA's `homekit` integration
- [x] Tested on HA 2025.1 through current release with a Daikin BRP069
- [x] Minimal runtime coupling to HA internals — only stable `homekit.const` / `homekit.iidmanager` / `homekit.models` imports from the vendored files; no monkey-patching or shims
- [x] Vendored code clearly marked with attribution and upstream commit SHA
- [x] No regressions for climate entities on the stock HomeKit bridge when properly configured (`climate` excluded there)
- [x] Single rich accessory per climate in Apple Home: fan speed and swing inside, preset switches as labelled sibling tiles
- [x] README with install, configuration, and pairing instructions
- [x] GitHub CI passes on every commit (hassfest + HACS + pytest)
- [x] UI config flow (not required for v0.1 but shipped in v0.5)
- [x] In-tree brand assets served via HA's 2026.3+ brand-proxy API
- [ ] Listed in the HACS default store (PR open, awaiting maintainer review)

## 13. Reference Environment

Primary hardware target for manual testing: a Daikin BRP069-series split-system air conditioner exposed through HA's core `daikin` integration, running on HAOS against the most recent HA monthly release. The Daikin reports:

- `fan_modes`: `["Auto", "Silence", "1", "2", "3", "4", "5"]`
- `swing_modes`: `["Off", "Vertical", "Horizontal", "3D"]`
- `preset_modes`: `["none", "away", "eco", "boost"]`
- `hvac_modes`: `["fan_only", "dry", "cool", "heat", "heat_cool", "off"]`

This is a deliberately-awkward worst case for HA's stock HomeKit bridge: every named set falls outside HA's predefined lists, every preset exists, and the entity supports enough HVAC modes to exercise mode-switching paths. If `homekit_climate_plus` handles it cleanly, simpler climate entities (Mitsubishi, Fujitsu, ecobee, Nest) fall out for free.

Secondary test entities on the same HA instance are generic resistive heaters with no fan or swing support, confirming the integration degrades gracefully to a bare `Thermostat` tile when nothing extra is wired up.

## 14. Attribution & Licensing

- Our code: **MIT** (permissive, HA community convention)
- Vendored code from `home-assistant/core`: **Apache 2.0**
- `LICENSE` contains the MIT text
- `NOTICE` contains the Apache 2.0 notice plus a link to the upstream HA repo and the commit SHA we vendored from
- `custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md` contains per-file attribution including original path, upstream commit SHA, and a record of every modification applied to the upstream source
- Each vendored `.py` file retains the original Home Assistant file's contents plus an "Adapted for homekit_climate_plus" header noting source and commit SHA
