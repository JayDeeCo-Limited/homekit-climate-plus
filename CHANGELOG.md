# Changelog

All notable changes to this project will be documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Repository scaffold: HACS metadata, hassfest + HACS + pytest CI
  workflows, component skeleton, MIT license, Apache 2.0 NOTICE.
- Vendored `type_thermostats.py`, `accessories.py`, `util.py` from Home
  Assistant 2026.4.3 (commit `1fec38e`). See
  [`custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md`](custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md)
  for links and modification notes.
- `util.auto_fan_mode_mapping` and `util.fan_mode_for_percent`: map
  arbitrary climate fan-mode names onto HomeKit's 0–100 slider, covering
  the Daikin / Mitsubishi / numeric-mode cases HA's built-in accessory
  refuses to handle.
- `HeaterCoolerPlus` accessory class: extends the vendored Home
  Assistant `Thermostat` accessory and attaches a linked Fanv2 service
  when the base class's predefined-fan-mode filter excludes the entity.
  Setter callbacks route active-off to `climate.turn_off` and slider
  moves to `climate.set_fan_mode` with the closest named mode; HA-side
  fan-mode and power-state changes propagate back via
  `async_update_state`.
- `HomeKitClimatePlusBridge`: pyhap-based HomeKit server that starts on
  a configurable port (default `21065`), advertises itself over HA's
  shared zeroconf instance, persists pairing state and accessory IDs
  across restarts, registers one `HeaterCoolerPlus` per configured
  entity with deterministic AID assignment, and shuts down cleanly on
  `EVENT_HOMEASSISTANT_STOP`.
- Persistent "pairing required" notification on first start showing the
  setup code for Apple Home.

### Fixed
- Vendored `util.py`: two `except ValueError, TypeError:` lines in
  `convert_to_float` / `coerce_int` were Python 2 syntax that wouldn't
  compile under Python 3; rewritten to `except (ValueError, TypeError):`.
  The bug is present in the upstream file.
