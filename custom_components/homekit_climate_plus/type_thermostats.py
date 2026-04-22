"""Extended climate accessory.

`HeaterCoolerPlus` subclasses the vendored `Thermostat` accessory. After the
base class's `__init__` runs we check whether it already attached a
rotation-speed or swing-mode characteristic — it will if and only if the
climate entity's fan / swing modes intersect Home Assistant's hard-coded
predefined sets (`low`/`middle`/`medium`/`high` for fan;
`on`/`both`/`horizontal`/`vertical` for swing). For any entity with
non-standard mode names — e.g. a Daikin reporting
`fan_modes=["Auto","Silence","1"–"5"]` and
`swing_modes=["Off","Vertical","Horizontal","3D"]` — those intersections
are empty and no Fanv2 service ever reaches HomeKit.

When that happens we attach our own Fanv2 service, linked to the primary
Thermostat service, with whichever characteristics the base class skipped
(RotationSpeed and/or SwingMode). All setter callbacks dispatch back to
the appropriate `climate.*` service and `async_update_state` pushes HA
state changes to HomeKit.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ClimateEntityFeature,
    DOMAIN as CLIMATE_DOMAIN,
    HVACMode,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
)
from homeassistant.components.homekit.const import (
    CHAR_ACTIVE,
    CHAR_ROTATION_SPEED,
    CHAR_SWING_MODE,
    PROP_MIN_STEP,
    SERV_FANV2,
    SERV_THERMOSTAT,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import State, callback

from .const import CONF_FAN_MODE_MAPPING, CONF_LINKED_SWING_MODE
from .util import auto_fan_mode_mapping, fan_mode_for_percent
from .vendored.type_thermostats import Thermostat

_LOGGER = logging.getLogger(__name__)


class HeaterCoolerPlus(Thermostat):
    """Thermostat with a custom Fanv2 for non-standard fan / swing modes."""

    def __init__(self, *args: Any) -> None:
        # Initialise our plus-* attrs BEFORE super().__init__ because the
        # vendored Thermostat tail-calls self.async_update_state(state) to
        # seed HomeKit values, and via MRO that dispatches to our override
        # which reads these fields.
        self._plus_mapping: dict[str, int] | None = None
        self._plus_char_active = None
        self._plus_char_speed = None
        self._plus_char_swing = None
        self._plus_swing_off: str | None = None
        self._plus_swing_on: str | None = None
        super().__init__(*args)
        self._plus_setup_fan()
        self._plus_setup_swing()

    # --- Fanv2 provisioning -------------------------------------------------

    def _plus_get_or_create_fanv2(self) -> Any:
        """Return the Fanv2 service, creating a linked one if missing.

        If the vendored base class already added a Fanv2, that's the one we
        extend. Otherwise we add a fresh Fanv2 with just CHAR_ACTIVE (the
        minimal required characteristic) and link it to the primary
        Thermostat service.
        """
        try:
            return self.get_service(SERV_FANV2)
        except ValueError:
            pass

        serv_thermostat = self.get_service(SERV_THERMOSTAT)
        serv_fan = self.add_preload_service(SERV_FANV2, [CHAR_ACTIVE])
        serv_thermostat.add_linked_service(serv_fan)
        state = self.hass.states.get(self.entity_id)
        active = self._plus_compute_active(state) if state else 0
        self._plus_char_active = serv_fan.configure_char(
            CHAR_ACTIVE,
            value=active,
            setter_callback=self._plus_set_fan_active,
        )
        return serv_fan

    # --- Fan rotation-speed setup ------------------------------------------

    def _plus_setup_fan(self) -> None:
        """Attach a RotationSpeed characteristic if the base class skipped it."""
        if CHAR_ROTATION_SPEED in self.fan_chars:
            return
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return
        fan_modes: list[str] = list(state.attributes.get(ATTR_FAN_MODES) or [])
        if not fan_modes:
            return

        override = self.config.get(CONF_FAN_MODE_MAPPING) or {}
        mapping: dict[str, int]
        if override:
            mapping = {name: int(pct) for name, pct in override.items()}
        else:
            mapping = auto_fan_mode_mapping(fan_modes)
        if not mapping:
            return
        self._plus_mapping = mapping

        serv_fan = self._plus_get_or_create_fanv2()
        current_mode = state.attributes.get(ATTR_FAN_MODE)
        current_percent = mapping.get(current_mode, 100)

        self._plus_char_speed = serv_fan.configure_char(
            CHAR_ROTATION_SPEED,
            value=current_percent,
            properties={PROP_MIN_STEP: max(1, round(100 / len(mapping)))},
            setter_callback=self._plus_set_fan_speed,
        )
        self._plus_char_speed.display_name = "Fan Mode"

        _LOGGER.debug(
            "HeaterCoolerPlus attached RotationSpeed to %s with mapping %s",
            self.entity_id,
            mapping,
        )

    # --- Swing-mode setup ---------------------------------------------------

    def _plus_setup_swing(self) -> None:
        """Attach a SwingMode characteristic if the base class skipped it."""
        if not self.config.get(CONF_LINKED_SWING_MODE, True):
            return
        if CHAR_SWING_MODE in self.fan_chars:
            return  # base class (or our own fan setup above) handled it
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        if not features & ClimateEntityFeature.SWING_MODE:
            return
        swing_modes: list[str] = list(
            state.attributes.get(ATTR_SWING_MODES) or []
        )
        if not swing_modes:
            return

        off_mode, on_mode = self._plus_classify_swing(swing_modes)
        if on_mode is None:
            # Only an "off" mode (or no modes at all after filtering) —
            # nothing meaningful to toggle.
            return
        self._plus_swing_off = off_mode
        self._plus_swing_on = on_mode

        serv_fan = self._plus_get_or_create_fanv2()
        current = state.attributes.get(ATTR_SWING_MODE)
        value = 1 if current and current != off_mode else 0
        self._plus_char_swing = serv_fan.configure_char(
            CHAR_SWING_MODE,
            value=value,
            setter_callback=self._plus_set_swing,
        )
        self._plus_char_swing.display_name = "Swing Mode"

        _LOGGER.debug(
            "HeaterCoolerPlus attached SwingMode to %s: off=%s, on=%s",
            self.entity_id,
            off_mode,
            on_mode,
        )

    @staticmethod
    def _plus_classify_swing(
        swing_modes: list[str],
    ) -> tuple[str | None, str | None]:
        """Pick (off_mode, on_mode) from the entity's swing_modes list.

        off_mode is the mode whose name lowercases to 'off' (if any);
        on_mode is the first mode that isn't the off mode. Either may be
        None if the entity doesn't advertise that shape.
        """
        off_mode = next((m for m in swing_modes if m.lower() == "off"), None)
        on_mode = next((m for m in swing_modes if m != off_mode), None)
        return off_mode, on_mode

    # --- Utility ------------------------------------------------------------

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
        # Turning off here turns the whole climate entity off. Turning on is
        # a no-op — the entity is already on if HomeKit can see a slider,
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

    def _plus_set_swing(self, value: int) -> None:
        """Apple Home toggled the swing sub-control."""
        if value == 0:
            target = self._plus_swing_off
        elif value == 1:
            target = self._plus_swing_on
        else:
            return
        if target is None:
            return
        self.async_call_service(
            CLIMATE_DOMAIN,
            SERVICE_SET_SWING_MODE,
            {ATTR_ENTITY_ID: self.entity_id, ATTR_SWING_MODE: target},
        )

    # --- HA → HomeKit state push --------------------------------------------

    @callback
    def async_update_state(self, new_state: State) -> None:
        """Push HA state changes to our extra characteristics, then defer to super."""
        super().async_update_state(new_state)

        if self._plus_mapping is not None and self._plus_char_speed is not None:
            fan_mode = new_state.attributes.get(ATTR_FAN_MODE)
            if fan_mode in self._plus_mapping:
                self._plus_char_speed.set_value(self._plus_mapping[fan_mode])

        if self._plus_char_active is not None:
            self._plus_char_active.set_value(self._plus_compute_active(new_state))

        if (
            self._plus_char_swing is not None
            and self._plus_swing_off is not None
        ):
            current_swing = new_state.attributes.get(ATTR_SWING_MODE)
            if current_swing is not None:
                self._plus_char_swing.set_value(
                    0 if current_swing == self._plus_swing_off else 1
                )
