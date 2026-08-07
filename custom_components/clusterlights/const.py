"""Constants for the Cluster Lights integration."""

from __future__ import annotations

DOMAIN = "clusterlights"
DEFAULT_NAME = "Cluster Light"

# Advertised BLE name of the controllers this was built against, e.g. LED-4-01-00000000.
# Used to filter the discovery pick-list; the manifest carries the same prefix as a
# bluetooth matcher so HA can offer the light on its own.
NAME_PREFIX = "LED-4-01"

# GATT write characteristic. Service fff0, notify fff4 (unused: these controllers are
# fire-and-forget, which is why the entity is assumed_state).
CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# Effect name -> mode flag, written as 05 01 02 03 <flag>.
EFFECTS: dict[str, int] = {
    "Wave": 0x01,
    "Phase": 0x02,
    "Phased Fade": 0x04,
    "Phased Twinkle": 0x08,
    "Fade": 0x10,
    "Fast Twinkle": 0x20,
    "Steady": 0x40,
}
