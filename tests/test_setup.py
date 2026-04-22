"""Import-level smoke tests that don't pull in Home Assistant's homekit
package (which transitively needs turbojpeg, ffmpeg, and other system
libraries). Bridge and HeaterCoolerPlus construction lives in a future
integration test suite with a proper HA fixture — those modules can't be
meaningfully instantiated outside a running HA instance anyway.
"""
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
