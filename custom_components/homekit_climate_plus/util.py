"""Helpers for homekit_climate_plus.

Home Assistant's built-in HomeKit integration only auto-generates a linked
Fanv2 service if at least one of the climate entity's fan modes is in its
hard-coded `PRE_DEFINED_FAN_MODES` set (low / middle / medium / high).
Climate entities with named modes outside that set — e.g. a Daikin reporting
`["Auto", "Silence", "1", "2", "3", "4", "5"]` — get no fan control in
Apple Home.

The two functions here bridge that gap: they map arbitrary fan-mode names
onto the 0–100 slider HomeKit's Fanv2 service actually exposes.
"""
from __future__ import annotations


def auto_fan_mode_mapping(fan_modes: list[str]) -> dict[str, int]:
    """Distribute `fan_modes` evenly across the 1–100 HomeKit slider range.

    The returned dict maps each mode name to the slider position that
    should select it. Positions are evenly spaced: mode index `i` (0-based)
    gets `round((i + 1) * 100 / N)` where N is the number of modes. The
    last mode always lands on 100 and there is no explicit 0 entry —
    `Active=0` is the "off" state, separate from fan speed.

    Empty input returns an empty mapping.
    """
    if not fan_modes:
        return {}
    n = len(fan_modes)
    step = 100 / n
    return {mode: round((i + 1) * step) for i, mode in enumerate(fan_modes)}


def fan_mode_for_percent(
    percent: int, mapping: dict[str, int]
) -> str | None:
    """Pick the fan mode whose mapped slider position is closest to `percent`.

    Ties are resolved by Python's usual stable ordering: the first mode
    encountered in `mapping.items()` wins. Returns None only when
    `mapping` is empty.
    """
    if not mapping:
        return None
    return min(mapping.items(), key=lambda kv: abs(kv[1] - percent))[0]
