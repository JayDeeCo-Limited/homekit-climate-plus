# Changelog

All notable changes to this project will be documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Initial repository scaffold: HACS metadata, hassfest + HACS + pytest CI
  workflows, component skeleton with YAML config schema, MIT license and
  Apache 2.0 NOTICE.
- Vendored `type_thermostats.py`, `accessories.py`, `util.py` from Home
  Assistant 2026.4.3 (commit `1fec38e`). See
  [`custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md`](custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md)
  for per-file links and modification notes.

### Fixed
- Vendored `util.py`: two `except ValueError, TypeError:` lines in
  `convert_to_float` / `coerce_int` were Python 2 syntax and wouldn't
  compile under Python 3; rewritten to `except (ValueError, TypeError):`.
  The bug is present in the upstream file.
