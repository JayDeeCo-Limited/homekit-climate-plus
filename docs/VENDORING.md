# Vendored Code Policy

`custom_components/homekit_climate_plus/vendored/` holds copies of three
files from the [Home Assistant core](https://github.com/home-assistant/core)
`homekit` integration:

- `accessories.py` — `HomeAccessory`, `HomeBridge`, `HomeDriver`,
  `HomeIIDManager`
- `type_thermostats.py` — `Thermostat`, `WaterHeater`
- `util.py` — temperature helpers, setup-message helpers, etc.

## Why vendor at all?

The plugin extends `Thermostat` (our `HeaterCoolerPlus` subclasses it)
and hosts accessories on `HomeBridge` / `HomeDriver`. If we imported
those directly from `homeassistant.components.homekit.*`, any time
Home Assistant refactored one of those classes — renamed a method,
moved a constant, changed a signature — our plugin would break at the
next HA upgrade, potentially for every user of the plugin
simultaneously.

Vendoring freezes the base-class surface at a specific HA release.
Upgrades to that release happen deliberately, on our schedule, with
tests.

## What's allowed in the vendored directory

1. **Verbatim copies** of the three files listed above, straight from
   the upstream repo at a specific commit SHA.
2. A short `Adapted for homekit_climate_plus` header prepended to each
   file noting source path and upstream commit.
3. Import-path rewrites limited to the specific pattern
   `from .const import …` → `from homeassistant.components.homekit.const
   import …` (and similarly for `.iidmanager` and `.models`). We
   rely on Home Assistant's live copy of those small, rarely-changing
   dependencies so we don't have to recursively vendor them too.
4. Syntax-only bug-fix patches, each one documented in
   `ATTRIBUTION.md` under "Modifications from upstream". Current
   example: the two Python 2 `except ValueError, TypeError:` lines in
   `util.py` that don't parse under Python 3.

## What's NOT allowed

- Adding new functionality to vendored files. Extensions belong in
  our own modules (`type_thermostats.py`, `util.py`, `bridge.py`) that
  import from `vendored/…`.
- Removing functionality from vendored files, even if we don't use it.
  Leaving unused code in place keeps the diff against upstream
  minimal and makes re-sync trivial.
- Reformatting / lint-driven churn. The files should match upstream
  line-for-line apart from the documented patches.

## Resync procedure

1. Pick a new target HA release tag (usually the latest `.0` release:
   `2026.5.0`, `2026.6.0`, etc.).
2. Look up the commit SHA for that tag:
   `gh api repos/home-assistant/core/git/refs/tags/<tag>`.
3. Download the three files from that SHA into `vendored/`.
4. Re-apply the import-path rewrites (same three substitutions as
   before).
5. Re-apply the `Adapted for …` headers.
6. Run `python3 -m py_compile custom_components/homekit_climate_plus/vendored/*.py`.
   If that fails, either:
   - Upstream fixed a previous bug (update `ATTRIBUTION.md`,
     remove the patch from our copy), or
   - Upstream introduced a new syntax-level problem. Inspect the
     specific lines, apply a minimal patch, document it in
     `ATTRIBUTION.md`.
7. Update `ATTRIBUTION.md`:
   - New target release + commit SHA in the header
   - Refresh the per-file "View" links
   - Note any changes to the "Modifications from upstream" section
8. Run the test suite: `pytest -q`.
9. Bump the plugin's minor version (e.g. `0.4.0` → `0.5.0`) in
   `manifest.json` and add a `## [0.5.0]` entry to `CHANGELOG.md`
   describing the vendor-sync and any behavioural differences the
   bumped base classes introduce.
10. Open a PR. CI will run hassfest, HACS, and pytest against the
    fresh vendored files.

## Resync cadence

Target: resync with every second HA monthly release (roughly every
8 weeks). More often if a specific upstream change makes our
extensions impossible without the newer base; less often if the
upstream surface is stable.

The vendored tree's `ATTRIBUTION.md` records the last sync. A simple
GitHub Action that cronjobs `python3 -m py_compile` against the
current vendored files with the latest HA release's `accessories.py`
fetched fresh would catch silent upstream regressions early; not in
v0.4, tracked as a future improvement.

## Licence

Our code: MIT (`LICENSE`).
Vendored code: Apache-2.0 (original HA licence). See `NOTICE` at the
repo root and `vendored/ATTRIBUTION.md` per-file.
