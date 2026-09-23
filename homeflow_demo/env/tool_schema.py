"""定义 HomeEnv 工具和工具参数校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .models import Action, AssistantTurn


TOOL_NAMES = {"query_device", "control_device", "finish"}


@dataclass
class ValidationResult:
    """保存动作校验是否通过以及失败原因。"""

    valid: bool
    error_code: str | None = None
    message: str | None = None


def available_tools() -> list[dict[str, Any]]:
    """返回提供给语言模型的最小工具 schema。"""
    return [
        {
            "name": "query_device",
            "description": "读取指定设备的当前状态。",
            "arguments": {"device_id": "string", "fields": "string[]"},
        },
        {
            "name": "control_device",
            "description": "修改指定设备的一个状态字段。",
            "arguments": {"device_id": "string", "command": "string", "value": "any"},
        },
        {
            "name": "finish",
            "description": "声明当前任务已经完成。",
            "arguments": {"summary": "string"},
        },
    ]


def normalize_action(action: Action | dict[str, Any] | str) -> Action:
    """把字典或 JSON 字符串统一转换为 Action。"""
    if isinstance(action, Action):
        return action
    if isinstance(action, str):
        try:
            action = json.loads(action)
        except json.JSONDecodeError as exc:
            raise ValueError("action is not valid JSON") from exc
    return Action.from_dict(action)


def normalize_assistant_turn(
    turn: AssistantTurn | Action | dict[str, Any] | str,
) -> AssistantTurn:
    """把模型输出或旧版原子动作统一转换成 AssistantTurn。"""
    if isinstance(turn, AssistantTurn):
        return turn
    if isinstance(turn, Action):
        return AssistantTurn(tool_calls=[turn])
    if isinstance(turn, str):
        try:
            parsed = json.loads(turn)
        except json.JSONDecodeError as exc:
            raise ValueError("assistant turn is not valid JSON") from exc
        return normalize_assistant_turn(parsed)
    if not isinstance(turn, dict):
        raise TypeError("assistant turn must be a dictionary, Action or JSON string")
    if "tool_calls" in turn or "text" in turn or "assistant_output" in turn:
        return AssistantTurn.from_dict(turn)
    return AssistantTurn(tool_calls=[Action.from_dict(turn)])


def validate_action(action: Action, devices: dict[str, dict[str, Any]]) -> ValidationResult:
    """根据设备类型和工具约束校验一次动作。"""
    if action.name not in TOOL_NAMES:
        return ValidationResult(False, "UNKNOWN_TOOL", f"unknown tool: {action.name}")
    if not isinstance(action.arguments, dict):
        return ValidationResult(False, "INVALID_ARGUMENTS", "arguments must be an object")

    if action.name == "finish":
        summary = action.arguments.get("summary", "")
        if not isinstance(summary, str):
            return ValidationResult(False, "INVALID_ARGUMENTS", "finish.summary must be a string")
        return ValidationResult(True)

    device_id = action.arguments.get("device_id")
    if not isinstance(device_id, str) or device_id not in devices:
        return ValidationResult(False, "UNKNOWN_DEVICE", f"unknown device: {device_id}")

    if action.name == "query_device":
        fields = action.arguments.get("fields", [])
        if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
            return ValidationResult(False, "INVALID_ARGUMENTS", "query_device.fields must be string[]")
        unknown_fields = sorted(set(fields) - set(devices[device_id].get("state", {})))
        if unknown_fields:
            return ValidationResult(False, "UNKNOWN_FIELD", f"unknown fields: {unknown_fields}")
        return ValidationResult(True)

    command = action.arguments.get("command")
    value = action.arguments.get("value")
    device_type = devices[device_id]["type"]
    allowed = _allowed_commands(device_type)
    if command not in allowed:
        return ValidationResult(False, "INVALID_COMMAND", f"{command} is invalid for {device_type}")
    if not _valid_value(command, value):
        return ValidationResult(False, "VALUE_OUT_OF_RANGE", f"invalid value for {command}: {value}")
    return ValidationResult(True)


def _allowed_commands(device_type: str) -> set[str]:
    """返回某类设备允许执行的控制命令。"""
    return {
        "light": {"set_power", "set_brightness", "set_color_temp"},
        "thermostat": {"set_power", "set_temperature", "set_mode"},
        "switch": {"set_power"},
        "lock": {"set_locked"},
    }.get(device_type, set())


def _valid_value(command: str, value: Any) -> bool:
    """校验控制命令的参数类型和数值范围。"""
    if command == "set_power":
        return value in {"on", "off"}
    if command == "set_brightness":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100
    if command == "set_color_temp":
        return isinstance(value, int) and not isinstance(value, bool) and 1500 <= value <= 9000
    if command == "set_temperature":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and 16 <= value <= 30
    if command == "set_mode":
        return value in {"cool", "heat", "auto", "off"}
    if command == "set_locked":
        return isinstance(value, bool)
    return False
