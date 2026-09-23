"""提供一个用于本地 smoke test 的最小 HomeEnv 场景。"""

from typing import Any


def build_demo_scenario() -> dict[str, Any]:
    """构造一个包含灯和空调双目标的可行场景。"""
    return {
        "scenario_id": "smoke_bedroom_001",
        "seed": 1,
        "user_request": "睡前关闭卧室的灯，并把空调设置为26度。",
        "devices": [
            {
                "id": "bedroom.light",
                "type": "light",
                "room": "bedroom",
                "state": {"power": "on", "brightness": 80},
            },
            {
                "id": "bedroom.air_conditioner",
                "type": "thermostat",
                "room": "bedroom",
                "state": {"power": "on", "temperature": 24, "mode": "cool"},
            },
        ],
        "goal": {
            "predicates": [
                {"device_id": "bedroom.light", "field": "power", "equals": "off"},
                {"device_id": "bedroom.air_conditioner", "field": "temperature", "equals": 26},
            ]
        },
        "max_turns": 6,
        "max_tool_calls_per_turn": 4,
    }
