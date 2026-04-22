"""Pytest configuration for homekit_climate_plus."""
from __future__ import annotations

import pytest

pytest_plugins = ("pytest_homeassistant_custom_component",)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading this integration from custom_components/ during tests."""
    yield
