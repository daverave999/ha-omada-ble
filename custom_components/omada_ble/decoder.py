"""BLE advertisement decoders for Omada BLE integration.

Supports:
  - ATC native format (Service UUID 0x181A) — pvvx/ATC_MiThermometer firmware
  - BTHome v2 format (Service UUID 0xFCD2) — generic BLE sensor protocol

Both are transmitted as raw hex in the Omada MQTT data field.
"""

from __future__ import annotations

import struct
import logging

from .const import UUID_ATC, UUID_BTHOME_V2, BTHOME_V2_OBJECTS

_LOGGER = logging.getLogger(__name__)


def parse_gap_service_data(hex_data: str) -> list[tuple[int, bytes]]:
    """Parse BLE advertisement data and extract (UUID, service_data) tuples.

    Handles the GAP layer (flags, service data, etc.) and returns
    just the service data payloads with their 16-bit UUIDs.
    """
    try:
        raw = bytes.fromhex(hex_data)
    except ValueError:
        _LOGGER.warning("Invalid hex data: %s", hex_data[:40])
        return []

    results: list[tuple[int, bytes]] = []
    i = 0
    while i < len(raw):
        if i + 1 >= len(raw):
            break
        ad_len = raw[i]
        if ad_len == 0:
            break
        if i + 1 + ad_len > len(raw):
            break

        ad_type = raw[i + 1]
        ad_data = raw[i + 2: i + 1 + ad_len]

        if ad_type == 0x16:  # Service Data - 16-bit UUID
            if len(ad_data) >= 2:
                uuid = struct.unpack_from("<H", ad_data, 0)[0]
                svc_payload = ad_data[2:]
                results.append((uuid, svc_payload))
        elif ad_type == 0x19 or ad_type == 0x20:
            # 32-bit or 128-bit UUID service data — skip for now
            pass

        i += 1 + ad_len

    return results


def decode_atc(svc_data: bytes) -> dict[str, float | int]:
    """Decode pvvx ATC native format (UUID 0x181A).

    Layout (15 bytes):
      MAC(6 BE) + temp(2 LE 0.01°C) + humi(2 LE 0.01%)
      + batt_mv(2 LE mV) + batt_pct(1) + counter(1) + flags(1)

    Returns dict with: temperature, humidity, battery, battery_mv, counter
    """
    if len(svc_data) < 15:
        _LOGGER.debug("ATC data too short: %d bytes", len(svc_data))
        return {}

    temp = struct.unpack_from("<h", svc_data, 6)[0] / 100.0
    humi = struct.unpack_from("<H", svc_data, 8)[0] / 100.0
    batt_mv = struct.unpack_from("<H", svc_data, 10)[0]
    batt_pct = svc_data[12]
    counter = svc_data[13]

    return {
        "temperature": round(temp, 2),
        "humidity": round(humi, 2),
        "battery": batt_pct,
        "battery_mv": batt_mv,
        "counter": counter,
    }


