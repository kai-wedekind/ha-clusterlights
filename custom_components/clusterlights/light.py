"""Cluster Lights BLE light — modern bleak via HA's bluetooth stack."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    PLATFORM_SCHEMA as LIGHT_PLATFORM_SCHEMA,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICES, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import CHAR_UUID, DEFAULT_NAME, DOMAIN, EFFECTS

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = LIGHT_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_DEVICES): {
            cv.string: vol.Schema({vol.Optional(CONF_NAME): cv.string})
        }
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import the deprecated YAML platform into config entries.

    No entities are added here. Each configured MAC is handed to the import step,
    which creates a config entry and sets the entity up through the normal path --
    so a YAML user keeps working across the upgrade without touching anything, and
    ends up on the same code path as everyone else.
    """
    for mac, dev in config[CONF_DEVICES].items():
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={
                    CONF_ADDRESS: mac.upper(),
                    CONF_NAME: (dev or {}).get(CONF_NAME, DEFAULT_NAME),
                },
            )
        )
    _LOGGER.warning(
        "Configuring Cluster Lights via the YAML light platform is deprecated and has "
        "been imported into a config entry. Remove the 'platform: clusterlights' block "
        "from your configuration"
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up a cluster light from a config entry."""
    async_add_entities(
        [
            ClusterLight(
                hass,
                entry.data[CONF_ADDRESS].upper(),
                entry.data.get(CONF_NAME, DEFAULT_NAME),
            )
        ]
    )


class ClusterLight(LightEntity):
    """A single cluster light string controlled over BLE."""

    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(EFFECTS.keys())
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, mac: str, name: str) -> None:
        self.hass = hass
        self._mac = mac
        self._attr_name = None
        self._attr_unique_id = "clusterlights_" + mac.replace(":", "").lower()
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_effect = None
        self._lock = asyncio.Lock()
        self._attr_device_info = DeviceInfo(
            connections={("bluetooth", mac)},
            identifiers={(DOMAIN, format_mac(mac))},
            name=name,
            manufacturer="PerfectLED",
            model="Cluster Lights (BLE)",
        )

    async def _send(self, packets: list[bytes]) -> None:
        """Connect (patiently — these lights advertise slowly), write, disconnect."""
        async with self._lock:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self._mac, connectable=True
            )
            if ble_device is None:
                raise HomeAssistantError(
                    "Cluster light " + self._mac + " not heard right now "
                    "(it advertises slowly; the adapter needs to catch one first)."
                )
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self._mac,
                max_attempts=12,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self._mac, connectable=True
                ),
            )
            try:
                for p in packets:
                    await client.write_gatt_char(CHAR_UUID, p, response=False)
                    await asyncio.sleep(0.15)
            finally:
                await client.disconnect()

    async def async_turn_on(self, **kwargs: Any) -> None:
        packets = [bytes([0x01, 0x01, 0x01, 0x01])]
        if ATTR_BRIGHTNESS in kwargs:
            val = max(1, round(kwargs[ATTR_BRIGHTNESS] * 99 / 255))
            packets.append(bytes([0x03, 0x01, 0x01, val]))
        if kwargs.get(ATTR_EFFECT) in EFFECTS:
            packets.append(bytes([0x05, 0x01, 0x02, 0x03, EFFECTS[kwargs[ATTR_EFFECT]]]))
        await self._send(packets)
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if kwargs.get(ATTR_EFFECT) in EFFECTS:
            self._attr_effect = kwargs[ATTR_EFFECT]
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send([bytes([0x01, 0x01, 0x01, 0x00])])
        self._attr_is_on = False
        self.async_write_ha_state()
