"""Pytest configuration for homekit_climate_plus.

Tests that need Home Assistant fixtures should explicitly request
`enable_custom_integrations` (and `hass` for async tests). We do NOT enable
it via `autouse`, because that forces non-async smoke tests to spin up the
async `hass` fixture and fails with `AttributeError: 'async_generator'
object has no attribute 'data'`.
"""
from __future__ import annotations

pytest_plugins = ("pytest_homeassistant_custom_component",)
