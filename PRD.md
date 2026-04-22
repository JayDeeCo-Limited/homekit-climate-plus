# homekit_climate_plus — PRD

## 1. Context & Problem

Home Assistant's HomeKit Bridge maps a `climate` entity to a HomeKit `HeaterCooler` accessory. That accessory exposes:
- Target temperature
- Heat/Cool/Off mode
- A single continuous `RotationSpeed` slider (0–100) for fan speed

What it **does not expose cleanly**:
- Named fan modes (Auto, Silence, 1–5) — lossy-mapped to the slider
- Swing modes (Off/Vertical/Horizontal/3D)
- Preset modes (away, eco, boost)
- Secondary sensors (inside/outside temp, humidity)

Today's workaround: create a template `fan.` entity that proxies `climate.set_fan_mode`, expose both to HomeKit as **two separate tiles**. This fragments the UX — the user manages one AC but sees a climate tile **and** a fan tile in Apple Home.

The underlying HomeKit Accessory Protocol (HAP) supports **linked services** — multiple services grouped under one accessory. Homebridge AC plugins use this routinely. HA's built-in HomeKit Bridge does not, for climate entities.

## 2. Goal

Ship a HACS-installable custom component **`homekit_climate_plus`** that exposes HA climate entities to HomeKit via its **own self-contained bridge** — delivering a single HomeKit accessory per climate entity with linked services for fan, swing, preset, and supplementary sensors. One tile, every control inside it. Zero patches or shims to HA core.

## 3. Non-Goals

- Not replacing HA's HomeKit Bridge — **run alongside** it. Users keep their existing bridge for non-climate entities.
- Not modifying, monkey-patching, or shim-ing HA core code at runtime.
- Not modifying the HAP spec, iOS Home app, or any Apple proprietary surface.
- Not writing new climate integrations (Daikin, Mitsubishi, etc.) — we consume existing `climate.*` entities.
- Not v0.1 concerns: media player, covers, light fixtures.

## 4. User Stories

- As an HA user with a Daikin AC, I pair the `homekit_climate_plus` bridge in Apple Home and see **one** AC accessory with all fan speeds, swing, and presets accessible from within it.
- As an HA user with a Mitsubishi / Fujitsu / ecobee / Nest climate entity, I get the same experience without Daikin-specific code.
- As a HACS user, I install this via "custom repository" and configure via `configuration.yaml` without writing template fans.
- As a homelab power user, I can still override per-entity behavior (fan percent mapping, characteristic masks).
- As a user on an HA monthly release, I don't worry about this plugin silently breaking — it has no runtime coupling to HA internals.

## 5. Architecture

### 5.1 Self-contained HomeKit bridge

`homekit_climate_plus` runs its own pyhap-based HomeKit bridge **inside the HA process**, independent of HA's built-in `homekit` integration.

```
iOS Apple Home app
    │
    ├─── HA HomeKit Bridge (stock)        — lights, switches, covers, sensors
    └─── homekit_climate_plus Bridge      — climate entities only
```

The user pairs the new bridge in Apple Home as a **second HomeKit bridge**, a one-time setup. Climate entities are excluded from the stock bridge (via its existing filter) and included in ours.

**Why this is robust:**

- No runtime patching of HA internals. We don't reach into HA core code paths.
- We own the whole surface: accessory lifecycle, characteristic wiring, bridge configuration, mDNS advertisement.
- HA core refactors cannot break us. Only changes to `pyhap` (our one dependency) could, and that's a semver'd third-party library.
- All the code we ship is code we control. Vendored-in pieces are versioned in our repo — no silent drift.

### 5.2 Vendored code from home-assistant/core

To avoid reimplementing known-good work, we **vendor** the climate-accessory and supporting bridge code from HA's `homekit` integration (Apache 2.0, attribution preserved). Specifically:

- `type_thermostats.py` — baseline `HeaterCooler` accessory class
- `accessories.py` — `HomeAccessory` + `HomeBridge` base classes
- `util.py` — temperature conversion, state mapping helpers
- Any private helpers those files transitively require

