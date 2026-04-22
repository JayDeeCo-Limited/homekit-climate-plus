"""Config flow for homekit_climate_plus.

Two entry paths:

1. **UI** — `async_step_user`: the user clicks **Add Integration**,
   picks a bridge name + port + optional PIN, then chooses one or
   more `climate.*` entities to expose. Each selected entity gets a
   minimal empty per-entity config; advanced per-entity tuning
   (fan_mode_mapping, linked_swing_mode, linked_humidity_sensor, …)
   still goes through the entry's options after creation, or YAML.

2. **YAML import** — `async_step_import`: when the integration is
   configured in `configuration.yaml`, `async_setup` creates an import
   flow with the YAML block verbatim as `data`. The entry looks
   identical to one made via the UI, so downstream `async_setup_entry`
   handles both the same way.

The options flow (`HomeKitClimatePlusOptionsFlow`) lets the user
add or remove entities after setup without tearing the bridge down —
the entry listener in `__init__.py` reloads the integration on
options change, which rebuilds the bridge with the new entity list.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITY_CONFIG,
    CONF_PIN,
    CONF_PORT,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
)


def _climate_entity_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="climate", multiple=True)
    )


class HomeKitClimatePlusConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for homekit_climate_plus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """First user-facing step: bridge identity + which entities to bridge."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME]
            entities: list[str] = user_input.get("entities", [])
            await self.async_set_unique_id(f"{DOMAIN}:{name}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=name,
                data={
                    CONF_NAME: name,
                    CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                    CONF_PIN: user_input.get(CONF_PIN) or None,
                    CONF_ENTITY_CONFIG: {eid: {} for eid in entities},
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    int, vol.Range(min=1024, max=65535)
                ),
                vol.Optional(CONF_PIN, default=""): str,
                vol.Required("entities", default=[]): _climate_entity_selector(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_import(
        self, user_input: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """YAML import: mirror the YAML block as an entry, no user interaction."""
        name = user_input.get(CONF_NAME) or DEFAULT_NAME
        await self.async_set_unique_id(f"{DOMAIN}:{name}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=name,
            data={
                CONF_NAME: name,
                CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                CONF_PIN: user_input.get(CONF_PIN),
                CONF_ENTITY_CONFIG: user_input.get(CONF_ENTITY_CONFIG, {}),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HomeKitClimatePlusOptionsFlow:
        return HomeKitClimatePlusOptionsFlow(config_entry)


class HomeKitClimatePlusOptionsFlow(config_entries.OptionsFlow):
    """Options flow: edit the list of climate entities after initial setup.

    Do NOT assign `self.config_entry` in __init__ — from HA 2024.x onward
    it's a read-only property on the base class, raising
    `AttributeError: property 'config_entry' of OptionsFlow has no
    setter`. The base class wires the entry via context; reading
    `self.config_entry` inside step methods works fine.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        current_entity_config: dict[str, dict[str, Any]] = (
            self.config_entry.options.get(CONF_ENTITY_CONFIG)
            or self.config_entry.data.get(CONF_ENTITY_CONFIG, {})
        )

        if user_input is not None:
            selected: list[str] = user_input.get("entities", [])
            # Preserve existing per-entity config for entities still selected;
            # new entities get a blank dict.
            new_entity_config = {
                eid: current_entity_config.get(eid, {}) for eid in selected
            }
            return self.async_create_entry(
                title="",
                data={CONF_ENTITY_CONFIG: new_entity_config},
            )

        schema = vol.Schema(
            {
                vol.Required(
                    "entities", default=list(current_entity_config.keys())
                ): _climate_entity_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
