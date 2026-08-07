"""Config flow for Cluster Lights.

Three ways in, because these controllers are awkward to find:

* Bluetooth discovery -- HA offers the light by itself when an adapter happens to hear
  one. That is the nicest path and the least likely to happen promptly: these strings
  advertise roughly once every 16-28 s, so "not showing up yet" is normal, not broken.
* A pick-list of already-discovered devices, so nobody has to copy a MAC by hand.
* Manual entry, which stays available precisely because discovery can take a while.

There is no connection test during setup, deliberately. Setup usually happens indoors
with the light outside and possibly unpowered, and a probe would fail for reasons that
say nothing about whether the config is right. The entity is assumed_state anyway, so a
wrong address surfaces on first use with a clear error rather than blocking setup here.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.device_registry import format_mac

from .const import DEFAULT_NAME, DOMAIN, NAME_PREFIX

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class ClusterLightsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cluster Lights."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_address: str | None = None
        self._discovered_name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a light the Bluetooth integration heard advertising."""
        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()
        self._discovered_address = discovery_info.address
        self._discovered_name = discovery_info.name or DEFAULT_NAME
        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered light."""
        assert self._discovered_address is not None
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data={
                    CONF_ADDRESS: self._discovered_address,
                    CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                },
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {vol.Optional(CONF_NAME, default=DEFAULT_NAME): str}
            ),
            description_placeholders={
                "name": self._discovered_name or DEFAULT_NAME,
                "address": self._discovered_address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow the user started from the UI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(format_mac(address))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                    },
                )

        # Offer anything already heard that looks like one of these controllers, so the
        # common case does not involve typing a MAC address from a phone app.
        current = self._async_current_ids()
        candidates = {
            info.address: f"{info.name or 'unknown'} ({info.address})"
            for info in bluetooth.async_discovered_service_info(self.hass, False)
            if (info.name or "").startswith(NAME_PREFIX)
            and format_mac(info.address) not in current
        }

        schema: dict[Any, Any] = {}
        if candidates:
            schema[vol.Required(CONF_ADDRESS)] = vol.In(candidates)
        else:
            schema[vol.Required(CONF_ADDRESS)] = str
        schema[vol.Optional(CONF_NAME, default=DEFAULT_NAME)] = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a device from the deprecated YAML light platform."""
        address = import_data[CONF_ADDRESS].upper()
        await self.async_set_unique_id(format_mac(address))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=import_data.get(CONF_NAME, DEFAULT_NAME),
            data={
                CONF_ADDRESS: address,
                CONF_NAME: import_data.get(CONF_NAME, DEFAULT_NAME),
            },
        )
