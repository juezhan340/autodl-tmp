"""提供一个覆盖房间发现、只读传感器和双设备控制的 V1.2 场景。"""

from __future__ import annotations

from typing import Any


def build_demo_scenario() -> dict[str, Any]:
    """构造卧室温湿度、灯、空调和客厅设备组成的可行场景。"""
    return {
        "scenario_id": "v1.2_demo_bedroom_001",
        "seed": 20260923,
        "home": {
            "rooms": [
                {
                    "room_id": "room_bedroom",
                    "display_name": "卧室",
                    "device_ids": ["sensor_bedroom_env", "device_bedroom_light", "device_bedroom_climate"],
                },
                {
                    "room_id": "room_living",
                    "display_name": "客厅",
                    "device_ids": ["device_living_light"],
                },
            ],
            "devices": [
                {
                    "device_id": "sensor_bedroom_env",
                    "room_id": "room_bedroom",
                    "display_name": "卧室温湿度传感器",
                    "kind": "sensor",
                    "device_type": "environment_sensor",
                    "state": {"temperature": 29.0, "humidity": 72.0},
                    "actions": [],
                },
                {
                    "device_id": "device_bedroom_light",
                    "room_id": "room_bedroom",
                    "display_name": "卧室主灯",
                    "kind": "actuator",
                    "device_type": "light",
                    "state": {"on": True},
                    "actions": _power_actions(),
                },
                {
                    "device_id": "device_bedroom_climate",
                    "room_id": "room_bedroom",
                    "display_name": "卧室空调",
                    "kind": "actuator",
                    "device_type": "climate",
                    "state": {"on": True, "mode": "cool", "target": 26.0},
                    "actions": _climate_actions(),
                },
                {
                    "device_id": "device_living_light",
                    "room_id": "room_living",
                    "display_name": "客厅主灯",
                    "kind": "actuator",
                    "device_type": "light",
                    "state": {"on": True},
                    "actions": _power_actions(),
                },
            ],
        },
        "task": {
            "user_request": "睡前关闭卧室主灯，并把卧室空调目标温度设置为24度，客厅主灯保持开启。",
            "conditions": [
                {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False},
                {"device_id": "device_bedroom_climate", "field": "target", "operator": "eq", "value": 24.0},
            ],
            "keep": [
                {"device_id": "device_living_light", "field": "on", "operator": "eq", "value": True}
            ],
        },
        "episode_config": {"max_turns": 8, "max_tool_calls_per_turn": 4},
        "metadata": {"split": "smoke", "task_kind": "multi_control", "feasible": True},
    }


def _power_actions() -> list[dict[str, Any]]:
    """返回灯、开关和风扇共用的无参数电源动作。"""
    return [
        {"action": "turn_on", "params": {}, "description": "打开设备"},
        {"action": "turn_off", "params": {}, "description": "关闭设备"},
        {"action": "toggle", "params": {}, "description": "切换设备开关状态"},
    ]


def _climate_actions() -> list[dict[str, Any]]:
    """返回空调的规范动作及参数边界。"""
    return _power_actions() + [
        {
            "action": "set_mode",
            "params": {"mode": {"type": "string", "enum": ["off", "cool", "heat", "auto"]}},
            "description": "设置空调模式",
        },
        {
            "action": "set_temperature",
            "params": {
                "value": {"type": "number", "minimum": 7.0, "maximum": 32.0, "step": 0.5}
            },
            "description": "设置目标温度",
        },
    ]
