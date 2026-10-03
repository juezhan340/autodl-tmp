import requests
BASE = "http://127.0.0.1:8000"

r = requests.get(f"{BASE}/api/rooms", timeout=10)
rooms = r.json()["data"]["rooms"]

for room in rooms:
    rid = room["room_id"]
    rd = requests.get(f"{BASE}/api/rooms/{rid}/devices", timeout=10)
    dev_data = rd.json().get("data", {})
    devs = [(k, v.get("device_type","?")) for k, v in dev_data.items()] if isinstance(dev_data, dict) else \
           [(d.get("device_id","?"), d.get("device_type","?")) for d in (dev_data or [])]

    rs = requests.get(f"{BASE}/api/rooms/{rid}/states", timeout=10)
    s = rs.json().get("data", {})

    print(f"\n=== {rid} ({len(devs)} device(s)) ===")
    print(f"  {s.get('temperature',0)/100:.1f}°C  {s.get('humidity',0)/100:.1f}%  {s.get('illuminance',0):.0f}lux")

    for did, dtype in devs:
        rd2 = requests.get(f"{BASE}/api/devices/{did}/attributes", timeout=10)
        attrs = rd2.json().get("data", {})
        onoff = attrs.get("1.OnOff.OnOff")
        level = attrs.get("1.LevelControl.CurrentLevel")
        temp = attrs.get("1.Thermostat.LocalTemperature") or attrs.get("1.TemperatureMeasurement.MeasuredValue")
        mode = attrs.get("1.LaundryWasherMode.CurrentMode")
        state = attrs.get("1.OperationalState.OperationalState")
        curtain = attrs.get("1.WindowCovering.CurrentPositionLiftPercent100ths")

        bits = []
        if onoff is not None:
            bits.append("ON" if onoff else "OFF")
        if level not in (None, "", "-"):
            bits.append(f"level={level}")
        if temp not in (None, "", "-"):
            bits.append(f"{float(temp)/100:.1f}°C")
        if mode is not None:
            bits.append(f"mode={mode}")
        if state is not None and state != 0:
            bits.append("running")
        if curtain is not None:
            bits.append(f"open={curtain/100:.0f}%")

        print(f"  [{dtype}] {did}  " + "  ".join(bits) if bits else "")
