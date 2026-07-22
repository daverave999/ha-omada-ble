"""Omada BLE Sensor integration for Home Assistant.

Receives BLE advertisement data from TP-Link Omada EAP access points via MQTT,
decodes ATC native (0x181A) and BTHome v2 (0xFCD2) formats, and creates
sensor entities in Home Assistant.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_MQTT_TOPIC,
    CONF_SENSOR_FORMAT,
    DEFAULT_MQTT_TOPIC,
    FORMAT_ATC,
    FORMAT_BTHOME_V2,
    FORMAT_AUTO,
)
from .decoder import decode_omada_ble

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_MQTT_TOPIC, default=DEFAULT_MQTT_TOPIC): cv.string,
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
    }

    # Subscribe to MQTT topic
    async def _message_handler(msg):
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

        # Dispatch state update to sensor entities
        for mac_key, entity_ids in hass.data[DOMAIN].get("_entity_map", {}).items():
            if mac_key == mac:
                for entity_id in entity_ids:
                    hass.helpers.event.async_call_later(0, lambda _: None)
                    # Trigger state update via coordinator-style refresh
                    hass.states.async_set(entity_id, None)

        _LOGGER.debug("Decoded %s: %s", mac, readings)

    # Subscribe via HA's MQTT integration
    await hass.components.mqtt.async_subscribe(topic, _message_handler)
    _LOGGER.info("Subscribed to MQTT topic: %s", topic)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok