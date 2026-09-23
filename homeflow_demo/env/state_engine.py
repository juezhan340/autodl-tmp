"""维护设备状态并执行已经通过 schema 校验的动作。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import Action


class StateEngine:
    """对 HomeEnv 中的设备状态提供确定性的读写操作。"""

    def __init__(self, devices: list[dict[str, Any]]) -> None:
        """复制并标准化场景中的设备状态。"""
        self._devices = self._normalize_devices(devices)

    @staticmethod
    def _normalize_devices(devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """校验设备结构并转换为 device_id 索引。"""
        normalized: dict[str, dict[str, Any]] = {}
        for raw_device in devices:
            device_id = raw_device.get("id")
            device_type = raw_device.get("type")
            state = raw_device.get("state")
            if not isinstance(device_id, str) or not device_id:
                raise ValueError("device.id must be a non-empty string")
            if device_id in normalized:
                raise ValueError(f"duplicate device id: {device_id}")
            if not isinstance(device_type, str) or not device_type:
                raise ValueError(f"device.type is invalid for {device_id}")
            if not isinstance(state, dict):
                raise ValueError(f"device.state must be an object for {device_id}")
            normalized[device_id] = {
                "id": device_id,
                "type": device_type,
                "room": raw_device.get("room", "unknown"),
                "state": deepcopy(state),
            }
        return normalized

    @property
    def devices(self) -> dict[str, dict[str, Any]]:
        """返回当前设备状态的深拷贝，防止调用方绕过状态转移。"""
        return deepcopy(self._devices)

    def query(self, device_id: str, fields: list[str]) -> dict[str, Any]:
        """读取指定设备的字段；空字段列表表示读取全部公开状态。"""
        device = self._devices[device_id]
        state = device["state"]
        selected = fields or sorted(state)
        return {
            "device_id": device_id,
            "type": device["type"],
            "room": device["room"],
            "state": {field: deepcopy(state[field]) for field in selected if field in state},
        }

    def control(self, action: Action) -> dict[str, Any]:
        """执行一次已经通过参数校验的控制动作并返回状态差异。"""
        device_id = str(action.arguments["device_id"])
        command = str(action.arguments["command"])
        value = deepcopy(action.arguments["value"])
        device = self._devices[device_id]
        field = self._command_to_field(command)
        previous = deepcopy(device["state"].get(field))
        device["state"][field] = value
        changed = previous != value
        return {
            "device_id": device_id,
            "command": command,
            "changed": changed,
            "state_diff": {field: {"from": previous, "to": deepcopy(value)}},
            "current_state": deepcopy(device["state"]),
        }

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """返回可用于恢复的设备状态快照。"""
        return deepcopy(self._devices)

    def restore(self, snapshot: dict[str, dict[str, Any]]) -> None:
        """恢复设备状态快照，并校验快照结构与当前设备一致。"""
        if set(snapshot) != set(self._devices):
            raise ValueError("snapshot device ids do not match current devices")
        self._devices = deepcopy(snapshot)

    @staticmethod
    def _command_to_field(command: str) -> str:
        """把控制命令映射到设备状态字段。"""
        return {
            "set_power": "power",
            "set_brightness": "brightness",
            "set_color_temp": "color_temp",
            "set_temperature": "temperature",
            "set_mode": "mode",
            "set_locked": "locked",
        }[command]

