"""家电目录与设备自报校验：烤箱、冰箱、可调光灯、禁止的动作名。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from new_demo.env.B_home_env import HomeEnv
from new_demo.env.B_models import ToolCall
from new_demo.env.B_schema import DEVICE_TYPES, SUPPORTED_ACTIONS, ensure_valid_scenario, validate_scenario_dict
from new_demo.tests.C_test_run import _home, _scenario


def _wrap(home: dict[str, Any]) -> dict[str, Any]:
    """把家包装成最小 Scenario，task 不引用原卧室空调。"""
    return _scenario(
        home=home,
        user_request="x",
        task={
            "intent": "x",
            "conditions": [],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    )


def _kitchen_home() -> dict[str, Any]:
    """厨房烤箱和冰箱，外加一盏夜灯。"""
    return {
        "rooms": [
            {"room_id": "room_kitchen", "display_name": "厨房", "device_ids": ["device_kitchen_oven", "device_kitchen_fridge"]},
            {"room_id": "room_bedroom", "display_name": "卧室", "device_ids": ["device_bedroom_night_light", "device_bedroom_light"]},
        ],
        "devices": [
            {
                "device_id": "device_kitchen_oven",
                "room_id": "room_kitchen",
                "display_name": "厨房烤箱",
                "kind": "actuator",
                "device_type": "oven",
                "state": {"on": False, "mode": "bake", "target": 180.0},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                    {
                        "action": "set_mode",
                        "params": {"mode": {"type": "string", "enum": ["bake", "broil", "keep_warm"]}},
                    },
                    {
                        "action": "set_temperature",
                        "params": {"value": {"type": "number", "minimum": 50.0, "maximum": 250.0, "step": 5.0}},
                    },
                ],
                "available": True,
            },
            {
                "device_id": "device_kitchen_fridge",
                "room_id": "room_kitchen",
                "display_name": "厨房冰箱",
                "kind": "actuator",
                "device_type": "refrigerator",
                "state": {"on": True, "target": 4.0},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                    {
                        "action": "set_temperature",
                        "params": {"value": {"type": "number", "minimum": 2.0, "maximum": 8.0, "step": 0.5}},
                    },
                ],
                "available": True,
            },
            {
                "device_id": "device_bedroom_night_light",
                "room_id": "room_bedroom",
                "display_name": "卧室夜灯",
                "kind": "actuator",
                "device_type": "light",
                "state": {"on": False},
                "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}],
                "available": True,
            },
            {
                "device_id": "device_bedroom_light",
                "room_id": "room_bedroom",
                "display_name": "卧室主灯",
                "kind": "actuator",
                "device_type": "light",
                "state": {"on": True, "level": 80},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                    {
                        "action": "set_percentage",
                        "params": {"value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}},
                    },
                ],
                "available": True,
            },
        ],
    }


def test_device_types_include_new_appliances() -> None:
    """B 认 14 个类型，词表不含 set_brightness。"""
    assert "oven" in DEVICE_TYPES
    assert "refrigerator" in DEVICE_TYPES
    assert "humidifier" in DEVICE_TYPES
    assert "tv" in DEVICE_TYPES
    assert len(DEVICE_TYPES) == 14
    assert "set_brightness" not in SUPPORTED_ACTIONS
    assert "set_volume" not in SUPPORTED_ACTIONS


def test_climate_target_still_capped_by_its_actions() -> None:
    """空调 25 过、180 不过。"""
    home = _home()
    assert validate_scenario_dict(_wrap(home)) == []
    home["devices"][1]["state"]["target"] = 180.0
    errors = validate_scenario_dict(_wrap(home))
    assert any("target" in item for item in errors)


def test_oven_range_and_mode_are_self_reported() -> None:
    """烤箱 180 过、400 不过、bake 过、cool 不过。"""
    home = _kitchen_home()
    assert validate_scenario_dict(_wrap(home)) == []
    bad_temp = deepcopy(home)
    bad_temp["devices"][0]["state"]["target"] = 400.0
    assert any("target" in item for item in validate_scenario_dict(_wrap(bad_temp)))
    bad_mode = deepcopy(home)
    bad_mode["devices"][0]["state"]["mode"] = "cool"
    assert any("mode" in item for item in validate_scenario_dict(_wrap(bad_mode)))


def test_fridge_range() -> None:
    """冰箱 4 过、25 不过。"""
    home = _kitchen_home()
    bad = deepcopy(home)
    bad["devices"][1]["state"]["target"] = 25.0
    assert any("target" in item for item in validate_scenario_dict(_wrap(bad)))


def test_washer_mode_enum() -> None:
    """洗衣机 quick 过、cool 不过。"""
    home = {
        "rooms": [{"room_id": "room_bath", "display_name": "卫生间", "device_ids": ["device_bath_washer"]}],
        "devices": [
            {
                "device_id": "device_bath_washer",
                "room_id": "room_bath",
                "display_name": "卫生间洗衣机",
                "kind": "actuator",
                "device_type": "washer",
                "state": {"on": False, "mode": "quick"},
                "actions": [
                    {"action": "turn_on", "params": {}},
                    {"action": "turn_off", "params": {}},
                    {
                        "action": "set_mode",
                        "params": {"mode": {"type": "string", "enum": ["normal", "quick", "delicate", "rinse"]}},
                    },
                ],
                "available": True,
            }
        ],
    }
    assert validate_scenario_dict(_wrap(home)) == []
    home["devices"][0]["state"]["mode"] = "cool"
    assert validate_scenario_dict(_wrap(home))


def test_same_signature_set_temperature() -> None:
    """烤箱写入仍是 set_temperature + value。"""
    env = HomeEnv()
    env.reset(_wrap(_kitchen_home()))
    result = env.step(
        ToolCall(
            "execute_action",
            {"device_id": "device_kitchen_oven", "action": "set_temperature", "params": {"value": 200.0}},
            "t1",
        )
    )
    assert result.event.ok is True
    assert result.event.result["data"]["state_after"]["target"] == 200.0


def test_inspect_device_is_sparse() -> None:
    """烤箱 state 没有 level/position/current。"""
    env = HomeEnv()
    env.reset(_wrap(_kitchen_home()))
    result = env.step(ToolCall("inspect_device", {"device_id": "device_kitchen_oven"}, "t1"))
    state = result.event.result["data"]["device"]["state"]
    assert set(state) == {"on", "mode", "target"}


def test_unknown_action_volume_and_night_light_dim() -> None:
    """烤箱 set_volume、夜灯 set_percentage 都是 UNSUPPORTED_ACTION。"""
    env = HomeEnv()
    env.reset(_wrap(_kitchen_home()))
    volume = env.step(
        ToolCall(
            "execute_action",
            {"device_id": "device_kitchen_oven", "action": "set_volume", "params": {"value": 10}},
            "t1",
        )
    )
    assert volume.event.ok is False
    assert volume.event.error_code == "UNSUPPORTED_ACTION"
    dim = env.step(
        ToolCall(
            "execute_action",
            {"device_id": "device_bedroom_night_light", "action": "set_percentage", "params": {"value": 30}},
            "t2",
        )
    )
    assert dim.event.ok is False
    assert dim.event.error_code == "UNSUPPORTED_ACTION"


def test_dimmable_light_set_percentage() -> None:
    """主灯可以 set_percentage。"""
    env = HomeEnv()
    env.reset(_wrap(_kitchen_home()))
    result = env.step(
        ToolCall(
            "execute_action",
            {"device_id": "device_bedroom_light", "action": "set_percentage", "params": {"value": 30}},
            "t1",
        )
    )
    assert result.event.ok is True
    assert result.event.result["data"]["state_after"]["level"] == 30


def test_oven_out_of_range_is_bad_request() -> None:
    """烤箱 400：B 返回 BAD_REQUEST，state 不变。"""
    env = HomeEnv()
    env.reset(_wrap(_kitchen_home()))
    before = env.runtime_state["device_kitchen_oven"]["state"]["target"]
    result = env.step(
        ToolCall(
            "execute_action",
            {"device_id": "device_kitchen_oven", "action": "set_temperature", "params": {"value": 400.0}},
            "t1",
        )
    )
    assert result.event.ok is False
    assert result.event.error_code == "BAD_REQUEST"
    assert env.runtime_state["device_kitchen_oven"]["state"]["target"] == before


def test_old_switch_light_home_still_valid() -> None:
    """闸 2 那种只有 on 的灯和空调 7–32 仍能过 schema。"""
    ensure_valid_scenario(_wrap(_home()))
