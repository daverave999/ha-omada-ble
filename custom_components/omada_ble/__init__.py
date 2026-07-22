"""Omada BLE Sensor integration for Home Assistant.

Receives BLE advertisement data from TP-Link Omada EAP access points via MQTT,
decodes ATC native (0x181A) and BTHome v2 (0xFCD2) formats, and creates
sensor entities in Home Assistant.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    CONF_MQTT_TOPIC,
    DEFAULT_MQTT_TOPIC,
    FORMAT_AUTO,
)
from .decoder import decode_omada_ble

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_MQTT_TOPIC, default=DEFAULT_MQTT_TOPIC): str,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Omada BLE from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    topic = entry.data.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)
    sensors = entry.data.get("sensors", [])

    # Build MAC → sensor config lookup (colon-stripped uppercase)
    mac_map: dict[str, dict[str, Any]] = {}
    for sensor in sensors:
        mac_clean = sensor["mac"].replace(":", "").upper()
        mac_map[mac_clean] = sensor

    # State storage: MAC → decoded values
    hass.data[DOMAIN][entry.entry_id] = {
        "mac_map": mac_map,
        "state": {},
        "topic": topic,
        "unsubscribe": None,
    }

    # Callback when MQTT message arrives
    @callback
    def _message_handler(msg):
        """Handle incoming MQTT messages from Omada EAPs."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Only process BLE data messages (have "data" and "mac" fields)
        if "data" not in payload or "mac" not in payload:
            return

        mac = payload["mac"]
        hex_data = payload["data"]

        if mac not in mac_map:
            return

        sensor_cfg = mac_map[mac]
        known_format = sensor_cfg.get("format", FORMAT_AUTO)

        decoded_formats = decode_omada_ble(hex_data, known_format)
        if not decoded_formats:
            _LOGGER.debug("No decodable data for %s", mac)
            return

        # Use the first successfully decoded format
        readings = list(decoded_formats.values())[0]

        # Add metadata
        readings["lastseen"] = payload.get("lastseen", "")
        readings["ap_mac"] = payload.get("apMac", "")
        readings["sensor_name"] = sensor_cfg["name"]

        hass.data[DOMAIN][entry.entry_id]["state"][mac] = readings

        # Fire event to trigger entity updates
        hass.bus.async_fire(f"{DOMAIN}_update_{mac}", {"mac": mac})

        _LOGGER.debug("Decoded %s: %s", mac, readings)

    # Subscribe via HA's MQTT integration (new API)
    from homeassistant.components import mqtt

    unsub = await mqtt.async_subscribe(hass, topic, _message_handler)
    hass.data[DOMAIN][entry.entry_id]["unsubscribe"] = unsub
    _LOGGER.info("Subscribed to MQTT topic: %s", topic)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unsubscribe from MQTT
    unsub = hass.data[DOMAIN].get(entry.entry_id, {}).get("unsubscribe")
    if unsub:
        unsub()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok