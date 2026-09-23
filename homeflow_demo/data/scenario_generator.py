"""生成可复现的 HomeEnv 训练、验证和测评场景。"""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable


@dataclass(frozen=True)
class DeviceTemplate:
    """描述可被放入家庭场景的设备模板。"""

    device_id: str
    device_type: str
    room: str
    state: dict[str, Any]


class ScenarioGenerator:
    """按固定 seed 生成结构合法且任务标签明确的 HomeEnv 场景。"""

    def __init__(self, seed: int = 20260921) -> None:
        """初始化本地随机数生成器，不修改全局 random 状态。"""
        self.seed = seed
        self._rng = random.Random(seed)
        self._counter = 0

    def generate(self, count: int, split: str) -> list[dict[str, Any]]:
        """生成指定数量的场景，并为每条记录写入 split 元数据。"""
        if count < 0:
            raise ValueError("count must be non-negative")
        if split not in {"train", "val", "eval"}:
            raise ValueError("split must be train, val or eval")
        return [self._generate_one(split) for _ in range(count)]

    def _generate_one(self, split: str) -> dict[str, Any]:
        """根据循环任务类型生成一个场景。"""
        index = self._counter
        self._counter += 1
        task_kind = [
            "single_control",
            "multi_control",
            "query_then_control",
            "brightness_control",
            "lock_control",
            "impossible_temperature",
        ][index % 6]
        if task_kind == "single_control":
            return self._single_control(split, index)
        if task_kind == "multi_control":
            return self._multi_control(split, index)
        if task_kind == "query_then_control":
            return self._query_then_control(split, index)
        if task_kind == "brightness_control":
            return self._brightness_control(split, index)
        if task_kind == "lock_control":
            return self._lock_control(split, index)
        return self._impossible_temperature(split, index)

    def _single_control(self, split: str, index: int) -> dict[str, Any]:
        """生成一个灯或开关的单目标控制任务。"""
        templates = self._templates()
        target = templates[0 if index % 2 == 0 else 2]
        initial = deepcopy_state(target.state)
        field = "power"
        value = "off" if initial[field] == "on" else "on"
        devices = self._select_devices([target.device_id])
        return self._scenario(
            split=split,
            index=index,
            task_kind="single_control",
            devices=devices,
            goals=[(target.device_id, field, value)],
            user_request=f"请把{target.room}的{self._device_label(target)}{self._power_label(value)}。",
        )

    def _multi_control(self, split: str, index: int) -> dict[str, Any]:
        """生成一个同时控制灯和空调的双目标任务。"""
        templates = self._templates()
        light = templates[0]
        thermostat = templates[1]
        devices = self._select_devices([light.device_id, thermostat.device_id])
        return self._scenario(
            split=split,
            index=index,
            task_kind="multi_control",
            devices=devices,
            goals=[
                (light.device_id, "power", "off"),
                (thermostat.device_id, "temperature", 26),
            ],
            user_request="睡前请关闭卧室的灯，并把空调温度设置为26度。",
        )

    def _query_then_control(self, split: str, index: int) -> dict[str, Any]:
        """生成要求先查询空调状态再控制的任务。"""
        thermostat = self._templates()[1]
        devices = self._select_devices([thermostat.device_id])
        return self._scenario(
            split=split,
            index=index,
            task_kind="query_then_control",
            devices=devices,
            goals=[(thermostat.device_id, "temperature", 26)],
            user_request="请先查看卧室空调的状态，如果温度不是26度，就调整到26度。",
            requires_query=True,
        )

    def _brightness_control(self, split: str, index: int) -> dict[str, Any]:
        """生成一个灯光亮度控制任务。"""
        light = self._templates()[0]
        devices = self._select_devices([light.device_id])
        return self._scenario(
            split=split,
            index=index,
            task_kind="brightness_control",
            devices=devices,
            goals=[(light.device_id, "brightness", 80)],
            user_request="把卧室灯的亮度调到80。",
        )

    def _lock_control(self, split: str, index: int) -> dict[str, Any]:
        """生成一个门锁控制任务。"""
        lock = self._templates()[3]
        devices = self._select_devices([lock.device_id])
        return self._scenario(
            split=split,
            index=index,
            task_kind="lock_control",
            devices=devices,
            goals=[(lock.device_id, "locked", True)],
            user_request="请锁上前门。",
        )

    def _impossible_temperature(self, split: str, index: int) -> dict[str, Any]:
        """生成一个目标超出设备允许范围的不可行任务。"""
        thermostat = self._templates()[1]
        devices = self._select_devices([thermostat.device_id])
        return self._scenario(
            split=split,
            index=index,
            task_kind="impossible_temperature",
            devices=devices,
            goals=[(thermostat.device_id, "temperature", 31)],
            user_request="请把卧室空调温度设置为31度。",
            feasible=False,
        )

    def _scenario(
        self,
        split: str,
        index: int,
        task_kind: str,
        devices: list[dict[str, Any]],
        goals: list[tuple[str, str, Any]],
        user_request: str,
        *,
        requires_query: bool = False,
        feasible: bool = True,
    ) -> dict[str, Any]:
        """组装场景字典并写入数据划分和任务组合标识。"""
        scenario_id = f"v1_{split}_{index:05d}"
        device_ids = sorted(device["id"] for device in devices)
        goal_ids = [f"{device_id}.{field}" for device_id, field, _ in goals]
        return {
            "scenario_id": scenario_id,
            "seed": self.seed + index,
            "user_request": user_request,
            "devices": devices,
            "goal": {
                "predicates": [
                    {"device_id": device_id, "field": field, "equals": value}
                    for device_id, field, value in goals
                ]
            },
            "max_turns": max(4, len(goals) + (2 if requires_query else 1)),
            "max_tool_calls_per_turn": 4,
            "metadata": {
                "split": split,
                "task_kind": task_kind,
                "feasible": feasible,
                "requires_query": requires_query,
                "scenario_template_id": task_kind,
                "device_combination_id": "+".join(device_ids),
                "goal_composition_id": "+".join(sorted(goal_ids)),
                "paraphrase_group_id": f"{split}_{task_kind}_{index % 3}",
            },
        }

    def _select_devices(self, required_ids: list[str]) -> list[dict[str, Any]]:
        """选择包含目标设备的 4～8 个设备，并保持结果可复现。"""
        templates = self._templates()
        required = [item for item in templates if item.device_id in required_ids]
        optional = [item for item in templates if item.device_id not in required_ids]
        self._rng.shuffle(optional)
        count = self._rng.randint(max(4, len(required)), len(templates))
        selected = required + optional[: count - len(required)]
        return [
            {
                "id": item.device_id,
                "type": item.device_type,
                "room": item.room,
                "state": deepcopy_state(item.state),
            }
            for item in selected
        ]

    @staticmethod
    def _templates() -> list[DeviceTemplate]:
        """返回固定设备模板，避免生成逻辑依赖外部配置。"""
        return [
            DeviceTemplate("bedroom.light", "light", "卧室", {"power": "on", "brightness": 40, "color_temp": 4000}),
            DeviceTemplate("bedroom.air_conditioner", "thermostat", "卧室", {"power": "on", "temperature": 24, "mode": "cool"}),
            DeviceTemplate("kitchen.coffee_switch", "switch", "厨房", {"power": "off"}),
            DeviceTemplate("front_door.lock", "lock", "前门", {"locked": False}),
            DeviceTemplate("living_room.light", "light", "客厅", {"power": "on", "brightness": 60, "color_temp": 3500}),
            DeviceTemplate("living_room.air_conditioner", "thermostat", "客厅", {"power": "on", "temperature": 25, "mode": "cool"}),
            DeviceTemplate("study.light", "light", "书房", {"power": "off", "brightness": 20, "color_temp": 5000}),
            DeviceTemplate("garage.switch", "switch", "车库", {"power": "off"}),
        ]

    @staticmethod
    def _device_label(template: DeviceTemplate) -> str:
        """返回面向用户的设备名称。"""
        return {"light": "灯", "thermostat": "空调", "switch": "开关", "lock": "门锁"}[template.device_type]

    @staticmethod
    def _power_label(value: str) -> str:
        """返回中文电源动作描述。"""
        return "打开" if value == "on" else "关闭"


def deepcopy_state(state: dict[str, Any]) -> dict[str, Any]:
    """复制设备状态，避免场景之间共享可变字典。"""
    return deepcopy(state)


def iter_device_combinations(devices: Iterable[DeviceTemplate], size: int) -> Iterable[tuple[str, ...]]:
    """返回指定设备规模的组合，用于数据划分测试。"""
    return combinations((device.device_id for device in devices), size)
