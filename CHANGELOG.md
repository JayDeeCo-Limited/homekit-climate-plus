# Changelog

All notable changes to this project will be documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versioning follows [SemVer](https://semver.org/).

## [0.4.0]

### Added
- **Swing mode (v0.2)**: `HeaterCoolerPlus` now attaches a HomeKit
  `SwingMode` characteristic to its `Fanv2` service for any entity that
  advertises `ClimateEntityFeature.SWING_MODE`, including ones whose
  swing-mode names don't match Home Assistant's hard-coded
  `on/both/horizontal/vertical` set (e.g. a Daikin reporting
  `Off/Vertical/Horizontal/3D`). The "off" mode is detected by
  case-insensitive match to `"off"`; the "on" mode is the first non-off
  entry. Respects `linked_swing_mode` (default `true`).
- **Preset-mode switches (v0.3)**: each non-`none` preset mode becomes
  a linked HomeKit `Switch` service. Toggling one calls
  `climate.set_preset_mode` with that preset; toggling off reverts to
  `none`. Others flip themselves off via the state-sync path once HA
  reflects the new preset. Requires the entity to advertise a `none`
  preset (case-insensitive); entities without one are skipped.
  Respects `linked_preset_modes` (default `true`).
- **Linked humidity sensor (v0.4)**: when
  `linked_humidity_sensor: sensor.xxx` is set on the entity config, a
  `HumiditySensor` service is linked to the main `Thermostat` service
  and kept in sync with the sensor's state.
- **Linked battery sensor (v0.4)**: `linked_battery_sensor: sensor.xxx`
  is handled automatically by the vendored `HomeAccessory` base class;
  no code changes needed on our side.

### Changed
- `HomeKitClimatePlusBridge` now stamps a deterministic, locally-
  administered MAC on the pyhap `AccessoryDriver` state before
  `async_start`, derived from a SHA-256 of the bridge's synthetic
  entry_id. Fixes a bug where the bridge advertised MAC `00:00:00:…`
  (pyhap's `EMPTY_MAC` placeholder that HA's `HomeDriver` leaves in
  place), colliding with every other HA-spawned HomeKit bridge and
  causing iOS to route `/pair-verify` requests for our bridge to
  whichever sibling bridge (e.g. "Living Room TV") picked up the TCP
  session first. Log evidence: iPhone POSTs targeting
  `Climate Bridge 000000._hap._tcp.local` were answered by
  `Living Room TV`. Stable-MAC fix lands in v0.4.0 so prior pairings
  survive across the upgrade.
- `HeaterCoolerPlus` now initialises all of its `_plus_*` attributes
  **before** calling `super().__init__`, because the vendored
  `Thermostat.__init__` tail-calls `self.async_update_state(state)`
  which MRO-dispatches to our override (fixes an AttributeError that
  prevented any accessory from registering).
- Pyhap `AccessoryDriver` + `HomeBridge` construction and the
  `add_accessory` call now run inside `hass.async_add_executor_job` so
  HA's event-loop watchdog stops flagging pyhap's synchronous
  `open(characteristics.json)` and `open(persist_file)` reads.
- Bridge startup is deferred until `EVENT_HOMEASSISTANT_STARTED` so
  entity state registry is populated by the time
  `_register_climate_accessories` runs. Prior to this, the bridge
  started too early and registered zero accessories because
  `hass.states.get(entity_id)` returned `None` for every configured
  climate entity.

## [0.1.0]

### Added
- Repository scaffold: HACS metadata, hassfest + HACS + pytest CI
  workflows, component skeleton, MIT license, Apache 2.0 NOTICE.
- Vendored `type_thermostats.py`, `accessories.py`, `util.py` from
  Home Assistant 2026.4.3 (commit `1fec38e`). See
  [`custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md`](custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md)
  for links and modification notes.
- `util.auto_fan_mode_mapping` and `util.fan_mode_for_percent`: map
  arbitrary climate fan-mode names onto HomeKit's 0–100 slider.
- `HeaterCoolerPlus` accessory class with linked `Fanv2` rotation-speed
  support for fan-mode names outside HA's predefined set.
- `HomeKitClimatePlusBridge`: pyhap-based HomeKit server, per-YAML
  entity_config, deterministic AID allocation, clean shutdown.
- Persistent "pairing required" notification on first start.

### Fixed
- Vendored `util.py`: two `except ValueError, TypeError:` lines in
  `convert_to_float` / `coerce_int` were Python 2 syntax that wouldn't
  compile under Python 3; rewritten to `except (ValueError, TypeError):`.
  The bug is present in the upstream file.
