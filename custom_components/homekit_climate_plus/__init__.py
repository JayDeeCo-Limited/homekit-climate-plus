"""homekit_climate_plus integration.

Runs a self-contained pyhap HomeKit bridge alongside Home Assistant's stock
HomeKit Bridge, exposing `climate.*` entities as single accessories with
linked Fanv2, SwingMode, preset, and sensor services. See PRD.md for the
full spec.

This file currently implements only YAML config-schema registration. Bridge
lifecycle is a v0.1 TODO (see bridge.py).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
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
    """Register YAML config. Bridge startup lands in v0.1."""
    domain_conf = config.get(DOMAIN)
    if domain_conf is None:
        return True

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["config"] = domain_conf

    _LOGGER.info(
        "homekit_climate_plus scaffold loaded for %d entity/entities "
        "(bridge startup pending)",
        len(domain_conf.get(CONF_ENTITY_CONFIG, {})),
    )
    return True
