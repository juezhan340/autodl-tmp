"""D1：分别抽户型和设备，生成 id、配对、命名，再随机初始 state。"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from new_demo.env.B_models import copy_json


STATIC = Path(__file__).resolve().parents[1] / "data_static"
DEFAULT_HOMES_PATH = STATIC / "D0_homes.jsonl"
DEFAULT_DEVICES_PATH = STATIC / "D0_devices.jsonl"

# 按户型大小：每房最少、每房最多、全屋目标台数
_SIZE_QUOTA = {
    "small": (1, 2, 5),
    "medium": (2, 3, 10),
    "large": (2, 3, 14),
}


def load_home_templates(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读十五种户型，只有房间，没有设备。"""
    return _read_jsonl(path or DEFAULT_HOMES_PATH)


def load_device_catalog(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读设备/传感器能力模板，条数以 jsonl 为准。"""
    return _read_jsonl(path or DEFAULT_DEVICES_PATH)


def make_home(
    seed: int,
    homes_path: str | Path | None = None,
    devices_path: str | Path | None = None,
) -> dict[str, Any]:
    """抽一套户型、挂若干设备，输出可进 B.reset 的 s0。种子不写进结果。"""
    rng = random.Random(seed)
    layout = copy_json(rng.choice(load_home_templates(homes_path)))
    catalog = load_device_catalog(devices_path)
    rooms = []
    for raw in layout["rooms"]:
        rooms.append(
            {
                "room_id": raw["room_id"],
                "display_name": raw["display_name"],
                "room_kind": raw["room_kind"],
                "device_ids": [],
            }
        )
    placed: list[dict[str, Any]] = []
    _place_required(rng, rooms, placed, catalog)
    min_per, max_per, target_total = _SIZE_QUOTA[layout["size"]]
    for room in rooms:
        while len(room["device_ids"]) < min_per:
            if not _place_in_room(rng, room, placed, catalog, max_per):
                break
    while len(placed) < target_total:
        candidates = [room for room in rooms if len(room["device_ids"]) < max_per]
        if not candidates:
            break
        room = rng.choice(candidates)
        if not _place_in_room(rng, room, placed, catalog, max_per):
            break
    for device in placed:
        _randomize_device_state(device, rng)
    return {
        "rooms": [
            {
                "room_id": room["room_id"],
                "display_name": room["display_name"],
                "device_ids": list(room["device_ids"]),
            }
            for room in rooms
        ],
        "devices": [
            {
                "device_id": item["device_id"],
                "room_id": item["room_id"],
                "display_name": item["display_name"],
                "kind": item["kind"],
                "device_type": item["device_type"],
                "state": copy_json(item["state"]),
                "actions": copy_json(item["actions"]),
                "available": True,
            }
            for item in placed
        ],
    }


def _place_required(
    rng: random.Random,
    rooms: list[dict[str, Any]],
    placed: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> None:
    """先保证空调、传感器、两盏灯，再按房间优先挂新家电。"""
    _place_matching(rng, rooms, placed, catalog, lambda item: item["device_type"] == "climate")
    _place_matching(rng, rooms, placed, catalog, lambda item: item["kind"] == "sensor")
    _place_matching(
        rng,
        rooms,
        placed,
        catalog,
        lambda item: item["device_type"] == "light" and _has_action(item, "set_percentage"),
    )
    _place_matching(
        rng,
        rooms,
        placed,
        catalog,
        lambda item: item["device_type"] == "light",
        prefer_new_room=True,
    )
    if sum(1 for item in placed if item["device_type"] == "light") < 2:
        _place_matching(rng, rooms, placed, catalog, lambda item: item["device_type"] == "light")
    for device_type in ("refrigerator", "oven", "dishwasher", "water_heater"):
        _place_matching(
            rng,
            rooms,
            placed,
            catalog,
            lambda item, wanted=device_type: item["device_type"] == wanted,
        )
    _place_matching(
        rng,
        rooms,
        placed,
        catalog,
        lambda item: item["device_type"] == "washer",
        room_kinds_first=("bath", "balcony"),
    )
    _place_matching(rng, rooms, placed, catalog, lambda item: item["device_type"] == "tv")
    _place_matching(rng, rooms, placed, catalog, lambda item: item["device_type"] == "humidifier")


def _place_matching(
    rng: random.Random,
    rooms: list[dict[str, Any]],
    placed: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    predicate,
    prefer_new_room: bool = False,
    room_kinds_first: tuple[str, ...] = (),
) -> bool:
    """放一台满足条件且房间允许的设备。"""
    items = [item for item in catalog if predicate(item)]
    rng.shuffle(items)
    if prefer_new_room:
        empty_first = [room for room in rooms if not room["device_ids"]]
        filled = [room for room in rooms if room["device_ids"]]
        room_order = empty_first + filled
    elif room_kinds_first:
        preferred = [room for kind in room_kinds_first for room in rooms if room["room_kind"] == kind]
        rest = [room for room in rooms if room not in preferred]
        room_order = preferred + rest
    else:
        room_order = list(rooms)
        rng.shuffle(room_order)
    for item in items:
        for room in room_order:
            if _can_place(room, item, placed):
                _attach(room, item, placed)
                return True
    return False


def _place_in_room(
    rng: random.Random,
    room: dict[str, Any],
    placed: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    max_per: int,
) -> bool:
    """往指定房间再挂一台尚未占用的目录设备。"""
    if len(room["device_ids"]) >= max_per:
        return False
    candidates = [item for item in catalog if _can_place(room, item, placed)]
    if not candidates:
        return False
    _attach(room, rng.choice(candidates), placed)
    return True


_UNIQUE_HOME_TYPES = {
    "tv",
    "water_heater",
    "washer",
    "dishwasher",
    "oven",
    "refrigerator",
    "humidifier",
}


def _can_place(room: dict[str, Any], item: dict[str, Any], placed: list[dict[str, Any]]) -> bool:
    """房间类型允许，同房不重复 catalog；电视等家电全屋最多一台。"""
    if room["room_kind"] not in item["allowed_room_kinds"]:
        return False
    if item["device_type"] in _UNIQUE_HOME_TYPES and any(
        dev["device_type"] == item["device_type"] for dev in placed
    ):
        return False
    used = {dev["catalog_id"] for dev in placed if dev["room_id"] == room["room_id"]}
    return item["catalog_id"] not in used


def _attach(room: dict[str, Any], item: dict[str, Any], placed: list[dict[str, Any]]) -> None:
    """生成 device_id / display_name，写入房间和设备两边。"""
    token = room["room_id"].removeprefix("room_")
    prefix = "sensor" if item["kind"] == "sensor" else "device"
    device_id = f"{prefix}_{token}_{item['id_token']}"
    device = {
        "catalog_id": item["catalog_id"],
        "device_id": device_id,
        "room_id": room["room_id"],
        "display_name": f"{room['display_name']}{item['name_stem']}",
        "kind": item["kind"],
        "device_type": item["device_type"],
        "state": copy_json(item["state"]),
        "actions": copy_json(item["actions"]),
    }
    room["device_ids"].append(device_id)
    placed.append(device)


def _has_action(item: dict[str, Any], action_name: str) -> bool:
    """目录模板是否公开该动作。"""
    return any(action.get("action") == action_name for action in item.get("actions", []))


def _randomize_device_state(device: dict[str, Any], rng: random.Random) -> None:
    """按该设备自己的 actions 随机初始 state，不按类型猜范围。"""
    state = device.setdefault("state", {})
    if "on" in state:
        state["on"] = rng.choice([True, False])
    mode_enum = _enum_for(device, "set_mode", "mode")
    if mode_enum and "mode" in state:
        state["mode"] = rng.choice(mode_enum)
    spec = _param_spec(device, "set_temperature", "value")
    if spec and "target" in state:
        state["target"] = _random_stepped(rng, spec)
    spec = _param_spec(device, "set_percentage", "value")
    if spec and "level" in state:
        value = _random_stepped(rng, spec)
        state["level"] = int(value) if spec.get("type") == "integer" else value
    if device.get("kind") != "sensor":
        return
    if "temperature" in state:
        state["temperature"] = round(rng.uniform(16.0, 32.0), 1)
    if "humidity" in state:
        state["humidity"] = round(rng.uniform(30.0, 80.0), 1)


def _enum_for(device: dict[str, Any], action_name: str, param_name: str) -> list[Any]:
    """读某个动作参数的 enum。"""
    spec = _param_spec(device, action_name, param_name)
    enum = spec.get("enum") if spec else None
    return list(enum) if isinstance(enum, list) and enum else []


def _param_spec(device: dict[str, Any], action_name: str, param_name: str) -> dict[str, Any] | None:
    """取出指定动作的参数约束。"""
    for action in device.get("actions", []):
        if action.get("action") != action_name:
            continue
        params = action.get("params") or {}
        spec = params.get(param_name)
        return spec if isinstance(spec, dict) else None
    return None


def _random_stepped(rng: random.Random, spec: dict[str, Any]) -> float:
    """在 minimum/maximum/step 上取一个点。"""
    minimum = float(spec["minimum"])
    maximum = float(spec["maximum"])
    step = float(spec["step"])
    steps = int(round((maximum - minimum) / step))
    return round(minimum + rng.randint(0, steps) * step, 4)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """读一行一个 JSON 对象的库文件。"""
    target = Path(path)
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = json.loads(stripped)
        if not isinstance(item, dict):
            raise ValueError(f"{target} line must be an object")
        rows.append(item)
    if not rows:
        raise ValueError(f"{target} is empty")
    return rows
