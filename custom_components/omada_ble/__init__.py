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

from homeassistant.components import mqtt
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


def normalize_mac(mac: str) -> str:
    """Normalize MAC to uppercase, no colons."""
    return mac.replace(":", "").upper()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Omada BLE from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    topic = entry.data.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)
    sensors = entry.data.get("sensors", [])

    # Build MAC → sensor config lookup (normalized: uppercase, no colons)
    mac_map: dict[str, dict[str, Any]] = {}
    for sensor in sensors:
        mac_clean = normalize_mac(sensor["mac"])
        mac_map[mac_clean] = sensor
        _LOGGER.info("Registered sensor: mac=%s name=%s format=%s",
                      mac_clean, sensor.get("name"), sensor.get("format"))

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
            raw = msg.payload
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Only process BLE data messages (have "data" and "mac" fields)
        if "data" not in payload or "mac" not in payload:
            return

        raw_mac = payload["mac"]
        mac = normalize_mac(raw_mac)
        hex_data = payload["data"]

        _LOGGER.debug("Received MQTT message: mac=%s (raw=%s), data length=%d",
                       mac, raw_mac, len(hex_data))

        if mac not in mac_map:
            _LOGGER.debug("Unknown MAC: %s (not in mac_map: %s)",
                           mac, list(mac_map.keys()))
            return

        sensor_cfg = mac_map[mac]
        known_format = sensor_cfg.get("format", FORMAT_AUTO)

        decoded_formats = decode_omada_ble(hex_data, known_format)
        if not decoded_formats:
            _LOGGER.warning("No decodable data for %s (format=%s, hex=%s)",
                            mac, known_format, hex_data[:40])
            return

        # Use the first successfully decoded format
        fmt_name, readings = next(iter(decoded_formats.items()))
        _LOGGER.debug("Decoded %s via %s: %s", mac, fmt_name, readings)

        # Add metadata
        readings["lastseen"] = payload.get("lastseen", "")
        readings["ap_mac"] = normalize_mac(payload.get("apMac", ""))
        readings["sensor_name"] = sensor_cfg["name"]

        hass.data[DOMAIN][entry.entry_id]["state"][mac] = readings

        # Fire event to trigger entity updates
        hass.bus.async_fire(f"{DOMAIN}_update_{mac}", {"mac": mac})

    # Subscribe via HA's MQTT integration
    unsub = await mqtt.async_subscribe(hass, topic, _message_handler)
    hass.data[DOMAIN][entry.entry_id]["unsubscribe"] = unsub
    _LOGGER.info("Subscribed to MQTT topic: %s (watching %d MACs: %s)",
                 topic, len(mac_map), list(mac_map.keys()))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unsub = hass.data[DOMAIN].get(entry.entry_id, {}).get("unsubscribe")
    if unsub:
        unsub()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok