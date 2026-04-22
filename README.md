# HomeKit Climate Plus

A Home Assistant custom integration that exposes `climate.*` entities to
Apple HomeKit as a **single rich accessory** per climate — with fan
speed, swing, and presets — rather than fragmenting a climate entity
across a climate tile plus a template fan tile plus separate helper
switches. It runs its own HomeKit bridge alongside Home Assistant's
built-in HomeKit Bridge; keep the stock bridge for everything else,
this one handles climate entities only.

## Status

**v0.4.0** — feature-complete per [PRD.md](PRD.md) roadmap. End-to-end
tested on a Daikin BRP069 via HA 2026.4.3. CI (hassfest + HACS + pytest)
green on every commit.

### What's in

- Self-contained pyhap HomeKit bridge with deterministic MAC and
  accessory IDs (stable across restarts).
- One Apple Home tile per climate entity with:
  - Target temperature, mode (Heat / Cool / Auto / Off), current temp
  - Fan speed slider mapped from any `fan_modes` list — auto-distributed
    across 1–100 or user-supplied
  - Swing on/off mapped from any `swing_modes` list
- One standalone switch tile per non-`none` preset (e.g. "Air
  Conditioner — Away", "Air Conditioner — Eco") for entities that
  expose a `'none'` preset. Mutually exclusive by convention via
  `climate.set_preset_mode`.
- Optional linked humidity and battery sensors on a climate's tile.
- First-run persistent notification with the Apple Home setup code.

### Not yet

- UI config flow (YAML is currently the only path to configure).
- Outdoor-temperature linked sensor (planned for a future minor bump).
- HACS default-store listing.

## Requirements

- Home Assistant 2025.1 or newer (built against 2026.4.3)
- Python 3.12+
- HACS 2.0+ for install
- iOS 16+ Home app

## Install (HACS, custom repository)

1. In HACS, **Integrations → ⋯ → Custom repositories**
2. Add `https://github.com/JayDeeCo-Limited/homekit-climate-plus` with
   category `Integration`
3. Install **HomeKit Climate Plus**
4. Restart Home Assistant

## Configure

Add to `configuration.yaml`:

```yaml
homekit_climate_plus:
  name: Climate Bridge        # shown in Apple Home during pairing
  port: 21066                 # optional; pick one not already in use
                              # (stock HomeKit uses 21064, accessory-mode
                              # bridges climb from there)
  pin: "739-42-618"           # optional but recommended — stable across
                              # restarts, saves you retyping
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
```

### Per-entity options

| Key | Type | Default | Meaning |
|---|---|---|---|
| `linked_swing_mode` | bool | `true` | Expose a HomeKit SwingMode characteristic on the Fanv2 sub-tile |
| `linked_preset_modes` | bool | `true` | Register one standalone Switch accessory per non-`none` preset mode |
| `fan_mode_mapping` | `{name: 1–100}` | auto-distributed | Override the default even-distribution of fan modes across the HomeKit slider |
| `linked_humidity_sensor` | entity id | — | Link an external humidity sensor as a HomeKit HumiditySensor service |
| `linked_battery_sensor` | entity id | — | Link a battery-level sensor (handled by the vendored HA base class) |

With an empty `{}`, every supported feature is auto-configured from the
entity's own attributes. The Daikin in the top-level example gets a
7-step fan slider, swing on/off, and three preset tiles (Away / Eco /
Boost) with zero extra configuration.

## Pair

On first start, look for a persistent notification titled
**"homekit_climate_plus: pairing required"** in Home Assistant. Then:

1. Open the **Home** app on iPhone
2. Tap **+** → **Add Accessory** → **More options…**
3. Select the bridge name from the config
4. Enter the setup code shown in the notification

## Exclude climate entities from the stock bridge

In your stock `homekit:` config, exclude any climate entities handled
here so they don't appear twice in Apple Home:

```yaml
homekit:
  filter:
    exclude_domains:
      - climate
```

Alternatively, if the stock bridge is UI-configured, open **Settings →
Devices & Services → HomeKit Bridge → Configure**, and uncheck Climate
from the domain filter.

## How it works

See the [Product Requirements Document](PRD.md) for the full design.
Short version:

- `bridge.py` owns the pyhap AccessoryDriver + Bridge lifecycle:
  deterministic MAC, persistent pairing state, stable AIDs.
- `type_thermostats.HeaterCoolerPlus` subclasses HA's vendored
  `Thermostat` accessory. Where the vendored implementation skips
  setting up fan/swing characteristics for entities whose mode names
  don't intersect HA's hard-coded predefined sets, `HeaterCoolerPlus`
  adds its own Fanv2 service with the full set of characteristics.
- `type_thermostats.PresetSwitchAccessory` is a standalone Switch
  accessory registered on the same bridge — one per preset, per
  climate — so Apple Home can render proper names on each tile
  (linked sub-services don't reliably get labeled names there).
- `vendored/*` holds frozen copies of three files from
  `home-assistant/core`'s `homekit` integration. See
  [`docs/VENDORING.md`](docs/VENDORING.md) for the resync policy and
  [`custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md`](custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md)
  for per-file attribution and the current upstream commit.

## License

MIT — see [LICENSE](LICENSE). Vendored code from `home-assistant/core`
is Apache 2.0; see [NOTICE](NOTICE).
