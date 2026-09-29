"""家庭状态的确定性读取、动作校验和原子写入。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .B_models import ActionSchema, Home, copy_json
from .B_tool_schema import ValidationResult, validate_action_params


class StateEngine:
    """维护 HomeEnv 运行时副本，提供四个家庭语义操作。"""

    def __init__(self, home: Home) -> None:
        """复制静态 Home，建立房间、设备和初始状态索引。"""
        self._rooms = {key: value.to_dict() for key, value in home.rooms.items()}
        self._devices = {key: value.to_dict() for key, value in home.devices.items()}

    @property
    def state(self) -> dict[str, dict[str, Any]]:
        """给 C-2 和 final_state 用，不含 actions。"""
        return {
            device_id: {
                "device_id": device_id,
                "room_id": device["room_id"],
                "display_name": device["display_name"],
                "kind": device["kind"],
                "device_type": device["device_type"],
                "state": copy_json(device["state"]),
                "available": device["available"],
            }
            for device_id, device in self._devices.items()
        }

    def observe_home(self) -> dict[str, Any]:
        """只回房间 id 和名称，不暴露设备、温湿度和台数。"""
        rooms: list[dict[str, Any]] = []
        for room_id in sorted(self._rooms):
            room = self._rooms[room_id]
            rooms.append({"room_id": room_id, "display_name": room["display_name"]})
        return {"rooms": rooms}

    def inspect_room(self, room_id: str) -> tuple[ValidationResult, dict[str, Any] | None]:
        """返回指定房间的设备轻量摘要。"""
        if room_id not in self._rooms:
            return ValidationResult(False, "UNKNOWN_ROOM", f"unknown room: {room_id}"), None
        room = self._rooms[room_id]
        devices = []
        for device_id in room["device_ids"]:
            device = self._devices[device_id]
            devices.append(
                {
                    "device_id": device_id,
                    "display_name": device["display_name"],
                    "kind": device["kind"],
                    "device_type": device["device_type"],
                    "available": device["available"],
                }
            )
        return ValidationResult(True), {
            "room": {
                "room_id": room_id,
                "display_name": room["display_name"],
                "environment": self._room_environment(room_id),
                "devices": devices,
            }
        }

    def inspect_device(self, device_id: str) -> tuple[ValidationResult, dict[str, Any] | None]:
        """返回指定设备的完整状态和动作 schema。"""
        if device_id not in self._devices:
            return ValidationResult(False, "UNKNOWN_DEVICE", f"unknown device: {device_id}"), None
        device = self._devices[device_id]
        return ValidationResult(True), {"device": copy_json(device)}

    def execute_action(
        self,
        device_id: str,
        action_name: str,
        params: dict[str, Any],
    ) -> tuple[ValidationResult, dict[str, Any] | None, dict[str, Any]]:
        """校验并原子执行一台设备公开的规范动作。"""
        if device_id not in self._devices:
            return ValidationResult(False, "UNKNOWN_DEVICE", f"unknown device: {device_id}"), None, {}
        device = self._devices[device_id]
        if not device["available"]:
            return ValidationResult(False, "DEVICE_UNAVAILABLE", f"device is unavailable: {device_id}"), None, {}
        action_map = {item["action"]: ActionSchema.from_dict(item) for item in device["actions"]}
        if action_name not in action_map:
            return (
                ValidationResult(
                    False,
                    "UNSUPPORTED_ACTION",
                    f"{device_id} does not support {action_name}",
                    "inspect_device 返回的 actions 是合法动作集合",
                ),
                None,
                {},
            )
        validation = validate_action_params(action_map[action_name], params)
        if not validation.valid:
            return validation, None, {}

        before = deepcopy(device["state"])
        candidate = deepcopy(before)
        effect = self._apply_action(candidate, action_name, params)
        if not effect.valid:
            return effect, None, {}
        device["state"] = candidate
        state_diff = self._state_diff(before, candidate)
        return ValidationResult(True), {
            "device_id": device_id,
            "action": action_name,
            "state_after": deepcopy(candidate),
            "verified": True,
            "changed": bool(state_diff),
        }, state_diff

    def _room_environment(self, room_id: str) -> dict[str, Any]:
        """从房间传感器 state 派生温度和湿度摘要。"""
        environment: dict[str, Any] = {}
        for device_id in self._rooms[room_id]["device_ids"]:
            device = self._devices[device_id]
            if device["kind"] != "sensor" or not device["available"]:
                continue
            for field in ("temperature", "humidity"):
                if field in device["state"]:
                    environment[field] = copy_json(device["state"][field])
        return environment

    @staticmethod
    def _apply_action(
        state: dict[str, Any],
        action_name: str,
        params: dict[str, Any],
    ) -> ValidationResult:
        """在候选状态上应用动作，成功后调用方才提交。"""
        if action_name in {"turn_on", "turn_off", "toggle"}:
            if not isinstance(state.get("on"), bool):
                return ValidationResult(False, "SERVICE_ERROR", "device state is missing boolean field: on")
            state["on"] = not state["on"] if action_name == "toggle" else action_name == "turn_on"
            return ValidationResult(True)
        mapping = {
            "set_mode": ("mode", "mode"),
            "set_temperature": ("target", "value"),
            "set_percentage": ("level", "value"),
        }
        if action_name not in mapping:
            return ValidationResult(False, "SERVICE_ERROR", f"no state mapping for action: {action_name}")
        field, param = mapping[action_name]
        if field not in state:
            return ValidationResult(False, "SERVICE_ERROR", f"device state is missing field: {field}")
        state[field] = copy_json(params[param])
        return ValidationResult(True)

    @staticmethod
    def _state_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """只返回实际改变的状态字段。"""
        diff: dict[str, Any] = {}
        for field in sorted(set(before) | set(after)):
            if before.get(field) != after.get(field):
                diff[field] = {"from": copy_json(before.get(field)), "to": copy_json(after.get(field))}
        return diff
