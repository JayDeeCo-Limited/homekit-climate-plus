"""homekit_climate_plus integration.

Runs a self-contained pyhap HomeKit bridge alongside Home Assistant's stock
HomeKit Bridge, exposing `climate.*` entities as single accessories with
linked Fanv2, SwingMode, preset, and sensor services. See PRD.md for the
full spec.

Configuration paths:

* **YAML** — `configuration.yaml` → `async_setup` → auto-imports as a
  config entry (source `import`) → `async_setup_entry` builds the bridge.
* **UI**  — "Add Integration" in the Home Assistant UI → config flow
  (`config_flow.py`) → `async_setup_entry` builds the bridge.

Both paths converge on a single runtime code path.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import CoreState, Event, HomeAssistant, callback
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
    """Register YAML config and import it into a config entry if present."""
    domain_conf = config.get(DOMAIN)
    if domain_conf is None:
        return True

    # Skip import if we already have an entry for this bridge name — this
    # avoids creating a duplicate on every HA restart.
    name = domain_conf.get(CONF_NAME, DEFAULT_NAME)
    for existing in hass.config_entries.async_entries(DOMAIN):
        if existing.data.get(CONF_NAME) == name:
            return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=dict(domain_conf),
        )
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Spin up the pyhap bridge for a configured entry."""
    # Imported here (not at module top) so pure-Python unit tests can import
    # `.util` / `.const` without dragging the full HA homekit package into
    # collection — that package needs turbojpeg + libjpeg-turbo at import
    # time, which aren't worth installing just for unit tests.
    from .bridge import HomeKitClimatePlusBridge

    # Later changes via the Options flow come through entry.options;
    # initial creation data lives in entry.data. Options wins.
    entity_config = (
        entry.options.get(CONF_ENTITY_CONFIG)
        or entry.data.get(CONF_ENTITY_CONFIG, {})
    )

    bridge = HomeKitClimatePlusBridge(
        hass,
        name=entry.data[CONF_NAME],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        pin=entry.data.get(CONF_PIN),
        entity_config=entity_config,
    )

    async def _start(_event: Event | None = None) -> None:
        await bridge.async_start()

    async def _stop(_event: Event) -> None:
        await bridge.async_stop()

    # Wait for HA to finish setting up every other integration before we
    # build accessories — otherwise `hass.states.get(entity_id)` returns
    # None for any entity whose platform hasn't reached `add_entities` yet.
    if hass.state is CoreState.running:
        await _start()
    else:
        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start)
        )

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = bridge
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Tear down the bridge when the entry is removed / reloaded."""
    bridge = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if bridge is not None:
        await bridge.async_stop()
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the integration when the user edits entity selection."""
    await hass.config_entries.async_reload(entry.entry_id)
