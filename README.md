# HomeKit Climate Plus

A Home Assistant custom integration that exposes `climate.*` entities to
Apple HomeKit as a **single accessory** with linked fan, swing, preset, and
sensor services — so one AC shows up as one tile in Apple Home with all its
controls inside, rather than being fragmented across a climate tile and a
template fan tile.

It runs **its own HomeKit bridge**, independent of Home Assistant's built-in
HomeKit Bridge integration. Keep the stock bridge for everything else; this
one handles climate entities only.

## Status

Early development — repo scaffold only. See [PRD.md](PRD.md) for the full
spec and roadmap.

## Requirements

- Home Assistant 2025.1 or newer
- Python 3.12+
- HACS 2.0+ (for install)
- iOS 16+ Home app

## Install (HACS, custom repository)

1. In HACS, **Integrations → ⋯ → Custom repositories**
2. Add `https://github.com/JayDeeCo/homekit-climate-plus` with category
   `Integration`
3. Install **HomeKit Climate Plus**
4. Restart Home Assistant

## Configure

Add to `configuration.yaml`:

```yaml
homekit_climate_plus:
  name: Climate Bridge
  port: 21065
  entity_config:
    climate.daikin_ac:
      linked_fan: fan.living_room_ac_fan
      linked_swing_mode: true
      linked_preset_modes: true
```

Full schema is in [PRD.md §5.5](PRD.md).

## Pair

After restart, open Apple Home → **Add Accessory** → **More options** →
pick the new bridge and scan the PIN from the Home Assistant notification.

## Exclude climate entities from the stock bridge

In your stock `homekit:` config, exclude any climate entities handled here
so they don't appear twice:

```yaml
homekit:
  filter:
    exclude_domains:
      - climate
```

## License

MIT — see [LICENSE](LICENSE). Vendored code from `home-assistant/core` is
Apache 2.0; see [NOTICE](NOTICE) and
[`custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md`](custom_components/homekit_climate_plus/vendored/ATTRIBUTION.md).
