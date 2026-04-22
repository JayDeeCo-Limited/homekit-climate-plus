"""pyhap bridge lifecycle for homekit_climate_plus.

Owns the small HomeKit server that runs inside Home Assistant: starts it on
a configurable port, advertises it over the LAN via Home Assistant's shared
zeroconf instance, persists pairing state and accessory IDs across
restarts, registers one `HeaterCoolerPlus` accessory per configured
climate entity, and shuts down cleanly on HA stop. One
`HomeKitClimatePlusBridge` per configured YAML block — v0.1 supports a
single block.

The bridge uses HA's `HomeBridge` / `HomeDriver` subclasses (vendored)
rather than raw pyhap, because our `HeaterCoolerPlus` accessory — which
extends HA's `Thermostat` — expects the HomeDriver's IID-storage and
context plumbing.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from homeassistant.components import persistent_notification, zeroconf
from homeassistant.components.homekit.iidmanager import AccessoryIIDStorage
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from .const import CONF_ENTITY_CONFIG, CONF_LINKED_PRESET_MODES, DOMAIN
from .type_thermostats import (
    PLUS_CONFIG_NONE_PRESET,
    PLUS_CONFIG_PRESET,
    HeaterCoolerPlus,
    PresetSwitchAccessory,
    extract_exposable_presets,
)
from .vendored.accessories import HomeBridge, HomeDriver

_LOGGER = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    """Reduce `value` to lower-case letters / digits / underscores only."""
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or DOMAIN


class HomeKitClimatePlusBridge:
    """Own a pyhap AccessoryDriver + HomeBridge for one YAML block."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        port: int,
        pin: str | None = None,
        entity_config: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.hass = hass
        self.name = name
        self.port = port
        self.pin = pin
        self.entity_config: dict[str, dict[str, Any]] = entity_config or {}

        self._driver: HomeDriver | None = None
        self._bridge: HomeBridge | None = None
        self._iid_storage: AccessoryIIDStorage | None = None

    # --- Identity / paths ---------------------------------------------------

    @property
    def synthetic_entry_id(self) -> str:
        """Stable fake entry_id, used to key IID / pairing storage files."""
        return f"{DOMAIN}_{_slugify(self.name)}"

    @property
    def persist_path(self) -> str:
        """Absolute path where pyhap stores its pairing state file."""
        return str(
            Path(self.hass.config.path(STORAGE_DIR))
            / f"{DOMAIN}.{_slugify(self.name)}"
        )

    @property
    def stable_mac(self) -> str:
        """Deterministic, bridge-name-derived locally-administered MAC.

        Every HomeKit bridge in the same LAN needs a unique MAC — pyhap
        advertises it as the `id=` field in the `_hap._tcp` mDNS TXT
        record. HA's vendored HomeDriver intentionally initialises with
        EMPTY_MAC (00:00:00:00:00:00) to avoid pyhap's expensive random
        generation, expecting each caller to stamp a real MAC before
        `async_start`. Without this, our bridge collides with every
        other HA-spawned bridge (they all use EMPTY_MAC until stamped)
        and iOS mis-routes pair-verify requests to whichever sibling
        picks up the TCP connection first.
        """
        digest = hashlib.sha256(self.synthetic_entry_id.encode()).digest()
        first = (digest[0] & 0xFE) | 0x02  # locally-administered, unicast
        return ":".join(
            [f"{first:02X}"] + [f"{b:02X}" for b in digest[1:6]]
        )

    # --- Lifecycle ----------------------------------------------------------

    async def async_start(self) -> None:
        """Build and start the pyhap bridge. Idempotent."""
        if self._driver is not None:
            return

        async_zc_instance = await zeroconf.async_get_async_instance(self.hass)

        self._iid_storage = AccessoryIIDStorage(self.hass, self.synthetic_entry_id)
        await self._iid_storage.async_initialize()

        # HomeDriver (pyhap AccessoryDriver) reads characteristics.json
        # synchronously at init, and add_accessory reads persist_file
        # synchronously — both trigger HA's "blocking call inside event
        # loop" warning. Build everything in an executor thread, then the
        # main loop resumes with a fully-wired driver + bridge.
        def _build() -> tuple[HomeDriver, HomeBridge]:
            driver = HomeDriver(
                hass=self.hass,
                entry_id=self.synthetic_entry_id,
                bridge_name=self.name,
                entry_title=self.name,
                iid_storage=self._iid_storage,
                port=self.port,
                persist_file=self.persist_path,
                pincode=self.pin.encode() if self.pin else None,
                async_zeroconf_instance=async_zc_instance,
                loop=self.hass.loop,
            )
            bridge = HomeBridge(self.hass, driver, self.name)
            driver.add_accessory(accessory=bridge)
            return driver, bridge

        self._driver, self._bridge = await self.hass.async_add_executor_job(_build)

        # Stamp a stable non-zero MAC so the bridge advertises a unique
        # `id=` in its mDNS TXT record. Without this, we collide with every
        # other HA-spawned homekit bridge (they all use EMPTY_MAC at init)
        # and iPhones mis-route pair-verify requests.
        self._driver.state.mac = self.stable_mac

        self._register_climate_accessories()

        await self._driver.async_start()

        _LOGGER.info(
            "%s bridge '%s' listening on port %d (pin %s, persist %s, %d "
            "accessory/accessories registered)",
            DOMAIN,
            self.name,
            self.port,
            self._driver.state.pincode.decode(),
            self.persist_path,
            len(self.entity_config),
        )

        if not self._driver.state.paired:
            self._show_pairing_notification()

    def _show_pairing_notification(self) -> None:
        """Post a persistent notification with the setup code.

        We don't use HA's `async_show_setup_message` — it depends on stock
        homekit's runtime_data and QR-serving view. A plain text PIN is
        fine: Apple Home lets the user type the code manually via
        "More options…" on the Add Accessory screen.
        """
        assert self._driver is not None
        pin = self._driver.state.pincode.decode()
        message = (
            f"To pair **{self.name}** with Apple Home:\n\n"
            f"1. Open the **Home** app on iPhone\n"
            f"2. Tap **+** → **Add Accessory**\n"
            f"3. Tap **More options…** and select **{self.name}**\n"
            f"4. When asked, enter the setup code: **{pin}**\n\n"
            f"This notification can be dismissed once pairing is complete."
        )
        persistent_notification.async_create(
            self.hass,
            message,
            title=f"{DOMAIN}: pairing required",
            notification_id=f"{DOMAIN}_{self.synthetic_entry_id}_pairing",
        )

    def _register_climate_accessories(self) -> None:
        """Attach accessories to the bridge for every configured climate entity.

        Each climate entity gets one `HeaterCoolerPlus` (the main tile with
        temperature, mode, fan speed, swing). If the entity advertises
        preset support and has a `none` preset, each non-`none` preset
        also gets its own `PresetSwitchAccessory` — a standalone Switch
        tile labelled e.g. "Air Conditioner — Away". Separate accessories
        (not linked services) because Apple Home doesn't reliably label
        repeated linked services of the same type.

        AIDs are deterministic: climate entities sort alphabetically, each
        entity takes one AID for itself plus one per exposed preset. Adding
        or removing a climate entity in the middle of the list will shift
        downstream AIDs, which may cause iOS to treat those as new
        accessories on next sync.
        """
        assert self._bridge is not None
        assert self._driver is not None

        next_aid = 2
        for entity_id in sorted(self.entity_config):
            entity_conf = dict(self.entity_config[entity_id])
            state = self.hass.states.get(entity_id)
            if state is None:
                _LOGGER.warning(
                    "%s: entity %s not in state registry at startup — skipping",
                    DOMAIN,
                    entity_id,
                )
                continue
            display_name = (
                state.attributes.get(ATTR_FRIENDLY_NAME) or entity_id
            )

            # Main climate accessory.
            try:
                main = HeaterCoolerPlus(
                    self.hass,
                    self._driver,
                    display_name,
                    entity_id,
                    next_aid,
                    entity_conf,
                )
            except Exception:  # pragma: no cover — surface at runtime
                _LOGGER.exception(
                    "%s: failed to build HeaterCoolerPlus for %s",
                    DOMAIN,
                    entity_id,
                )
                continue
            self._bridge.add_accessory(main)
            _LOGGER.debug(
                "%s: registered %s as climate accessory aid=%d",
                DOMAIN,
                entity_id,
                next_aid,
            )
            next_aid += 1

            # Per-preset switch accessories (mutually exclusive by convention).
            if not entity_conf.get(CONF_LINKED_PRESET_MODES, True):
                continue
            exposable, none_preset = extract_exposable_presets(state)
            if not exposable or none_preset is None:
                continue
            for preset in exposable:
                preset_config = {
                    **entity_conf,
                    PLUS_CONFIG_PRESET: preset,
                    PLUS_CONFIG_NONE_PRESET: none_preset,
                }
                preset_display = f"{display_name} — {preset.title()}"
                try:
                    preset_acc = PresetSwitchAccessory(
                        self.hass,
                        self._driver,
                        preset_display,
                        entity_id,
                        next_aid,
                        preset_config,
                    )
                except Exception:
                    _LOGGER.exception(
                        "%s: failed to build preset %r switch for %s",
                        DOMAIN,
                        preset,
                        entity_id,
                    )
                    continue
                self._bridge.add_accessory(preset_acc)
                _LOGGER.debug(
                    "%s: registered preset switch '%s' for %s as aid=%d",
                    DOMAIN,
                    preset_display,
                    entity_id,
                    next_aid,
                )
                next_aid += 1

    async def async_stop(self) -> None:
        """Gracefully shut the bridge down. Safe to call more than once."""
        if self._driver is None:
            return
        await self._driver.async_stop()
        self._driver = None
        self._bridge = None
        self._iid_storage = None
        _LOGGER.info("%s bridge '%s' stopped", DOMAIN, self.name)
