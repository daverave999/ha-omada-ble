"""Constants for the Omada BLE integration."""

DOMAIN = "omada_ble"

# MQTT topic that Omada EAPs publish BLE data to
DEFAULT_MQTT_TOPIC = "homeassistant"

# BLE service UUIDs
UUID_ATC = 0x181A
UUID_BTHOME_V2 = 0xFCD2

# Config entry fields
CONF_MQTT_TOPIC = "mqtt_topic"
CONF_SENSOR_MAC = "sensor_mac"
CONF_SENSOR_NAME = "sensor_name"
CONF_SENSOR_FORMAT = "sensor_format"

# Sensor formats
FORMAT_ATC = "atc"
FORMAT_BTHOME_V2 = "bthome_v2"
FORMAT_AUTO = "auto"

# BTHome v2 object IDs: (name, byte_length)
BTHOME_V2_OBJECTS = {
    0x00: ("packet_id", 1),
    0x01: ("battery", 1),
    0x02: ("temperature_001", 2),    # int16 LE, 0.01°C
    0x03: ("humidity_001", 2),        # uint16 LE, 0.01%
    0x04: ("pressure_01", 4),         # uint32 LE, 0.01 hPa
    0x05: ("illuminance", 3),         # uint24 LE, 0.01 lux
    0x06: ("mass_kg", 2),            # uint16 LE, 0.01 kg
    0x07: ("mass_lb", 2),            # uint16 LE, 0.01 lb
    0x08: ("dewpoint", 2),           # int16 LE, 0.01°C
    0x09: ("count", 1),
    0x0A: ("temperature_1", 2),      # int16 LE, 0.1°C
    0x0B: ("pressure_1", 4),         # uint32 LE, 1 hPa
    0x0C: ("humidity_1", 2),         # uint16 LE, 0.1%
    0x0D: ("co2", 2),                # uint16 LE, 1 ppm
    0x0E: ("pm25", 2),               # uint16 LE, 1 μg/m³
    0x0F: ("pm10", 2),               # uint16 LE, 1 μg/m³
    0x10: ("voc", 2),                # uint16 LE, 1 ppb (not official, placeholder)
    0x11: ("gate_position", 1),       # uint8, 0-100%
    0x12: ("moisture_001", 2),       # uint16 LE, 0.01%
    0x13: ("moisture_1", 2),         # uint16 LE, 0.1%
    0x14: ("onoff", 1),              # uint8, 0/1
    0x15: ("door_window", 1),        # uint8, 0=closed 1=open
    0x16: ("motion", 1),             # uint8, 0=clear 1=motion
    0x17: ("light", 1),              # uint8, 0=dark 1=light
    0x18: ("button", 1),             # uint8, event codes
    0x19: ("switch", 1),            # uint8, 0=off 1=on
    0x1A: ("index", 2),             # uint16 LE
    0x20: ("voltage", 2),            # uint16 LE, 0.001 V
    0x21: ("count_16", 2),           # uint16 LE
    0x22: ("energy", 4),             # uint32 LE, 0.001 kWh
    0x23: ("power", 4),              # uint32 LE, 0.01 W
    0x24: ("voltage_1", 2),          # uint16 LE, 0.1 V
    0x25: ("current", 2),            # uint16 LE, 0.001 A
    0x26: ("rgb", 3),               # uint8 R, G, B
    0x27: ("text", None),            # variable length (next byte = len)
    0x3A: ("general", 1),            # uint8, generic value
    0x3D: ("button_event", 1),       # uint8
    0x3E: ("dimmer", 1),            # uint8, 0-100%
    0x44: ("sound", 1),              # uint8
}

# HA entity mappings for decoded values
ENTITY_MAP = {
    "temperature": {"device_class": "temperature", "unit": "°C", "icon": "mdi:thermometer"},
    "humidity": {"device_class": "humidity", "unit": "%", "icon": "mdi:water-percent"},
    "battery": {"device_class": "battery", "unit": "%", "icon": "mdi:battery"},
    "battery_mv": {"device_class": "voltage", "unit": "mV", "icon": "mdi:battery-outline"},
    "pressure": {"device_class": "atmospheric_pressure", "unit": "hPa", "icon": "mdi:gauge"},
    "co2": {"device_class": "carbon_dioxide", "unit": "ppm", "icon": "mdi:molecule-co2"},
    "pm25": {"device_class": "pm25", "unit": "μg/m³", "icon": "mdi:dust"},
    "illuminance": {"device_class": "illuminance", "unit": "lx", "icon": "mdi:brightness-5"},
    "voltage": {"device_class": "voltage", "unit": "V", "icon": "mdi:flash"},
}