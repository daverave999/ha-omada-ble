"""Sensor platform for Omada BLE integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_SENSOR_FORMAT,
    FORMAT_ATC,
    FORMAT_BTHOME_V2,
    FORMAT_AUTO,
    ENTITY_MAP,
)
from .decoder import decode_omada_ble

_LOGGER = logging.getLogger(__name__)

# Mapping from decoded keys to HA sensor entity properties
SENSOR_DEFS = {
    "temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "suffix": "temperature",
    },
    "humidity": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
        "icon": "mdi:water-percent",
        "suffix": "humidity",
    },
    "battery": {
        "device_class": SensorDeviceClass.BATTERY,
        "unit": PERCENTAGE,
        "icon": "mdi:battery",
        "suffix": "battery",
    },
    "battery_mv": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": "mV",
        "icon": "mdi:battery-outline",
        "suffix": "battery_voltage",
    },
    "pressure": {
        "device_class": SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        "unit": UnitOfPressure.HPA,
        "icon": "mdi:gauge",
        "suffix": "pressure",
    },
    "illuminance": {
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "unit": LIGHT_LUX,
        "icon": "mdi:brightness-5",
        "suffix": "illuminance",
    },
    "co2": {
        "device_class": SensorDeviceClass.CO2,
        "unit": CONCENTRATION_PARTS_PER_MILLION,
        "icon": "mdi:molecule-co2",
        "suffix": "co2",
    },
    "pm25": {
        "device_class": SensorDeviceClass.PM25,
        "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        "icon": "mdi:dust",
        "suffix": "pm25",
    },
    "voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit": UnitOfElectricPotential.VOLT,
        "icon": "mdi:flash",
        "suffix": "voltage",
    },
    "current": {
        "device_class": SensorDeviceClass.CURRENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "icon": "mdi:current-ac",
        "suffix": "current",
    },
    "power": {
        "device_class": SensorDeviceClass.POWER,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:flash",
        "suffix": "power",
    },
    "energy": {
        "device_class": SensorDeviceClass.ENERGY,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:lightning-bolt",
        "suffix": "energy",
    },
    "count": {
        "device_class": None,
        "unit": None,
        "icon": "mdi:counter",
        "suffix": "count",
    },
    "dewpoint": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:water-thermometer",
        "suffix": "dewpoint",
    },
    "moisture": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "unit": PERCENTAGE,
        "icon": "mdi:water",
        "suffix": "moisture",
    },
    "mass_kg": {
        "device_class": None,
        "unit": "kg",
        "icon": "mdi:weight",
        "suffix": "mass",
    },
}


class OmadaBleSensor(SensorEntity):
    """Representation of an Omada BLE sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        mac: str,
        name: str,
        sensor_key: str,
        device_class: SensorDeviceClass | None,
        unit: str | None,
        icon: str,
    ) -> None:
        """Initialize the sensor."""
        self._mac = mac
        self._sensor_key = sensor_key
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_name = f"{name} {sensor_key.replace('_', ' ').title()}"
        self._attr_unique_id = f"omada_ble_{mac}_{SENSOR_DEFS.get(sensor_key, {}).get('suffix', sensor_key)}"
        self._attr_state_class = "measurement" if device_class in (
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.HUMIDITY,
            SensorDeviceClass.PRESSURE,
            SensorDeviceClass.BATTERY,
            SensorDeviceClass.ILLUMINANCE,
            SensorDeviceClass.CO2,
            SensorDeviceClass.PM25,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.CURRENT,
            SensorDeviceClass.POWER,
            SensorDeviceClass.ENERGY,
        ) else None

        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=name,
            manufacturer="Xiaomi",
            model="LYWSD03MMC (pvvx firmware)",
            connections={("mac", f"{mac[0:2]}:{mac[2:4]}:{mac[4:6]}:{mac[6:8]}:{mac[8:10]}:{mac[10:12]}")},
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return self._device_info

    def update_state(self, readings: dict[str, Any]) -> None:
        """Update sensor state from decoded readings."""
        value = readings.get(self._sensor_key)
        if value is not None:
            self._attr_native_value = value
            self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Omada BLE sensor entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    mac_map: dict[str, dict] = data["mac_map"]

    entities: list[OmadaBleSensor] = []
    entity_map: dict[str, list[str]] = {}  # MAC → list of entity_ids

    for mac, sensor_cfg in mac_map.items():
        name = sensor_cfg.get("name", mac)

        # Create entities for all supported measurement types.
        # Only entities that actually receive data will show values.
        for sensor_key, sensor_def in SENSOR_DEFS.items():
            entity = OmadaBleSensor(
                mac=mac,
                name=name,
                sensor_key=sensor_key,
                device_class=sensor_def["device_class"],
                unit=sensor_def["unit"],
                icon=sensor_def["icon"],
            )
            entities.append(entity)
            entity_map.setdefault(mac, []).append(entity.entity_id)

    hass.data[DOMAIN]["_entity_map"] = entity_map
    async_add_entities(entities, True)

    # Register a state listener that updates entities when new data arrives
    async def _state_listener(event):
        """Handle state updates from the MQTT subscription."""
        for mac, readings in data.get("state", {}).items():
            for entity in entities:
                if entity._mac == mac:
                    entity.update_state(readings)

    # Store a callback for the __init__.py to trigger updates
    data["update_callback"] = lambda: hass.async_create_task(
        hass.bus.async_fire(f"{DOMAIN}_update", {})
    )

    hass.bus.async_listen(f"{DOMAIN}_update", _state_listener)