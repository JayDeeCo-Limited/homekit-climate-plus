"""pyhap Bridge wrapper for homekit_climate_plus.

Owns the HomeKit bridge lifecycle: pyhap AccessoryDriver/Bridge setup,
pairing-state persistence under `.storage/homekit_climate_plus.<entry_id>`,
mDNS advertisement start/stop, and accessory registration.

TODO(v0.1): implement. See PRD.md §5.4.
"""
from __future__ import annotations
