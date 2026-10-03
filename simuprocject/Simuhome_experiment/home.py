import json
import sys
import time
import requests

BASE = "http://127.0.0.1:8000"


def load_home(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "initial_home_config" in config:
        config = config["initial_home_config"]

    r = requests.post(f"{BASE}/api/simulation/reset", json=config, timeout=10)

    if r.status_code != 200:
        print(f"Failed: {r.status_code}")
        try:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(r.text[:500])
        sys.exit(1)

    meta = r.json()["data"]["meta"]
    print(f"Loaded: {meta['num_rooms']} room(s), {meta['num_devices']} device(s)")


def get_attrs(device_id):
    r = requests.get(f"{BASE}/api/devices/{device_id}/attributes", timeout=10)
    data = r.json().get("data", {})

    if isinstance(data, dict) and "attributes" in data:
        return data["attributes"]

    return data


def show_state():
    r = requests.get(f"{BASE}/api/rooms", timeout=10)
    rooms = r.json()["data"]["rooms"]

    for room in rooms:
        rid = room["room_id"]

        rd = requests.get(f"{BASE}/api/rooms/{rid}/devices", timeout=10)
        dev_data = rd.json().get("data", {})

        if isinstance(dev_data, dict):
            devs = [(k, v.get("device_type", "?")) for k, v in dev_data.items()]
        else:
            devs = [
                (d.get("device_id", "?"), d.get("device_type", "?"))
                for d in (dev_data or [])
            ]

        rs = requests.get(f"{BASE}/api/rooms/{rid}/states", timeout=10)
        s = rs.json().get("data", {})

        print(f"\n=== {rid} ({len(devs)} device(s)) ===")

        t = s.get("temperature", 0) / 100
        h = s.get("humidity", 0) / 100
        il = s.get("illuminance", 0)

        print(f"  {t:.1f}°C  {h:.1f}%  {il:.0f}lux")

        for did, dtype in devs:
            attrs = get_attrs(did)

            onoff = attrs.get("1.OnOff.OnOff")
            level = attrs.get("1.LevelControl.CurrentLevel")
            temp = (
                attrs.get("1.Thermostat.LocalTemperature")
                or attrs.get("1.TemperatureMeasurement.MeasuredValue")
            )
            mode = attrs.get("1.LaundryWasherMode.CurrentMode")
            state = attrs.get("1.OperationalState.OperationalState")

            bits = []

            if onoff is not None:
                bits.append("ON" if onoff else "OFF")

            if level not in (None, "", "-"):
                bits.append(f"level={level}")

            if temp not in (None, "", "-"):
                bits.append(f"{float(temp) / 100:.1f}°C")

            if mode is not None:
                bits.append(f"mode={mode}")

            if state is not None and state != 0:
                bits.append("running")

            if bits:
                print(f"  [{dtype}] {did}  " + "  ".join(bits))
            else:
                print(f"  [{dtype}] {did}")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "home_minimal.json"
    load_home(config_path)
    time.sleep(0.5)
    show_state()