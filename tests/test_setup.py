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
