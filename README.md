# Omada BLE Sensor

Home Assistant custom integration that receives BLE sensor data from TP-Link Omada EAP access points via MQTT.

Omada EAPs with BLE capability (EAP723, EAP772, EAP670, etc.) can be configured as BLE gateways through the Omada SDN controller's **IoT Transport Streams** feature. They forward raw BLE advertisement data to an MQTT broker. This integration subscribes to that MQTT topic, decodes the advertisement data, and creates Home Assistant sensor entities.

## Supported formats

| Format | Service UUID | Devices |
|---|---|---|
| ATC native | 0x181A | Xiaomi LYWSD03MMC with pvvx firmware |
| BTHome v2 | 0xFCD2 | Generic — Xiaomi LYWSD03MMC (pvvx), BTHome-compatible sensors |

## Installation

### Via HACS (recommended)

1. Add this repository as a custom repository in HACS:
   `https://github.com/daverave999/ha-omada-ble`
2. Install "Omada BLE Sensor" from HACS
3. Restart Home Assistant

### Manual

1. Copy the `custom_components/omada_ble/` directory to your HA config's `custom_components/` directory
2. Restart Home Assistant

## Omada configuration

1. In the Omada SDN controller, go to **Site Settings → IoT Service → Bluetooth**
2. Enable BLE on your EAP(s)
3. Create an **IoT Transport Stream**:
   - **Server Type**: MQTT
   - **Server URL**: `mqtt://<your_ha_ip>:1883`
   - **Username/Password**: Your MQTT broker credentials
   - **Device Class**: Unclassified (or leave default)
   - **BLE Data Forwarding**: Enable
4. Save and apply

## Home Assistant setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Omada BLE Sensor**
3. Enter the MQTT topic your EAPs publish to (default: `homeassistant`)
4. The integration subscribes for 5 seconds and discovers any BLE devices the EAPs have seen, showing MAC addresses and signal strength
5. Select discovered devices to add, or enter a MAC manually
6. The advertisement format (ATC vs BTHome v2) is auto-detected from the data — no need to configure it manually
7. Sensors appear as devices with temperature, humidity, battery, and other entities depending on what the sensor broadcasts

## Supported BTHome v2 objects

| Object ID | Measurement | Unit | Resolution |
|---|---|---|---|
| 0x01, 0x08 | Battery | % | 1 |
| 0x02 | Temperature | °C | 0.01 |
| 0x03 | Humidity | % | 0.01 |
| 0x04 | Pressure | hPa | 0.01 |
| 0x0A | Temperature | °C | 0.1 |
| 0x0C | Humidity | % | 0.1 |
| 0x0D | CO₂ | ppm | 1 |
| 0x0E | PM2.5 | μg/m³ | 1 |
| 0x0F | PM10 | μg/m³ | 1 |
| 0x20 | Voltage | V | 0.001 |
| 0x21 | Count | — | 1 |

See [bthome.io/format](https://bthome.io/format/) for the full specification.

## ATC native format

The pvvx ATC firmware sends: MAC(6) + temp(2 LE 0.01°C) + humi(2 LE 0.01%) + batt_mv(2 LE mV) + batt%(1) + counter(1) + flags(1).

## Configuration

```yaml
# configuration.yaml (optional — config flow is preferred)
omada_ble:
  mqtt_topic: homeassistant  # default
```

## Credits

- [pvvx/ATC_MiThermometer](https://github.com/pvvx/ATC_MiThermometer) — custom firmware for Xiaomi LYWSD03MMC
- [BTHome](https://bthome.io/) — open BLE sensor protocol
- [TP-Link Omada](https://www.omadanetworks.com/) — EAP BLE gateway feature