"""生成覆盖 V1.2 八类任务的确定性 HomeFlow Scenario。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeflow_demo.env.schema import ensure_valid_scenario


TASK_KINDS = (
    "single_control",
    "multi_control",
    "query_then_control",
    "temperature_threshold",
    "humidity_threshold",
    "correct_no_op",
    "sensor_readonly",
    "missing_device",
)


class ScenarioGenerator:
    """按固定 seed 生成房间、设备、任务和隐藏真值完整的 V1.2 场景。"""

    def __init__(self, seed: int = 20260924) -> None:
        """创建独立随机数生成器并从零开始编号。"""
        self.seed = seed
        self._counter = 0

    def generate(self, count: int, split: str) -> list[dict[str, Any]]:
        """生成指定 split 的场景，并逐条执行 schema 校验。"""
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("count must be a non-negative integer")
        if split not in {"train", "val", "eval"}:
            raise ValueError("split must be train, val or eval")
        scenarios = [self._generate_one(split) for _ in range(count)]
        for scenario in scenarios:
            ensure_valid_scenario(scenario)
        return scenarios

    def _generate_one(self, split: str) -> dict[str, Any]:
        """按循环任务类型生成一条包含完整家庭快照的场景。"""
        index = self._counter
        self._counter += 1
        task_kind = TASK_KINDS[index % len(TASK_KINDS)]
        home = self._build_home(index)
        task, metadata = self._build_task(task_kind, home, index)
        return {
            "scenario_id": f"v1.2_{split}_{index:05d}",
            "seed": self.seed + index,
            "home": home,
            "task": task,
            "episode_config": {"max_turns": 10, "max_tool_calls_per_turn": 4},
            "metadata": {
                "split": split,
                "task_kind": task_kind,
                "scenario_template_id": task_kind,
                "generator_version": "v1.2",
                **metadata,
            },
        }

    def _build_home(self, index: int) -> dict[str, Any]:
        """构造四个有设备房间和一个空书房，并改变少量初始状态。"""
        cycle = index // len(TASK_KINDS)
        phase = index + self.seed
        bedroom_temperature = 30.0 if cycle % 2 == 0 else 25.0
        bedroom_humidity = float(55 + phase % 9)
        bathroom_humidity = 58.0 if cycle % 2 == 0 else 72.0
        bedroom_light_on = bool(phase % 2)
        climate_target = float(25 + phase % 2)
        devices = [
            _device(
                "sensor_bedroom_env",
                "room_bedroom",
                "卧室温湿度传感器",
                "sensor",
                "environment_sensor",
                {"temperature": bedroom_temperature, "humidity": bedroom_humidity},
                [],
            ),
            _device(
                "device_bedroom_light",
                "room_bedroom",
                "卧室主灯",
                "actuator",
                "light",
                {"on": bedroom_light_on},
                _power_actions(),
            ),
            _device(
                "device_bedroom_climate",
                "room_bedroom",
                "卧室空调",
                "actuator",
                "climate",
                {"on": True, "mode": "cool", "target": climate_target},
                _climate_actions(),
            ),
            _device(
                "sensor_bathroom_humidity",
                "room_bathroom",
                "卫生间湿度传感器",
                "sensor",
                "humidity_sensor",
                {"humidity": bathroom_humidity},
                [],
            ),
            _device(
                "device_bathroom_fan",
                "room_bathroom",
                "卫生间排风扇",
                "actuator",
                "fan",
                {"on": False, "level": 0},
                _fan_actions(),
            ),
            _device(
                "device_living_light",
                "room_living",
                "客厅主灯",
                "actuator",
                "light",
                {"on": True},
                _power_actions(),
            ),
            _device(
                "device_kitchen_switch",
                "room_kitchen",
                "厨房插座",
                "actuator",
                "switch",
                {"on": False},
                _power_actions(),
            ),
        ]
        room_names = {
            "room_bedroom": "卧室",
            "room_bathroom": "卫生间",
            "room_living": "客厅",
            "room_kitchen": "厨房",
            "room_study": "书房",
        }
        rooms = []
        for room_id, display_name in room_names.items():
            rooms.append(
                {
                    "room_id": room_id,
                    "display_name": display_name,
                    "device_ids": [
                        item["device_id"] for item in devices if item["room_id"] == room_id
                    ],
                }
            )
        return {"rooms": rooms, "devices": devices}

    def _build_task(
        self,
        task_kind: str,
        home: dict[str, Any],
        index: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """根据任务类型构造用户请求、隐藏条件和任务元数据。"""
        states = {item["device_id"]: item["state"] for item in home["devices"]}
        if task_kind == "single_control":
            target = not states["device_bedroom_light"]["on"]
            return _task(
                "请把卧室主灯切换到相反的开关状态。",
                [_condition("device_bedroom_light", "on", target)],
            ), {"feasible": True}
        if task_kind == "multi_control":
            return _task(
                "睡前关闭卧室主灯，把空调目标温度设为24度，客厅主灯保持开启。",
                [
                    _condition("device_bedroom_light", "on", False),
                    _condition("device_bedroom_climate", "target", 24.0),
                ],
                [_condition("device_living_light", "on", True)],
            ), {"feasible": True}
        if task_kind == "query_then_control":
            return _task(
                "先查看卧室空调当前状态，如果目标温度不是23度，就设置为23度。",
                [_condition("device_bedroom_climate", "target", 23.0)],
            ), {"feasible": True}
        if task_kind == "temperature_threshold":
            temperature = states["sensor_bedroom_env"]["temperature"]
            target = 24.0 if temperature > 28.0 else states["device_bedroom_climate"]["target"]
            return _task(
                "查看卧室温度；高于28度时把空调目标温度设为24度，否则保持当前设置。",
                [_condition("device_bedroom_climate", "target", target)],
            ), {
                "feasible": True,
                "context_device_ids": ["sensor_bedroom_env"],
                "threshold_branch": "control" if temperature > 28.0 else "no_op",
            }
        if task_kind == "humidity_threshold":
            humidity = states["sensor_bathroom_humidity"]["humidity"]
            fan_on = humidity > 65.0
            return _task(
                "查看卫生间湿度；高于65%时打开排风扇，否则不要操作。",
                [_condition("device_bathroom_fan", "on", fan_on)],
            ), {
                "feasible": True,
                "context_device_ids": ["sensor_bathroom_humidity"],
                "threshold_branch": "control" if fan_on else "no_op",
            }
        if task_kind == "correct_no_op":
            return _task(
                "确认客厅主灯已经开启；如果已经满足就不要重复操作。",
                [_condition("device_living_light", "on", True)],
            ), {"feasible": True}
        if task_kind == "sensor_readonly":
            return _task(
                "把卧室温湿度传感器显示的温度改成21度。",
                [_condition("sensor_bedroom_env", "temperature", 21.0)],
            ), {"feasible": False, "expected_failure": "UNSUPPORTED_ACTION"}
        return _task(
            "打开书房的空气净化器；如果书房没有这台设备，应停止并说明。",
            [],
        ), {
            "feasible": False,
            "target_room_id": "room_study",
            "expected_failure": "MISSING_TARGET_DEVICE",
            "variant": index % 3,
        }


def _device(
    device_id: str,
    room_id: str,
    display_name: str,
    kind: str,
    device_type: str,
    state: dict[str, Any],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """组装一台设备并复制可变字段。"""
    return {
        "device_id": device_id,
        "room_id": room_id,
        "display_name": display_name,
        "kind": kind,
        "device_type": device_type,
        "state": deepcopy(state),
        "actions": deepcopy(actions),
        "available": True,
    }


def _condition(device_id: str, field: str, value: Any) -> dict[str, Any]:
    """组装一个等值隐藏条件。"""
    return {"device_id": device_id, "field": field, "operator": "eq", "value": value}


def _task(
    user_request: str,
    conditions: list[dict[str, Any]],
    keep: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """组装任务可见请求和隐藏 verifier 条件。"""
    return {"user_request": user_request, "conditions": conditions, "keep": keep or []}


def _power_actions() -> list[dict[str, Any]]:
    """返回通用开关动作。"""
    return [
        {"action": "turn_on", "params": {}, "description": "打开设备"},
        {"action": "turn_off", "params": {}, "description": "关闭设备"},
        {"action": "toggle", "params": {}, "description": "切换设备开关"},
    ]


def _climate_actions() -> list[dict[str, Any]]:
    """返回空调动作及可发现参数边界。"""
    return _power_actions() + [
        {
            "action": "set_mode",
            "params": {"mode": {"type": "string", "enum": ["off", "cool", "heat", "auto"]}},
            "description": "设置工作模式",
        },
        {
            "action": "set_temperature",
            "params": {
                "value": {
                    "type": "number",
                    "minimum": 7.0,
                    "maximum": 32.0,
                    "step": 0.5,
                }
            },
            "description": "设置目标温度",
        },
    ]


def _fan_actions() -> list[dict[str, Any]]:
    """返回排风扇开关和百分比动作。"""
    return _power_actions() + [
        {
            "action": "set_percentage",
            "params": {
                "value": {"type": "integer", "minimum": 0, "maximum": 100, "step": 1}
            },
            "description": "设置风量百分比",
        }
    ]
