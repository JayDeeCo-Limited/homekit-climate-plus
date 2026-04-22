"""pyhap bridge lifecycle for homekit_climate_plus.

Owns the small HomeKit server that runs inside Home Assistant: starts it on
a configurable port, advertises it over the LAN via Home Assistant's shared
zeroconf instance, persists pairing state across restarts, and shuts it
down cleanly on HA stop. One `HomeKitClimatePlusBridge` per configured
block of YAML — v0.1 supports a single block.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver

from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class HomeKitClimatePlusBridge:
    """Own a pyhap AccessoryDriver + root Bridge for one YAML block."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        port: int,
        pin: str | None = None,
    ) -> None:
        self.hass = hass
        self.name = name
        self.port = port
        self.pin = pin
        self._driver: AccessoryDriver | None = None
        self._bridge: Bridge | None = None

    @property
    def persist_path(self) -> str:
        """Absolute path where pyhap stores its pairing state file."""
        slug = self.name.lower().replace(" ", "_").replace("-", "_")
        return str(
            Path(self.hass.config.path(STORAGE_DIR)) / f"{DOMAIN}.{slug}"
        )

    async def async_start(self) -> None:
        """Build and start the pyhap bridge. Idempotent."""
        if self._driver is not None:
            return

        async_zc_instance = await zeroconf.async_get_async_instance(self.hass)

        self._driver = AccessoryDriver(
            port=self.port,
            persist_file=self.persist_path,
            pincode=self.pin.encode() if self.pin else None,
            async_zeroconf_instance=async_zc_instance,
            loop=self.hass.loop,
        )
        self._bridge = Bridge(self._driver, self.name)
        self._driver.add_accessory(accessory=self._bridge)

        # v0.1 TODO: register HeaterCoolerPlus accessories for every entity
        # in the configured entity_config mapping.

        await self._driver.async_start()

        _LOGGER.info(
            "%s bridge '%s' listening on port %d (pin %s, persist %s)",
            DOMAIN,
            self.name,
            self.port,
            self._driver.state.pincode.decode(),
            self.persist_path,
        )

    async def async_stop(self) -> None:
        """Gracefully shut the bridge down. Safe to call more than once."""
        if self._driver is None:
            return
        await self._driver.async_stop()
        self._driver = None
        self._bridge = None
        _LOGGER.info("%s bridge '%s' stopped", DOMAIN, self.name)
