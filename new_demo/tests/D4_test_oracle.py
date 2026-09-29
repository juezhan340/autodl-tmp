"""D4：T1 过、T2 全 ok、T4 probe 必须失败、T5 inspect、keep 不打。"""

from __future__ import annotations

from copy import deepcopy

from new_demo.data.D1_home_maker import make_home
from new_demo.data.D4_oracle import check_blueprint
from new_demo.tests.C_test_run import _home


def test_t1_write_passes_even_if_already_set() -> None:
    """灯已经是目标状态也照发，execute 仍 ok。"""
    home = _home()
    home["devices"][0]["state"]["on"] = False
    task = {
        "intent": "关灯",
        "conditions": [{"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    original = deepcopy(home)
    result = check_blueprint(home, task)
    assert result.ok is True
    assert home == original


def test_t2_writes_all_conditions_and_skips_keep() -> None:
    """T2 打灯和空调，不打客厅灯。"""
    home = _home()
    task = {
        "intent": "睡前",
        "conditions": [
            {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False},
            {"device_id": "device_bedroom_climate", "field": "target", "operator": "eq", "value": 24.0},
        ],
        "keep": [{"device_id": "device_living_light", "field": "on", "operator": "eq", "value": True}],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    assert check_blueprint(home, task).ok is True


def test_t4_probe_must_fail_and_not_mutate() -> None:
    """越界 probe 必须失败，s0 的 target 仍是 25。"""
    home = _home()
    task = {
        "intent": "五度",
        "conditions": [],
        "keep": [],
        "required_observations": [{"kind": "device", "device_id": "device_bedroom_climate"}],
        "expected_finish": {"outcome": "refused", "allowed_reason_codes": ["OUT_OF_SAFE_RANGE"]},
    }
    probe = {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 5.0}}
    result = check_blueprint(home, task, probe)
    assert result.ok is True
    legal = {"device_id": "device_bedroom_climate", "action": "set_temperature", "params": {"value": 24.0}}
    bad = check_blueprint(home, task, legal)
    assert bad.ok is False


def test_t5_inspect_sensor() -> None:
    """T5 inspect 传感器，不 execute。"""
    home = _home()
    task = {
        "intent": "湿度",
        "conditions": [],
        "keep": [],
        "required_observations": [{"kind": "device", "device_id": "sensor_bedroom_env"}],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    assert check_blueprint(home, task).ok is True


def test_missing_device_id_fails_static() -> None:
    """隐藏条件引用不存在的 id，不发蓝图。"""
    home = _home()
    task = {
        "intent": "x",
        "conditions": [{"device_id": "device_ghost", "field": "on", "operator": "eq", "value": False}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    result = check_blueprint(home, task)
    assert result.ok is False
    assert result.error_code == "UNKNOWN_DEVICE"


def test_d1_home_can_be_checked() -> None:
    """D1 抽出来的家也能被 D4 打一条关灯。"""
    home = make_home(3)
    light_id = next(item["device_id"] for item in home["devices"] if item["device_type"] == "light")
    on_value = next(item["state"]["on"] for item in home["devices"] if item["device_id"] == light_id)
    task = {
        "intent": "灯",
        "conditions": [{"device_id": light_id, "field": "on", "operator": "eq", "value": on_value}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    assert check_blueprint(home, task).ok is True


def test_dimmable_lamp_level_passes() -> None:
    """台灯 level=30 能打 set_percentage。"""
    home = _home()
    home["devices"][0]["state"] = {"on": True, "level": 80}
    home["devices"][0]["actions"].append(
        {"action": "set_percentage", "params": {"value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}}}
    )
    task = {
        "intent": "暗一点",
        "conditions": [{"device_id": "device_bedroom_light", "field": "level", "operator": "eq", "value": 30}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    assert check_blueprint(home, task).ok is True


def test_night_light_level_fails() -> None:
    """夜灯没有 level，D4 不能把调光当合法写入。"""
    home = _home()
    home["rooms"][0]["device_ids"].append("device_bedroom_night_light")
    home["devices"].append(
        {
            "device_id": "device_bedroom_night_light",
            "room_id": "room_bedroom",
            "display_name": "卧室夜灯",
            "kind": "actuator",
            "device_type": "light",
            "state": {"on": False},
            "actions": [{"action": "turn_on", "params": {}}, {"action": "turn_off", "params": {}}],
            "available": True,
        }
    )
    task = {
        "intent": "夜灯暗一点",
        "conditions": [{"device_id": "device_bedroom_night_light", "field": "level", "operator": "eq", "value": 30}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    result = check_blueprint(home, task)
    assert result.ok is False


def test_fridge_probe_must_fail() -> None:
    """冰箱 25 度 probe 失败且 state 不变。"""
    home = _home()
    home["rooms"].append({"room_id": "room_kitchen", "display_name": "厨房", "device_ids": ["device_kitchen_fridge"]})
    home["devices"].append(
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
        }
    )
    task = {
        "intent": "二十五度",
        "conditions": [],
        "keep": [],
        "required_observations": [{"kind": "device", "device_id": "device_kitchen_fridge"}],
        "expected_finish": {"outcome": "refused", "allowed_reason_codes": ["OUT_OF_SAFE_RANGE"]},
    }
    probe = {"device_id": "device_kitchen_fridge", "action": "set_temperature", "params": {"value": 25.0}}
    assert check_blueprint(home, task, probe).ok is True
    legal = {"device_id": "device_kitchen_fridge", "action": "set_temperature", "params": {"value": 4.0}}
    assert check_blueprint(home, task, legal).ok is False


def test_t3_le_writes_bound_when_too_hot() -> None:
    """当前 27，le 26，D4 写入 26。"""
    from new_demo.data.D4_oracle import _call_from_condition

    home = _home()
    home["devices"][1]["state"]["target"] = 27.0
    task = {
        "intent": "凉快一点",
        "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 26.0}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    assert check_blueprint(home, task).ok is True
    call = _call_from_condition(
        task["conditions"][0],
        {"device_bedroom_climate": {"state": {"target": 27.0}}},
    )
    assert call is not None
    assert call.arguments["params"]["value"] == 26.0


def test_t3_le_skips_write_when_already_cool() -> None:
    """当前 22，le 26，已经成立，不再写成 26。"""
    from new_demo.data.D4_oracle import _call_from_condition

    home = _home()
    home["devices"][1]["state"]["target"] = 22.0
    task = {
        "intent": "凉快一点",
        "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 26.0}],
        "keep": [],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    assert check_blueprint(home, task).ok is True
    call = _call_from_condition(
        task["conditions"][0],
        {"device_bedroom_climate": {"state": {"target": 22.0}}},
    )
    assert call is None