These go into `custom_components/homekit_climate_plus/vendored/` with a clear `ATTRIBUTION.md` linking to the exact upstream commit we forked from. We sync upstream deliberately on each release, not automatically.

### 5.3 Extended accessory class

On top of vendored `HeaterCooler`, we define `HeaterCoolerPlus` in our own module:

```python
# custom_components/homekit_climate_plus/type_thermostats.py
from .vendored.type_thermostats import HeaterCooler

class HeaterCoolerPlus(HeaterCooler):
    """HeaterCooler with linked Fanv2, SwingMode, and preset support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfg = self.config  # entity_config for this entity
        if linked_fan := cfg.get("linked_fan"):
            self._add_linked_fan(linked_fan, cfg.get("fan_mode_mapping"))
        elif self._entity_state.attributes.get("fan_modes"):
            self._add_auto_fan()               # auto-generate from fan_modes
        if cfg.get("linked_swing_mode", True):
            self._add_swing_mode()
        if cfg.get("linked_preset_modes", True):
            self._add_preset_modes()

    def _add_linked_fan(self, fan_entity_id, mapping):
        svc_fan = self.add_preload_service("Fanv2", ["RotationSpeed"])
        svc_fan.configure_char("Active",            setter_callback=self._set_fan_active)
        svc_fan.configure_char("RotationSpeed",     setter_callback=self._set_fan_speed)
        svc_fan.configure_char("CurrentFanState")   # 0=inactive, 1=idle, 2=blowing
        svc_fan.configure_char("TargetFanState")    # 0=manual, 1=auto
        self.char_active_fan      = svc_fan.get_characteristic("Active")
        self.char_rotation_speed  = svc_fan.get_characteristic("RotationSpeed")
        self.get_service("HeaterCooler").add_linked_service(svc_fan)
        # register HA state listener → push to characteristics
        ...
```

### 5.4 Bridge lifecycle

In `__init__.py`:

