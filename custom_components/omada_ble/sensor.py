"""Sensor platform for Omada BLE integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfPressure,
    CONCENTRATION_PARTS_PER_MILLION,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    LIGHT_LUX,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FORMAT_ATC, FORMAT_BTHOME_V2, FORMAT_AUTO

_LOGGER = logging.getLogger(__name__)

# Measurement keys the decoder can produce, mapped to HA sensor properties.
# Only entities for keys that actually appear in decoded data will show values.
SENSOR_DEFS = {
    "temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "suffix": "temperature",
    },
    "humidity": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "icon": "mdi:water-percent",
        "suffix": "humidity",
    },
    "battery": {
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "icon": "mdi:battery",
        "suffix": "battery",
    },
    "battery_mv": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "mV",
        "icon": "mdi:battery-outline",
        "suffix": "battery_voltage",
    },
    "pressure": {
        "device_class": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.HPA,
        "icon": "mdi:gauge",
        "suffix": "pressure",
    },
    "illuminance": {
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": LIGHT_LUX,
        "icon": "mdi:brightness-5",
        "suffix": "illuminance",
    },
    "co2": {
        "device_class": SensorDeviceClass.CO2,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": CONCENTRATION_PARTS_PER_MILLION,
        "icon": "mdi:molecule-co2",
        "suffix": "co2",
    },
    "pm25": {
        "device_class": SensorDeviceClass.PM25,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        "icon": "mdi:dust",
        "suffix": "pm25",
    },
    "pm10": {
        "device_class": SensorDeviceClass.PM10,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        "icon": "mdi:dust",
        "suffix": "pm10",
    },
    "voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "icon": "mdi:flash",
        "suffix": "voltage",
    },
    "dewpoint": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:water-thermometer",
        "suffix": "dewpoint",
    },
    "count": {
        "device_class": None,
        "state_class": None,
        "unit": None,
        "icon": "mdi:counter",
        "suffix": "count",
    },
}

# Measurement keys that each format typically produces.
# Used to create only relevant entities instead of all possible ones.
FORMAT_DEFAULT_KEYS = {
    FORMAT_ATC: {"temperature", "humidity", "battery", "battery_mv"},
    FORMAT_BTHOME_V2: {"temperature", "humidity", "battery"},
    FORMAT_AUTO: {"temperature", "humidity", "battery"},
}


class OmadaBleSensor(SensorEntity):
    """Representation of an Omada BLE sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        mac: str,
        name: str,
        sensor_key: str,
        sensor_def: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        self._mac = mac
        self._sensor_key = sensor_key
        self._attr_device_class = sensor_def.get("device_class")
        self._attr_state_class = sensor_def.get("state_class")
        self._attr_native_unit_of_measurement = sensor_def.get("unit")
        self._attr_icon = sensor_def.get("icon")
        suffix = sensor_def.get("suffix", sensor_key)
        self._attr_name = f"{name} {suffix.replace('_', ' ').title()}"
        self._attr_unique_id = f"omada_ble_{mac}_{suffix}"

        mac_formatted = f"{mac[0:2]}:{mac[2:4]}:{mac[4:6]}:{mac[6:8]}:{mac[8:10]}:{mac[10:12]}"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=name,
            manufacturer="Xiaomi",
            model="LYWSD03MMC (pvvx firmware)",
            connections={("mac", mac_formatted)},
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return self._device_info

    async def async_added_to_hass(self) -> None:
        """Register for state updates when entity is added to HA."""
        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_update_{self._mac}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, event) -> None:
        """Handle state update event from the integration."""
        entry_data = self.hass.data.get(DOMAIN, {})
        for entry_id, data in entry_data.items():
            if not isinstance(data, dict):
                continue
            state = data.get("state", {})
            if self._mac in state:
                readings = state[self._mac]
                value = readings.get(self._sensor_key)
                if value is not None:
                    self._attr_native_value = value
                    self.async_write_ha_state()
                return


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada BLE sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    mac_map: dict[str, dict] = data["mac_map"]

    entities: list[OmadaBleSensor] = []

    for mac, sensor_cfg in mac_map.items():
        name = sensor_cfg.get("name", mac)
        fmt = sensor_cfg.get("format", FORMAT_AUTO)

        # Create entities only for measurement types the format typically produces
        default_keys = FORMAT_DEFAULT_KEYS.get(fmt, FORMAT_DEFAULT_KEYS[FORMAT_AUTO])
        for sensor_key in default_keys:
            if sensor_key not in SENSOR_DEFS:
                continue
            entity = OmadaBleSensor(
                mac=mac,
                name=name,
                sensor_key=sensor_key,
                sensor_def=SENSOR_DEFS[sensor_key],
            )
            entities.append(entity)

    async_add_entities(entities, True)
    _LOGGER.info("Added %d sensor entities for %d devices", len(entities), len(mac_map))