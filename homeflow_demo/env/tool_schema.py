"""定义 V1.2 策略可见工具、统一返回外壳和参数校验规则。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import ActionSchema, ParameterSchema, ToolCall, copy_json


ENVIRONMENT_TOOL_NAMES = {"observe_home", "inspect_room", "inspect_device", "execute_action"}
RUNNER_TOOL_NAMES = {"finish"}
TOOL_NAMES = ENVIRONMENT_TOOL_NAMES | RUNNER_TOOL_NAMES
STRATEGY_ERROR_CODES = {
    "UNKNOWN_ROOM",
    "UNKNOWN_DEVICE",
    "UNSUPPORTED_ACTION",
    "BAD_REQUEST",
    "INVALID_ASSISTANT_RESPONSE",
    "TOO_MANY_TOOL_CALLS",
}
ENVIRONMENT_ERROR_CODES = {
    "DEVICE_UNAVAILABLE",
    "BACKEND_UNREACHABLE",
}


@dataclass(frozen=True)
class ValidationResult:
    """保存参数校验结论和可返回给策略的失败信息。"""

    valid: bool
    code: str | None = None
    message: str | None = None
    hint: str | None = None


def available_tools() -> list[dict[str, Any]]:
    """返回 A 可见的四个家庭工具和一个 runner 终止工具。"""
    return [
        {
            "name": "observe_home",
            "description": "查看房间目录、房间环境摘要和设备数量；不会返回设备 ID。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "inspect_room",
            "description": "查看一个房间的全部设备摘要并获取 device_id。",
            "parameters": {
                "type": "object",
                "properties": {"room_id": {"type": "string"}},
                "required": ["room_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "inspect_device",
            "description": "查看一台设备的完整公开状态和 actions 参数范围。",
            "parameters": {
                "type": "object",
                "properties": {"device_id": {"type": "string"}},
                "required": ["device_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "execute_action",
            "description": "执行设备 actions 中公开的规范动作；传感器没有可执行动作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string"},
                    "action": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["device_id", "action", "params"],
                "additionalProperties": False,
            },
        },
        {
            "name": "finish",
            "description": "结束当前 episode 并提交简短总结；它不是家庭设备写命令。",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
        },
    ]


def validate_tool_call_shape(call: ToolCall, *, include_finish: bool = False) -> ValidationResult:
    """校验工具名和固定参数容器，不解释设备动作语义。"""
    if not isinstance(call.call_id, str) or not call.call_id:
        return ValidationResult(False, "BAD_REQUEST", "call_id must be a non-empty string")
    allowed = TOOL_NAMES if include_finish else ENVIRONMENT_TOOL_NAMES
    if not isinstance(call.name, str) or call.name not in allowed:
        return ValidationResult(
            False,
            "BAD_REQUEST",
            f"unknown tool: {call.name}",
            "use one of the tools provided in the current tool schema",
        )
    if not isinstance(call.arguments, dict):
        return ValidationResult(False, "BAD_REQUEST", "arguments must be an object")
    expected: dict[str, tuple[set[str], set[str]]] = {
        "observe_home": (set(), set()),
        "inspect_room": ({"room_id"}, {"room_id"}),
        "inspect_device": ({"device_id"}, {"device_id"}),
        "execute_action": ({"device_id", "action", "params"}, {"device_id", "action", "params"}),
        "finish": (
            {"summary", "outcome", "facts", "reason_code"},
            {"summary"},
        ),
    }
    allowed_keys, required_keys = expected[call.name]
    if not all(isinstance(key, str) for key in call.arguments):
        return ValidationResult(False, "BAD_REQUEST", "argument names must be strings")
    keys = set(call.arguments)
    missing = sorted(required_keys - keys)
    extra = sorted(keys - allowed_keys)
    if missing or extra:
        return ValidationResult(
            False,
            "BAD_REQUEST",
            f"invalid arguments for {call.name}: missing={missing}, extra={extra}",
        )
    string_keys = {
        "inspect_room": ("room_id",),
        "inspect_device": ("device_id",),
        "execute_action": ("device_id", "action"),
        "finish": ("summary",),
    }.get(call.name, ())
    for key in string_keys:
        if not isinstance(call.arguments.get(key), str) or not call.arguments.get(key):
            return ValidationResult(False, "BAD_REQUEST", f"{call.name}.{key} must be a non-empty string")
    if call.name == "execute_action" and not isinstance(call.arguments.get("params"), dict):
        return ValidationResult(False, "BAD_REQUEST", "execute_action.params must be an object")
    if call.name == "finish":
        outcome = call.arguments.get("outcome")
        if outcome is not None and outcome not in {"completed", "answered", "refused"}:
            return ValidationResult(False, "BAD_REQUEST", "finish.outcome must be completed, answered or refused")
        facts = call.arguments.get("facts")
        if facts is not None and not isinstance(facts, list):
            return ValidationResult(False, "BAD_REQUEST", "finish.facts must be an array")
        reason_code = call.arguments.get("reason_code")
        if reason_code is not None and not isinstance(reason_code, str):
            return ValidationResult(False, "BAD_REQUEST", "finish.reason_code must be a string or null")
    return ValidationResult(True)


def validate_action_params(action: ActionSchema, params: dict[str, Any]) -> ValidationResult:
    """按设备公开的 ActionSchema 重复校验模型提交参数。"""
    expected = set(action.params)
    actual = set(params)
    missing = sorted(name for name, spec in action.params.items() if spec.required and name not in actual)
    extra = sorted(actual - expected)
    if missing or extra:
        return ValidationResult(
            False,
            "BAD_REQUEST",
            f"invalid params for {action.action}: missing={missing}, extra={extra}",
            "inspect_device 返回的 actions 是合法参数集合",
        )
    for name, spec in action.params.items():
        if name not in params:
            continue
        issue = _validate_parameter_value(name, params[name], spec)
        if issue:
            return issue
    return ValidationResult(True)


def success_envelope(data: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    """构造统一的成功结果外壳。"""
    return {
        "ok": True,
        "data": copy_json(data),
        "error": None,
        "meta": {"elapsed_ms": max(0.0, float(elapsed_ms)), "clock": "none"},
    }


def error_envelope(
    code: str,
    message: str,
    elapsed_ms: float,
    hint: str | None = None,
) -> dict[str, Any]:
    """构造统一的失败结果外壳。"""
    error: dict[str, Any] = {"code": code, "message": message}
    if hint:
        error["hint"] = hint
    return {
        "ok": False,
        "data": None,
        "error": error,
        "meta": {"elapsed_ms": max(0.0, float(elapsed_ms)), "clock": "none"},
    }


def policy_result_view(result: dict[str, Any]) -> dict[str, Any]:
    """移除硬件相关 elapsed_ms，避免策略从机器负载获得捷径。"""
    view = copy_json(result)
    meta = view.get("meta")
    if isinstance(meta, dict):
        meta.pop("elapsed_ms", None)
    return view


def classify_error(code: str | None) -> str:
    """把错误码稳定归为策略错误、环境错误或未决错误。"""
    if code in STRATEGY_ERROR_CODES:
        return "strategy_error"
    if code in ENVIRONMENT_ERROR_CODES:
        return "environment_failure"
    if code == "SERVICE_ERROR":
        return "unresolved"
    return "unresolved"


def _validate_parameter_value(
    name: str,
    value: Any,
    spec: ParameterSchema,
) -> ValidationResult | None:
    """校验单个参数的 Python 类型、枚举、范围和步长。"""
    type_ok = {
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
    }.get(spec.type, False)
    if not type_ok:
        return ValidationResult(False, "BAD_REQUEST", f"parameter {name} must be {spec.type}")
    if spec.enum and value not in spec.enum:
        return ValidationResult(False, "BAD_REQUEST", f"parameter {name} must be one of {list(spec.enum)}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return ValidationResult(False, "BAD_REQUEST", f"parameter {name} must be finite")
        if spec.minimum is not None and value < spec.minimum:
            return ValidationResult(False, "BAD_REQUEST", f"parameter {name} is below {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            return ValidationResult(False, "BAD_REQUEST", f"parameter {name} exceeds {spec.maximum}")
        if spec.step is not None and spec.minimum is not None:
            units = (float(value) - float(spec.minimum)) / float(spec.step)
            if abs(units - round(units)) > 1e-8:
                return ValidationResult(False, "BAD_REQUEST", f"parameter {name} does not match step {spec.step}")
    return None