- `async_setup_entry` starts a pyhap `Bridge` on a configurable port (default 21065, not HA's default homekit port)
- Creates a `HeaterCoolerPlus` accessory for each configured climate entity
- Registers the bridge's mDNS/Bonjour advertisement
- Persists pairing state to HA storage under `.storage/homekit_climate_plus.<entry_id>`
- `async_unload_entry` cleanly tears down bridge + mDNS

### 5.5 Config schema

```yaml
homekit_climate_plus:
  name: Climate Bridge       # shown in Apple Home during pairing
  port: 21065                # optional, default shown
  pin: 123-45-678            # optional, regenerated if omitted
  entity_config:
    climate.daikin_ac:
      linked_fan: fan.living_room_ac_fan          # optional — auto-generate if omitted
      linked_swing_mode: true                      # default true, set false to disable
      linked_preset_modes: true                    # default true, set false to disable
      fan_mode_mapping:                            # optional — override auto-generated
        Auto: 14
        Silence: 28
        "1": 43
        "2": 57
        "3": 71
        "4": 86
        "5": 100
      linked_humidity_sensor: sensor.indoor_humidity
      linked_battery_sensor: sensor.ac_battery
```

When `linked_fan` is omitted but the climate entity has `fan_modes`, the plugin generates the percent mapping automatically and exposes the Fanv2 service driven directly by `climate.set_fan_mode`. No template fan needed.

### 5.6 State sync

- **HA → HomeKit**: `async_track_state_change_event` on climate entity + any linked entities. Push characteristic updates via `char.set_value()`.
- **HomeKit → HA**: `setter_callback` on each writable characteristic. Dispatch to `climate.set_fan_mode`, `climate.set_swing_mode`, `climate.set_preset_mode`, or `fan.set_percentage` depending on linkage.

## 6. Repository Layout

```
homekit_climate_plus/
├── custom_components/homekit_climate_plus/
│   ├── __init__.py                # component setup, bridge lifecycle
│   ├── manifest.json              # integration metadata
│   ├── const.py                   # DOMAIN, config keys, defaults
│   ├── config_flow.py             # UI config flow (post-v0.1)
│   ├── bridge.py                  # pyhap Bridge wrapper, pairing persistence
│   ├── type_thermostats.py        # HeaterCoolerPlus (extends vendored base)
│   ├── util.py                    # our helpers: fan mode percent mapping, etc.
│   ├── vendored/
│   │   ├── ATTRIBUTION.md         # Apache 2.0 notice, upstream commit SHA
│   │   ├── __init__.py
│   │   ├── type_thermostats.py    # copied from home-assistant/core
│   │   ├── accessories.py         # copied from home-assistant/core
│   │   └── util.py                # copied from home-assistant/core
│   └── translations/
│       └── en.json
├── tests/
│   ├── conftest.py
│   ├── test_fan_linking.py
│   ├── test_swing.py
│   ├── test_mapping.py
│   └── test_bridge_lifecycle.py
├── hacs.json                      # HACS metadata
├── .github/
│   ├── workflows/
│   │   ├── hassfest.yaml          # home-assistant/actions/hassfest
│   │   ├── hacs.yaml              # hacs/action@main
│   │   └── pytest.yaml
│   └── ISSUE_TEMPLATE/
├── LICENSE                        # MIT (our code)
├── NOTICE                         # Apache 2.0 notice for vendored HA code
├── README.md                      # install, config, pairing screenshots
├── CHANGELOG.md
└── .gitignore
```

## 7. Implementation Phases

**v0.1 — MVP (self-contained bridge + fan linking)**
1. Repo scaffold, MIT license, NOTICE file, HACS metadata, hassfest CI
2. Vendor HA's homekit accessory base + climate accessory code; record upstream commit SHA in `ATTRIBUTION.md`
3. Build `bridge.py` — pyhap Bridge setup, pairing storage, mDNS lifecycle
4. Implement `HeaterCoolerPlus` (linked Fanv2 service, auto-generated fan-mode mapping, manual override support)
5. Config entry support via `configuration.yaml` YAML schema
6. Unit tests for fan mode mapping, state translation, characteristic callbacks
7. Integration test: pyhap bridge stands up, accessory registered correctly, state sync works against mock climate entity
8. README with install, exclude-from-stock-bridge instructions, Daikin screenshots
9. Tag `v0.1.0`, publish as HACS custom repository

**v0.2 — Swing mode**
1. SwingMode characteristic (0/1) on HeaterCoolerPlus
2. Maps to `climate.set_swing_mode` using first non-"off" swing mode
3. Optional `swing_mode_mapping` for multi-state swings

**v0.3 — Preset modes**
1. Preset mode exposed as HomeKit `Mode` selector or custom characteristic
2. Fallback strategy when Apple Home doesn't render it cleanly

**v0.4 — Secondary sensors & polish**
1. Outside temp sensor linking (Daikin exposes this)
2. Humidity-aware cooling
3. Config flow UI so users don't edit YAML

**v1.0 — Stabilization**
1. First upstream sync of vendored code (probably 2–3 HA releases after v0.1)
2. Publish to HACS default store (via PR)
3. Long-lived repo with documented sync policy

## 8. Testing Strategy

- **Unit**: `pytest-homeassistant-custom-component` for config parsing, fan mode mapping, state translation
- **Integration**: pyhap bridge lifecycle tests, mock climate entity with varying `fan_modes`/`swing_modes`, assert accessory definition includes correct services and linked_services
- **Manual**: Daikin TS-453Be environment (user's AC). Verify on iOS Home, Controller for HomeKit, Eve
- **CI gates**: hassfest, hacs-validate, pytest

## 9. Compatibility Matrix

| Thing | Requirement |
|---|---|
| Home Assistant | >= 2025.1 (stable config entry API) |
| Python | >= 3.12 |
| HACS | >= 2.0 (for install) |
| pyhap | whatever HA ships (no pin — we rely on HA's version) |
| iOS Home | 16+ (linked services work; rendering is continuous slider) |
| Controller for HomeKit | 7+ (renders linked Fanv2 as stepper) |
| Eve | 7+ (renders named characteristics) |

## 10. Risks & Open Questions

1. **Vendored-code upstream drift** — HA will evolve `type_thermostats.py` and friends. Mitigation: vendored files have documented upstream commit SHA; maintainer rebases deliberately on each release; semver bump when vendored code updates.
2. **HomeKit pair re-registration** — significant accessory signature changes require users to unpair + re-pair the bridge. Clearly documented in README and release notes.
3. **Conflict with stock HomeKit bridge** — if a user forgets to exclude climate entities from the stock bridge, the same entity appears on both bridges. Plugin detects this on startup and logs a loud warning, with docs on how to fix.
4. **iOS Home app rendering of linked Fanv2** — may still show a sub-tile in accessory detail view rather than fully integrated controls. Early iOS 17/18 UX testing required before declaring v0.1 stable.
5. **Testing without physical hardware** — CI uses mock climate entities. Full validation requires a real HomeKit pairing round-trip with actual iOS devices. User's Daikin is the v0.1 reference environment.
6. **Bridge port collision** — default port 21065, user-configurable, documented in README. Plugin fails fast with clear error if port is in use.

## 11. Reference Material

- `homeassistant/components/homekit/type_thermostats.py` (HA core) — **source for vendoring**
- `homeassistant/components/homekit/accessories.py` (HA core) — **source for vendoring**
- `homeassistant/components/homekit/util.py` (HA core) — **source for vendoring**
- `pyhap/service.py` — `Service.add_linked_service()` API
- `pyhap/characteristic.py` — `Characteristic.set_value()` for state push
- `pyhap/accessory_driver.py` — `AccessoryDriver` bridge startup pattern
- HAP Specification — "Fanv2 Service" and "HeaterCooler Service" sections
- Homebridge plugin `homebridge-daikin-local` — reference implementation of linked-service pattern

## 12. Success Criteria

- [ ] HACS-installable from a custom repository URL
- [ ] Runs its own HomeKit bridge, independent of HA's `homekit` integration
- [ ] Tested on HA 2025.1 through current release with Daikin (user's hardware)
- [ ] Zero runtime coupling to HA internals — no monkey-patches, no shims
- [ ] Vendored code clearly marked with attribution and upstream commit SHA
- [ ] No regressions for climate entities with stock homekit when properly configured
- [ ] Single accessory per climate in Apple Home with fan speed inside the tile
- [ ] README + pairing screenshots published
- [ ] GitHub CI passes on every commit (hassfest + hacs + pytest)

## 13. Reference Environment (source of truth for initial dev & testing)

- HA instance: HAOS VM at `192.168.1.166`, static DNS to `192.168.1.1`
- HA Core at time of PRD: `2026.4.3`; HAOS `17.2`
- Test climate entity: `climate.daikin_ac` (Daikin BRP069 via HA core `daikin` integration)
  - `fan_modes`: `["Auto", "Silence", "1", "2", "3", "4", "5"]`
  - `swing_modes`: `["Off", "Vertical", "Horizontal", "3D"]`
  - `preset_modes`: `["none", "away", "eco", "boost"]`
  - `hvac_modes`: `["fan_only", "dry", "cool", "heat", "heat_cool", "off"]`
- Current workaround (to be replaced): `fan.living_room_ac_fan` template fan in `/config/configuration.yaml`
- HA HomeKit Bridge (stock, keep for non-climate): `HASS Bridge E8925C` (`entry_id: 871565d21e7d504bdb04205814a3696d`)

## 14. Attribution & Licensing

- Our code: **MIT** (permissive, HA community convention)
- Vendored code from `home-assistant/core`: **Apache 2.0** (their license)
- `LICENSE` contains our MIT text
- `NOTICE` contains the Apache 2.0 notice plus link to the upstream HA repo and the commit SHA we vendored from
- `custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md` contains per-file attribution including original path and upstream commit SHA
- Each vendored `.py` file retains the original HA copyright header plus an "Adapted for homekit_climate_plus" header noting the source
