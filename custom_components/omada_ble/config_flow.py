"""Config flow for Omada BLE integration."""

from __future__ import annotations

import asyncio
import json
import re
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_MQTT_TOPIC,
    CONF_SENSOR_MAC,
    CONF_SENSOR_NAME,
    CONF_SENSOR_FORMAT,
    DEFAULT_MQTT_TOPIC,
    FORMAT_ATC,
    FORMAT_BTHOME_V2,
    FORMAT_AUTO,
)

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:?){6}$")


def normalize_mac(mac: str) -> str:
    """Normalize MAC to uppercase, no colons."""
    return mac.replace(":", "").upper()


class OmadaBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Omada BLE."""

    VERSION = 1

    def __init__(self):
        self.mqtt_topic: str = DEFAULT_MQTT_TOPIC
        self.sensors: list[dict] = []
        self.discovered: dict[str, dict] = {}  # MAC -> {rssi, ap_mac, lastseen}

    async def async_step_user(self, user_input=None):
        """Handle the initial step — MQTT topic configuration."""
        errors = {}

        if user_input is not None:
            self.mqtt_topic = user_input[CONF_MQTT_TOPIC]
            return await self.async_step_discover()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_MQTT_TOPIC, default=DEFAULT_MQTT_TOPIC): str,
            }),
            errors=errors,
            description_placeholders={},
        )

    async def async_step_discover(self, user_input=None):
        """Discover BLE devices from the MQTT topic."""
        if user_input is not None:
            selected = user_input.get("selected_macs", [])
            for mac in selected:
                mac_clean = normalize_mac(mac)
                self.sensors.append({
                    "mac": mac_clean,
                    "name": f"BLE {mac}",
                    "format": FORMAT_AUTO,
                })
            if user_input.get("add_manual", False) or not selected:
                return await self.async_step_sensor()
            return await self.async_step_sensor()

        # Subscribe to MQTT and collect devices for 5 seconds
        discovered_macs = await self._discover_devices()

        if not discovered_macs:
            return await self.async_step_sensor()

        # Build description with discovered devices listed
        device_lines = []
        for mac, info in discovered_macs.items():
            mac_display = f"{mac[0:2]}:{mac[2:4]}:{mac[4:6]}:{mac[6:8]}:{mac[8:10]}:{mac[10:12]}"
            rssi = info.get("rssi", "?")
            device_lines.append(f"• {mac_display} (RSSI: {rssi} dB)")

        self.discovered = discovered_macs

        schema = vol.Schema({
            vol.Optional("selected_macs"): vol.All(vol.Coerce(list), []),
            vol.Optional("add_manual", default=False): bool,
        })

        return self.async_show_form(
            step_id="discover",
            data_schema=schema,
            description_placeholders={
                "discovered_devices": "\n".join(device_lines),
                "count": str(len(discovered_macs)),
            },
        )

    async def _discover_devices(self) -> dict[str, dict]:
        """Subscribe to MQTT and collect BLE device MACs for 5 seconds."""
        from homeassistant.components import mqtt

        discovered: dict[str, dict] = {}
        topic = self.mqtt_topic

        @callback
        def _message_handler(msg):
            """Process incoming MQTT messages for device discovery."""
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return

            # Process telemetry messages with reported[] arrays
            if "reported" in payload:
                for device in payload.get("reported", []):
                    mac = normalize_mac(device.get("mac", ""))
                    if not mac:
                        continue
                    rssi_info = device.get("rssi", {})
                    avg_rssi = rssi_info.get("avg") if isinstance(rssi_info, dict) else None
                    existing = discovered.get(mac, {})
                    if avg_rssi is not None:
                        if existing.get("rssi") is None or avg_rssi > existing["rssi"]:
                            existing["rssi"] = avg_rssi
                    discovered[mac] = existing

            # Process BLE data messages with individual MAC + data
            if "mac" in payload and "data" in payload:
                mac = normalize_mac(payload["mac"])
                ap_mac = normalize_mac(payload.get("apMac", ""))
                existing = discovered.get(mac, {})
                existing["ap_mac"] = ap_mac
                existing["has_data"] = True
                discovered[mac] = existing

        try:
            unsub = await mqtt.async_subscribe(self.hass, topic, _message_handler)
            await asyncio.sleep(5)
            unsub()
        except Exception:
            pass

        return discovered

    async def async_step_sensor(self, user_input=None):
        """Add a sensor by MAC address."""
        errors = {}

        if user_input is not None:
            mac_input = user_input.get(CONF_SENSOR_MAC, "").strip()
            name = user_input.get(CONF_SENSOR_NAME, "").strip()
            fmt = user_input[CONF_SENSOR_FORMAT]

            if not mac_input:
                if self.sensors:
                    return await self.async_step_finish()
                errors[CONF_SENSOR_MAC] = "mac_required"

            elif not MAC_PATTERN.match(mac_input):
                errors[CONF_SENSOR_MAC] = "invalid_mac"

            else:
                mac = normalize_mac(mac_input)
                if any(s["mac"] == mac for s in self.sensors):
                    errors[CONF_SENSOR_MAC] = "mac_already_added"
                else:
                    if not name:
                        name = f"BLE {mac_input}"
                    self.sensors.append({
                        "mac": mac,
                        "name": name,
                        "format": fmt,
                    })
                    return await self.async_step_sensor()

        discovered_lines = []
        if self.discovered:
            for mac, info in self.discovered.items():
                mac_display = f"{mac[0:2]}:{mac[2:4]}:{mac[4:6]}:{mac[6:8]}:{mac[8:10]}:{mac[10:12]}"
                rssi = info.get("rssi", "?")
                discovered_lines.append(f"• {mac_display} (RSSI: {rssi} dB)")

        sensors_added = "\n".join(
            f"  • {s['name']} ({s['mac'][0:2]}:{s['mac'][2:4]}:{s['mac'][4:6]}:{s['mac'][6:8]}:{s['mac'][8:10]}:{s['mac'][10:12]}) — {s['format']}"
            for s in self.sensors
        ) if self.sensors else "None yet"

        return self.async_show_form(
            step_id="sensor",
            data_schema=vol.Schema({
                vol.Optional(CONF_SENSOR_MAC): str,
                vol.Optional(CONF_SENSOR_NAME): str,
                vol.Required(CONF_SENSOR_FORMAT, default=FORMAT_AUTO): vol.In({
                    FORMAT_AUTO: "Auto-detect",
                    FORMAT_ATC: "ATC native (0x181A)",
                    FORMAT_BTHOME_V2: "BTHome v2 (0xFCD2)",
                }),
            }),
            errors=errors,
            description_placeholders={
                "sensors_added": sensors_added,
                "discovered_devices": "\n".join(discovered_lines) if discovered_lines else "No devices discovered. Enter MAC manually.",
            },
        )

    async def async_step_finish(self, user_input=None):
        """Confirm and create the entry."""
        if not self.sensors:
            return await self.async_step_sensor()

        return self.async_create_entry(
            title=f"Omada BLE ({len(self.sensors)} sensor{'s' if len(self.sensors) != 1 else ''})",
            data={
                CONF_MQTT_TOPIC: self.mqtt_topic,
                "sensors": self.sensors,
            },
        )


class OmadaBleOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for adding/removing sensors."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage sensors."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        sensors = self.config_entry.data.get("sensors", [])
        sensor_list = "\n".join(
            f"  • {s['name']} ({s['mac'][0:2]}:{s['mac'][2:4]}:{s['mac'][4:6]}:{s['mac'][6:8]}:{s['mac'][8:10]}:{s['mac'][10:12]}) — {s['format']}"
            for s in sensors
        )

        return self.async_show_form(
            step_id="init",
            description_placeholders={"sensor_list": sensor_list},
        )