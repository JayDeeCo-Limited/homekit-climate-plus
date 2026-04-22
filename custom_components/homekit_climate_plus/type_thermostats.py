"""Extended climate accessory with a linked Fanv2 service.

`HeaterCoolerPlus` subclasses the vendored `Thermostat` accessory. After the
base class's `__init__` runs we check whether it already attached a
rotation-speed characteristic — it will if and only if the climate entity's
`fan_modes` intersect Home Assistant's hard-coded
`PRE_DEFINED_FAN_MODES` set (`low`/`middle`/`medium`/`high`). For any
entity with non-standard fan-mode names — e.g. a Daikin reporting
`["Auto", "Silence", "1"–"5"]` — that intersection is empty and no fan
control reaches HomeKit.

When that happens we attach our own Fanv2 service, linked to the primary
Thermostat service, using either the user-supplied
`fan_mode_mapping` from config or an auto-generated even distribution.
Slider changes call `climate.set_fan_mode` with the closest named mode;
active-off turns the whole entity off; HA-side fan-mode or power-state
changes are pushed back to the characteristics via
`async_update_state`.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    DOMAIN as CLIMATE_DOMAIN,
    HVACMode,
    SERVICE_SET_FAN_MODE,
)
from homeassistant.components.homekit.const import (
    CHAR_ACTIVE,
    CHAR_ROTATION_SPEED,
    PROP_MIN_STEP,
    SERV_FANV2,
    SERV_THERMOSTAT,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import State, callback

from .const import CONF_FAN_MODE_MAPPING
from .util import auto_fan_mode_mapping, fan_mode_for_percent
from .vendored.type_thermostats import Thermostat

_LOGGER = logging.getLogger(__name__)


class HeaterCoolerPlus(Thermostat):
    """Thermostat accessory with a linked Fanv2 for arbitrary fan-mode names."""

    def __init__(self, *args: Any) -> None:
        # Initialize our attributes BEFORE super().__init__ runs. The parent
        # Thermostat.__init__ calls self.async_update_state(state) at the
        # tail to seed HomeKit characteristics from the current HA entity
        # state — and via MRO that dispatches to OUR override, which reads
        # self._plus_mapping. If we set these after super(), the override
        # hits AttributeError.
        self._plus_mapping: dict[str, int] | None = None
        self._plus_char_active = None
        self._plus_char_speed = None
        super().__init__(*args)
        self._plus_setup_fan()

    # --- Setup --------------------------------------------------------------

    def _plus_setup_fan(self) -> None:
        """Attach a custom Fanv2 service if the base class didn't already."""
        if CHAR_ROTATION_SPEED in self.fan_chars:
            return
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return
        fan_modes: list[str] = list(state.attributes.get(ATTR_FAN_MODES) or [])
        if not fan_modes:
            return

        override = self.config.get(CONF_FAN_MODE_MAPPING) or {}
        if override:
            mapping: dict[str, int] = {
                name: int(pct) for name, pct in override.items()
            }
        else:
            mapping = auto_fan_mode_mapping(fan_modes)
        if not mapping:
            return
        self._plus_mapping = mapping

        serv_thermostat = self.get_service(SERV_THERMOSTAT)
        serv_fan = self.add_preload_service(
            SERV_FANV2, [CHAR_ACTIVE, CHAR_ROTATION_SPEED]
        )
        serv_thermostat.add_linked_service(serv_fan)

        current_mode = state.attributes.get(ATTR_FAN_MODE)
        current_percent = mapping.get(current_mode, 100)
        active = self._plus_compute_active(state)

        self._plus_char_active = serv_fan.configure_char(
            CHAR_ACTIVE,
            value=active,
            setter_callback=self._plus_set_fan_active,
        )
        self._plus_char_speed = serv_fan.configure_char(
            CHAR_ROTATION_SPEED,
            value=current_percent,
            properties={PROP_MIN_STEP: max(1, round(100 / len(mapping)))},
            setter_callback=self._plus_set_fan_speed,
        )
        self._plus_char_speed.display_name = "Fan Mode"

        _LOGGER.debug(
            "HeaterCoolerPlus attached Fanv2 to %s with mapping %s",
            self.entity_id,
            mapping,
        )

    @staticmethod
    def _plus_compute_active(state: State) -> int:
        """0 when the entity is off / unavailable / unknown, else 1."""
        return (
            0
            if state.state in (HVACMode.OFF, STATE_UNAVAILABLE, STATE_UNKNOWN)
            else 1
        )

    # --- HomeKit → HA setter callbacks --------------------------------------

    def _plus_set_fan_active(self, active: int) -> None:
        """Apple Home toggled the fan sub-tile on/off."""
        # Turning off here turns the whole climate entity off. Turning on
        # is a no-op — the entity is already on if HomeKit can see a slider,
        # and we don't want to pick an HVAC mode on the user's behalf.
        if active == 0:
            self.async_call_service(
                CLIMATE_DOMAIN,
                SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: self.entity_id},
            )

    def _plus_set_fan_speed(self, percent: int) -> None:
        """Apple Home moved the fan-speed slider."""
        if not self._plus_mapping:
            return
        mode = fan_mode_for_percent(percent, self._plus_mapping)
        if mode is None:
            return
        self.async_call_service(
            CLIMATE_DOMAIN,
            SERVICE_SET_FAN_MODE,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_FAN_MODE: mode},
        )

    # --- HA → HomeKit state push --------------------------------------------

    @callback
    def async_update_state(self, new_state: State) -> None:
        """Push HA state changes to our extra characteristics, then defer to super."""
        super().async_update_state(new_state)
        if self._plus_mapping is None:
            return
        fan_mode = new_state.attributes.get(ATTR_FAN_MODE)
        if self._plus_char_speed is not None and fan_mode in self._plus_mapping:
            self._plus_char_speed.set_value(self._plus_mapping[fan_mode])
        if self._plus_char_active is not None:
            self._plus_char_active.set_value(self._plus_compute_active(new_state))
