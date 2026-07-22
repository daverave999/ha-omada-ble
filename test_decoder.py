#!/usr/bin/env python3
"""Test decoder logic standalone (no HA imports)."""
import struct

UUID_ATC = 0x181A
UUID_BTHOME_V2 = 0xFCD2

BTHOME_V2_OBJECTS = {
    0x00: ("packet_id", 1), 0x01: ("battery", 1), 0x02: ("temperature_001", 2),
    0x03: ("humidity_001", 2), 0x04: ("pressure_01", 4), 0x0A: ("temperature_1", 2),
    0x0C: ("humidity_1", 2), 0x0D: ("co2", 2), 0x0E: ("pm25", 2), 0x0F: ("pm10", 2),
    0x09: ("count", 1), 0x21: ("count_16", 2), 0x20: ("voltage", 2),
}

def parse_gap_service_data(hex_data):
    try:
        raw = bytes.fromhex(hex_data)
    except ValueError:
        return []
    results = []
    i = 0
    while i < len(raw):
        if i + 1 >= len(raw): break
        ad_len = raw[i]
        if ad_len == 0: break
        if i + 1 + ad_len > len(raw): break
        ad_type = raw[i + 1]
        ad_data = raw[i + 2: i + 1 + ad_len]
        if ad_type == 0x16 and len(ad_data) >= 2:
            uuid = struct.unpack_from("<H", ad_data, 0)[0]
            results.append((uuid, ad_data[2:]))
        i += 1 + ad_len
    return results

def decode_atc(svc_data):
    if len(svc_data) < 15: return {}
    return {
        "temperature": round(struct.unpack_from("<h", svc_data, 6)[0] / 100.0, 2),
        "humidity": round(struct.unpack_from("<H", svc_data, 8)[0] / 100.0, 2),
        "battery": svc_data[12],
        "battery_mv": struct.unpack_from("<H", svc_data, 10)[0],
        "counter": svc_data[13],
    }

def decode_bthome_v2(svc_data):
    if len(svc_data) < 2: return {}
    if svc_data[0] & 0x80: return {}
    result = {}
    i = 1
    while i < len(svc_data):
        obj_id = svc_data[i]
        if obj_id not in BTHOME_V2_OBJECTS: break
        name, length = BTHOME_V2_OBJECTS[obj_id]
        if i + 1 + length > len(svc_data): break
        vb = svc_data[i + 1: i + 1 + length]
        if obj_id == 0x02: result["temperature"] = round(struct.unpack_from("<h", vb, 0)[0] / 100.0, 2)
        elif obj_id == 0x0A: result["temperature"] = round(struct.unpack_from("<h", vb, 0)[0] / 10.0, 1)
        elif obj_id == 0x03: result["humidity"] = round(struct.unpack_from("<H", vb, 0)[0] / 100.0, 2)
        elif obj_id == 0x0C: result["humidity"] = round(struct.unpack_from("<H", vb, 0)[0] / 10.0, 1)
        elif obj_id in (0x01, 0x08): result["battery"] = vb[0]
        elif obj_id == 0x00: result["packet_id"] = vb[0]
        elif obj_id == 0x09: result["count"] = vb[0]
        elif obj_id == 0x21: result["count"] = struct.unpack_from("<H", vb, 0)[0]
        i += 1 + length
    return result

def decode_omada_ble(hex_data, known_format="auto"):
    results = {}
    for uuid, svc_data in parse_gap_service_data(hex_data):
        if uuid == UUID_ATC and known_format in ("atc", "auto"):
            d = decode_atc(svc_data)
            if d: results["atc"] = d
        elif uuid == UUID_BTHOME_V2 and known_format in ("bthome_v2", "auto"):
            d = decode_bthome_v2(svc_data)
            if d: results["bthome_v2"] = d
    return results

# === TESTS ===
r = decode_atc(parse_gap_service_data('02010612161a18e05db138c1a42c0a76118d0b649c04')[0][1])
assert r['temperature'] == 26.04; assert r['humidity'] == 44.70; assert r['battery'] == 100; assert r['battery_mv'] == 2957
print(f"ATC OK: {r}")

r2 = decode_bthome_v2(parse_gap_service_data('0201060e16d2fc400022016402d90e03db0b')[0][1])
assert r2['temperature'] == 38.01; assert r2['humidity'] == 30.35; assert r2['battery'] == 100
print(f"BTHome v2 OK: {r2}")

assert 'atc' in decode_omada_ble('02010612161a18e05db138c1a42c0a76118d0b649c04', 'auto')
assert 'bthome_v2' in decode_omada_ble('0201060e16d2fc400022016402d90e03db0b', 'auto')

r3 = decode_atc(bytes.fromhex('e05db138c1a443090915400c64c504'))
assert r3['temperature'] == 23.71; assert r3['humidity'] == 53.85
print(f"ATC original: {r3}")

r4 = decode_bthome_v2(bytes.fromhex('4000c5016402ed0903f712'))
print(f"BT_therm_2: {r4}")

r5 = decode_bthome_v2(bytes.fromhex('4000bd016402950c032b0f'))
print(f"BT_therm_3: {r5}")

assert decode_bthome_v2(bytes.fromhex('C0000000')) == {}
assert decode_bthome_v2(bytes.fromhex('400AE601'))['temperature'] == 48.6
assert parse_gap_service_data('') == []
assert parse_gap_service_data('020106') == []

print("\nAll tests passed!")