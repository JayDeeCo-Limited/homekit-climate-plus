"""Smoke tests for the scaffold."""
from __future__ import annotations


def test_config_schema_importable() -> None:
    from custom_components.homekit_climate_plus import CONFIG_SCHEMA

    assert CONFIG_SCHEMA is not None


def test_const_domain_matches_manifest() -> None:
    import json
    import pathlib

    from custom_components.homekit_climate_plus.const import DOMAIN

    manifest_path = (
        pathlib.Path(__file__).parent.parent
        / "custom_components"
        / "homekit_climate_plus"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["domain"] == DOMAIN


def test_bridge_can_be_instantiated_without_starting() -> None:
    """Construction alone must not touch the network, filesystem, or pyhap."""
    from unittest.mock import MagicMock

    from custom_components.homekit_climate_plus.bridge import (
        HomeKitClimatePlusBridge,
    )

    hass = MagicMock()
    hass.config.path.return_value = "/tmp/ha-storage"

    bridge = HomeKitClimatePlusBridge(
        hass,
        name="Climate Bridge",
        port=21065,
        pin=None,
        entity_config={
            "climate.daikin_ac": {},
            "climate.bedroom_ac": {"linked_swing_mode": False},
        },
    )

    assert bridge.name == "Climate Bridge"
    assert bridge.port == 21065
    assert bridge.pin is None
    assert bridge.persist_path.endswith(
        "homekit_climate_plus.climate_bridge"
    )
    assert bridge.synthetic_entry_id == "homekit_climate_plus_climate_bridge"
    assert set(bridge.entity_config) == {
        "climate.daikin_ac",
        "climate.bedroom_ac",
    }


def test_heater_cooler_plus_is_a_thermostat_subclass() -> None:
    """Structural sanity: HeaterCoolerPlus inherits from the vendored Thermostat."""
    from custom_components.homekit_climate_plus.type_thermostats import (
        HeaterCoolerPlus,
    )
    from custom_components.homekit_climate_plus.vendored.type_thermostats import (
        Thermostat,
    )

    assert issubclass(HeaterCoolerPlus, Thermostat)
