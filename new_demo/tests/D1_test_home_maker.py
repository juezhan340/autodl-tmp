"""D1：户型库与设备库分开抽，再配对 id 和名字。"""

from __future__ import annotations

import inspect
from collections import Counter

from new_demo.data import D1_home_maker
from new_demo.data.D1_home_maker import load_device_catalog, load_home_templates, make_home
from new_demo.env.B_schema import ensure_valid_scenario


def _wrap(home: dict) -> dict:
    """把 s0 包成最小 Scenario 以便走 schema。"""
    return {
        "scenario_id": "sc_d1",
        "blueprint_id": "bp_d1",
        "home": home,
        "user_request": "d1",
        "task": {
            "intent": "d1",
            "conditions": [],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
        "episode_config": {"max_turns": 10, "max_tool_calls_per_turn": 1},
    }


def test_catalog_counts() -> None:
    """十五种户型、二十一种设备。"""
    homes = load_home_templates()
    devices = load_device_catalog()
    assert len(homes) == 15
    assert Counter(item["size"] for item in homes) == {"small": 5, "medium": 5, "large": 5}
    assert len(devices) == 21
    assert all(item["catalog_id"] != "cat_heater_switch" for item in devices)
    dimmable = [item for item in devices if item["catalog_id"] in {"cat_ceiling_light", "cat_desk_lamp"}]
    assert len(dimmable) == 2
    assert all(any(action.get("action") == "set_percentage" for action in item["actions"]) for item in dimmable)
    night = next(item for item in devices if item["catalog_id"] == "cat_night_light")
    assert not any(action.get("action") == "set_percentage" for action in night["actions"])
    assert {item["size"] for item in homes} == {"small", "medium", "large"}
    assert all("devices" not in item for item in homes)
    assert all(not room.get("device_ids") for item in homes for room in item["rooms"])


def test_sampled_home_pairs_ids_and_names() -> None:
    """房间 device_ids 与设备 room_id 一致，显示名带房间名。"""
    for seed in range(20):
        home = make_home(seed)
        scenario = ensure_valid_scenario(_wrap(home))
        for room in scenario.home.rooms.values():
            for device_id in room.device_ids:
                device = scenario.home.devices[device_id]
                assert device.room_id == room.room_id
                assert device.display_name.startswith(room.display_name)
        types = {item.device_type for item in scenario.home.devices.values()}
        kinds = {item.kind for item in scenario.home.devices.values()}
        assert "climate" in types
        assert "sensor" in kinds
        assert "light" in types
        assert sum(1 for item in scenario.home.devices.values() if item.device_type == "light") >= 2


def test_seed_not_written_into_home() -> None:
    """抽样种子不进 s0。"""
    home = make_home(1)
    assert "seed" not in home
    assert "home_template_id" not in home


def test_same_seed_repeatable() -> None:
    """同一种子得到同一份 s0。"""
    assert make_home(7) == make_home(7)


def test_python_does_not_hardcode_a_house() -> None:
    """户型和设备名单在 jsonl 里，不在 Python 分支里写死五房七设备。"""
    source = inspect.getsource(D1_home_maker)
    assert "ht_small_1" not in source
    assert "device_bedroom_climate" not in source
    assert "卧室主灯" not in source

def _room_kind_index():
    """用户型库还原 room_id 到 room_kind。"""
    mapping = {}
    for home in load_home_templates():
        for room in home["rooms"]:
            mapping[room["room_id"]] = room["room_kind"]
    return mapping


def test_new_appliances_respect_rooms_and_ranges() -> None:
    """30 个种子：冰箱/烤箱只在厨房，洗衣机只在浴/阳台，加湿器不住厨房。"""
    kinds = _room_kind_index()
    saw_fridge = False
    for seed in range(30):
        home = make_home(seed)
        ensure_valid_scenario(_wrap(home))
        for device in home["devices"]:
            kind = kinds[device["room_id"]]
            if device["device_type"] in {"oven", "refrigerator", "dishwasher"}:
                assert kind == "kitchen"
            if device["device_type"] == "refrigerator":
                saw_fridge = True
                assert 2.0 <= device["state"]["target"] <= 8.0
            if device["device_type"] == "washer":
                assert kind in {"bath", "balcony"}
            if device["device_type"] == "humidifier":
                assert kind in {"bedroom", "living", "study"}
            if device["device_type"] == "tv":
                assert kind in {"living", "bedroom"}
            if device["device_type"] == "climate":
                assert 7.0 <= device["state"]["target"] <= 32.0
            if "night_light" in device["device_id"]:
                assert "level" not in device["state"]
            if device["device_type"] == "light" and any(
                action.get("action") == "set_percentage" for action in device["actions"]
            ):
                assert 0 <= device["state"]["level"] <= 100
    kitchen_homes = 0
    for seed in range(30):
        home = make_home(seed)
        if any(room["room_id"] == "room_kitchen" for room in home["rooms"]):
            kitchen_homes += 1
    assert saw_fridge or kitchen_homes == 0
    assert saw_fridge


def test_appliances_at_most_one_per_home() -> None:
    """电视、洗衣机、冰箱等家电全屋最多一台。"""
    unique = {"tv", "water_heater", "washer", "dishwasher", "oven", "refrigerator", "humidifier"}
    for seed in range(30):
        counts = {}
        for device in make_home(seed)["devices"]:
            if device["device_type"] in unique:
                counts[device["device_type"]] = counts.get(device["device_type"], 0) + 1
        assert all(value == 1 for value in counts.values())
