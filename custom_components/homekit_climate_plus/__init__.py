"""homekit_climate_plus integration.

Runs a self-contained pyhap HomeKit bridge alongside Home Assistant's stock
HomeKit Bridge, exposing `climate.*` entities as single accessories with
linked Fanv2, SwingMode, preset, and sensor services. See PRD.md for the
full spec.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.const import (
    CONF_NAME,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import CoreState, Event, HomeAssistant
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ENTITY_CONFIG,
    CONF_FAN_MODE_MAPPING,
    CONF_LINKED_BATTERY_SENSOR,
    CONF_LINKED_FAN,
    CONF_LINKED_HUMIDITY_SENSOR,
    CONF_LINKED_PRESET_MODES,
    CONF_LINKED_SWING_MODE,
    CONF_PIN,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_LINKED_FAN): cv.entity_id,
        vol.Optional(CONF_LINKED_SWING_MODE, default=True): cv.boolean,
        vol.Optional(CONF_LINKED_PRESET_MODES, default=True): cv.boolean,
        vol.Optional(CONF_FAN_MODE_MAPPING): vol.Schema(
            {cv.string: vol.All(int, vol.Range(min=0, max=100))}
        ),
        vol.Optional(CONF_LINKED_HUMIDITY_SENSOR): cv.entity_id,
        vol.Optional(CONF_LINKED_BATTERY_SENSOR): cv.entity_id,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_PIN): cv.string,
                vol.Required(CONF_ENTITY_CONFIG): vol.Schema(
                    {cv.entity_id: ENTITY_CONFIG_SCHEMA}
                ),
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Start the homekit_climate_plus bridge from YAML config."""
    domain_conf = config.get(DOMAIN)
    if domain_conf is None:
        return True

    # Imported here (not at module top) so that `custom_components.
    # homekit_climate_plus.util` and `.const` can be imported by tests
    # without dragging in the full HA `homekit` package — it has hard
    # system-library dependencies (turbojpeg, libjpeg-turbo, ffmpeg) that
    # aren't worth installing just for pure-Python unit tests.
    from .bridge import HomeKitClimatePlusBridge

    bridge = HomeKitClimatePlusBridge(
        hass,
        name=domain_conf[CONF_NAME],
        port=domain_conf[CONF_PORT],
        pin=domain_conf.get(CONF_PIN),
        entity_config=domain_conf.get(CONF_ENTITY_CONFIG, {}),
    )

    async def _start(_event: Event | None = None) -> None:
        await bridge.async_start()

    async def _stop(_event: Event) -> None:
        await bridge.async_stop()

    # Wait for HA to finish setting up every other integration before we
    # build accessories — otherwise `hass.states.get(entity_id)` returns
    # None for any entity whose platform hasn't reached `add_entities` yet,
    # and those accessories get silently skipped. For reloads (HA already
    # running), start immediately.
    if hass.state is CoreState.running:
        await _start()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["bridge"] = bridge
    hass.data[DOMAIN]["config"] = domain_conf
    return True