def decode_bthome_v2(svc_data: bytes) -> dict[str, float | int]:
    """Decode BTHome v2 format (UUID 0xFCD2).

    Layout:
      header(1) + TLV objects (obj_id, value_bytes...)

    Header byte:
      bit 7: encrypted (0=no, 1=yes)
      bit 6: BTHome v2 flag (should be 1)
      bits 0-5: reserved

    Object IDs follow the BTHome v2 specification.
    See: https://bthome.io/format/
    """
    if len(svc_data) < 2:
        return {}

    header = svc_data[0]
    encrypted = bool(header & 0x80)

    if encrypted:
        _LOGGER.debug("Encrypted BTHome packet — needs bindkey")
        return {}

    result: dict[str, float | int] = {}
    i = 1  # skip header byte

    while i < len(svc_data):
        obj_id = svc_data[i]

        if obj_id not in BTHOME_V2_OBJECTS:
            _LOGGER.debug("Unknown BTHome obj_id 0x%02x at offset %d", obj_id, i)
            break

        name, length = BTHOME_V2_OBJECTS[obj_id]

        # Variable-length text type
        if length is None:
            i += 1
            if i >= len(svc_data):
                break
            text_len = svc_data[i]
            i += 1
            text_val = svc_data[i: i + text_len].decode("utf-8", errors="replace")
            result[name] = text_val
            i += text_len
            continue

        if i + 1 + length > len(svc_data):
            _LOGGER.debug("BTHome obj 0x%02x truncated at offset %d", obj_id, i)
            break

        value_bytes = svc_data[i + 1: i + 1 + length]

        if obj_id == 0x02:  # temperature 0.01°C
            result["temperature"] = round(struct.unpack_from("<h", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x0A:  # temperature 0.1°C
            result["temperature"] = round(struct.unpack_from("<h", value_bytes, 0)[0] / 10.0, 1)
        elif obj_id == 0x03:  # humidity 0.01%
            result["humidity"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x0C:  # humidity 0.1%
            result["humidity"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 10.0, 1)
        elif obj_id in (0x01, 0x08):  # battery %
            result["battery"] = value_bytes[0]
        elif obj_id == 0x04:  # pressure 0.01 hPa
            result["pressure"] = round(struct.unpack_from("<I", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x0B:  # pressure 1 hPa
            result["pressure"] = struct.unpack_from("<I", value_bytes, 0)[0]
        elif obj_id == 0x05:  # illuminance 0.01 lux
            result["illuminance"] = round(struct.unpack_from("<I", value_bytes[:3].ljust(4, b"\x00"), 0)[0] / 100.0, 2)
        elif obj_id == 0x06:  # mass kg 0.01
            result["mass_kg"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x07:  # mass lb 0.01
            result["mass_lb"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x08:  # dewpoint 0.01°C
            result["dewpoint"] = round(struct.unpack_from("<h", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x09:  # count uint8
            result["count"] = value_bytes[0]
        elif obj_id == 0x0D:  # CO2 ppm
            result["co2"] = struct.unpack_from("<H", value_bytes, 0)[0]
        elif obj_id == 0x0E:  # PM2.5
            result["pm25"] = struct.unpack_from("<H", value_bytes, 0)[0]
        elif obj_id == 0x0F:  # PM10
            result["pm10"] = struct.unpack_from("<H", value_bytes, 0)[0]
        elif obj_id == 0x12:  # moisture 0.01%
            result["moisture"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x13:  # moisture 0.1%
            result["moisture"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 10.0, 1)
        elif obj_id == 0x20:  # voltage 0.001V
            result["voltage"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 1000.0, 3)
        elif obj_id == 0x24:  # voltage 0.1V
            result["voltage"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 10.0, 1)
        elif obj_id == 0x21:  # count uint16
            result["count"] = struct.unpack_from("<H", value_bytes, 0)[0]
        elif obj_id == 0x22:  # energy 0.001 kWh
            result["energy"] = round(struct.unpack_from("<I", value_bytes, 0)[0] / 1000.0, 3)
        elif obj_id == 0x23:  # power 0.01W
            result["power"] = round(struct.unpack_from("<I", value_bytes, 0)[0] / 100.0, 2)
        elif obj_id == 0x25:  # current 0.001A
            result["current"] = round(struct.unpack_from("<H", value_bytes, 0)[0] / 1000.0, 3)
        elif obj_id == 0x00:  # packet ID
            result["packet_id"] = value_bytes[0]
        elif obj_id == 0x14:  # on/off
            result["on"] = bool(value_bytes[0])
        elif obj_id == 0x15:  # door/window
            result["door_window"] = "open" if value_bytes[0] else "closed"
        elif obj_id == 0x16:  # motion
            result["motion"] = bool(value_bytes[0])
        elif obj_id == 0x17:  # light
            result["light"] = "light" if value_bytes[0] else "dark"
        elif obj_id == 0x18:  # button
            result["button"] = value_bytes[0]
        elif obj_id == 0x19:  # switch
            result["switch"] = bool(value_bytes[0])
        else:
            _LOGGER.debug("Unhandled BTHome obj 0x%02x: %s", obj_id, value_bytes.hex(" "))

        i += 1 + length

    return result


def decode_omada_ble(hex_data: str, known_format: str = "auto") -> dict[str, dict[str, float | int | str]]:
    """Decode BLE advertisement from Omada MQTT data field.

    Args:
        hex_data: Raw hex string from the Omada MQTT data field
        known_format: "atc", "bthome_v2", or "auto" (detect from UUID)

    Returns:
        Dict mapping format name ("atc" or "bthome_v2") to decoded values.
        Empty dict if no known service data found.
    """
    services = parse_gap_service_data(hex_data)
    results: dict[str, dict] = {}

    for uuid, svc_data in services:
        if uuid == UUID_ATC and known_format in ("atc", "auto"):
            decoded = decode_atc(svc_data)
            if decoded:
                results["atc"] = decoded
        elif uuid == UUID_BTHOME_V2 and known_format in ("bthome_v2", "auto"):
            decoded = decode_bthome_v2(svc_data)
            if decoded:
                results["bthome_v2"] = decoded

    return results