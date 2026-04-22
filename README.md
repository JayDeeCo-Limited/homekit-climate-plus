# HomeKit Climate Plus

A Home Assistant custom integration that exposes `climate.*` entities to
Apple HomeKit as a **single accessory** with the fan speed inside it — so
one AC shows up as one tile in Apple Home with all its controls, rather
than being fragmented across a climate tile and a template fan tile.

It runs **its own HomeKit bridge**, independent of Home Assistant's
built-in HomeKit Bridge integration. Keep the stock bridge for everything
else; this one handles climate entities only.

## Status

v0.1 pre-release. The linked fan-speed feature is implemented end-to-end
and all automated checks pass. Swing mode, preset modes, and secondary
sensors are planned for v0.2 – v0.4; see [PRD.md](PRD.md) for the full
roadmap.

### What works today

- A self-contained HomeKit bridge announced over mDNS on your LAN
- Pairing via the persistent notification that appears on first run
- One Apple Home tile per configured `climate.*` entity, with linked fan
  speed — even for entities whose fan-mode names (e.g. a Daikin's
  `Auto / Silence / 1–5`) don't match Home Assistant's stock built-in list
- Auto-generated fan-mode → slider mapping, or a manual override via the
  `fan_mode_mapping` config key
- State sync both ways: Apple Home ⇄ Home Assistant

### Not yet

- Swing-mode characteristic (v0.2)
- Preset modes (v0.3)
- Linked humidity / battery / outside-temperature sensors (v0.4)
- UI config flow — v0.1 is YAML-only

## Requirements

- Home Assistant 2025.1 or newer (tested against 2026.4.3)
- Python 3.12+
- HACS 2.0+ (for install)
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
  name: Climate Bridge
  port: 21065          # optional, default shown
  entity_config:
    climate.daikin_ac: {}
```

The empty `{}` is intentional: with no overrides, the plugin auto-detects
the entity's fan modes and distributes them evenly across Apple Home's
1–100 slider. A seven-mode Daikin, for example, lands on:

| Fan mode | Slider |
|---|---|
| Auto | 14 |
| Silence | 29 |
| 1 | 43 |
| 2 | 57 |
| 3 | 71 |
| 4 | 86 |
| 5 | 100 |

To override that mapping — say, to drop certain modes or reorder — use
`fan_mode_mapping`:

```yaml
homekit_climate_plus:
  entity_config:
    climate.daikin_ac:
      fan_mode_mapping:
        Auto: 14
        Silence: 28
        "1": 43
        "2": 57
        "3": 71
        "4": 86
        "5": 100
```

Full schema reference: [PRD.md §5.5](PRD.md).

## Pair

On first start, look for a persistent notification titled
**"homekit_climate_plus: pairing required"** in Home Assistant with the
8-digit setup code. Then:

1. Open the **Home** app on iPhone
2. Tap **+** → **Add Accessory** → **More options…**
3. Select the bridge (by the `name` from your config)
4. Enter the setup code from the notification

## Exclude climate entities from the stock bridge

In your stock `homekit:` config, exclude any climate entities handled
here so they don't appear twice in Apple Home:

```yaml
homekit:
  filter:
    exclude_domains:
      - climate
```

## License

MIT — see [LICENSE](LICENSE). Vendored code from `home-assistant/core`
is Apache 2.0; see [NOTICE](NOTICE) and
[`custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md`](custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md).
