"""对 HomeEnv 场景和动作执行结构级校验。"""

from __future__ import annotations

from typing import Any

from .models import Action, Scenario


DEVICE_TYPES = {"light", "thermostat", "switch", "lock"}
ACTION_NAMES = {"query_device", "control_device", "finish"}
DEVICE_STATE_FIELDS = {
    "light": {"power", "brightness", "color_temp"},
    "thermostat": {"power", "temperature", "mode"},
    "switch": {"power"},
    "lock": {"locked"},
}


class SchemaValidationError(ValueError):
    """表示场景或动作未通过结构校验。"""


def validate_scenario_dict(data: dict[str, Any]) -> list[str]:
    """返回场景字典中的所有结构问题，空列表表示通过。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["scenario must be an object"]
    for field_name in ("scenario_id", "user_request", "devices", "goal"):
        if field_name not in data:
            errors.append(f"missing field: {field_name}")
    if not isinstance(data.get("scenario_id"), str) or not data.get("scenario_id"):
        errors.append("scenario_id must be a non-empty string")
    if not isinstance(data.get("user_request"), str) or not data.get("user_request"):
        errors.append("user_request must be a non-empty string")
    devices = data.get("devices")
    if not isinstance(devices, list) or not devices:
        errors.append("devices must be a non-empty list")
        devices = []
    device_ids: set[str] = set()
    device_map: dict[str, dict[str, Any]] = {}
    for index, device in enumerate(devices):
        errors.extend(_validate_device(device, index, device_ids, device_map))

    goal = data.get("goal")
    predicates = goal.get("predicates") if isinstance(goal, dict) else None
    if not isinstance(predicates, list) or not predicates:
        errors.append("goal.predicates must be a non-empty list")
        predicates = []
    for index, predicate in enumerate(predicates):
        errors.extend(_validate_predicate(predicate, index, device_map))

    # 旧 V1 数据若同时带有两个字段，以 max_steps 保持旧场景行为不变。
    max_turns = data["max_steps"] if "max_steps" in data else data.get("max_turns", 6)
    if not isinstance(max_turns, int) or isinstance(max_turns, bool) or not 0 < max_turns <= 64:
        errors.append("max_turns (or legacy max_steps) must be an integer in [1, 64]")
    max_tool_calls = data.get("max_tool_calls_per_turn", 4)
    if (
        not isinstance(max_tool_calls, int)
        or isinstance(max_tool_calls, bool)
        or not 1 <= max_tool_calls <= 64
    ):
        errors.append("max_tool_calls_per_turn must be an integer in [1, 64]")
    seed = data.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        errors.append("seed must be an integer or null")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    return errors


def ensure_valid_scenario(data: dict[str, Any]) -> Scenario:
    """校验场景字典并转换成 Scenario。"""
    errors = validate_scenario_dict(data)
    if errors:
        raise SchemaValidationError("; ".join(errors))
    return Scenario.from_dict(data)


def validate_action_dict(data: dict[str, Any]) -> list[str]:
    """返回结构化动作中的格式问题。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["action must be an object"]
    if data.get("name") not in ACTION_NAMES:
        errors.append("action.name must be query_device, control_device or finish")
    if not isinstance(data.get("arguments", {}), dict):
        errors.append("action.arguments must be an object")
    return errors


def ensure_valid_action(data: dict[str, Any]) -> Action:
    """校验动作字典并转换成 Action。"""
    errors = validate_action_dict(data)
    if errors:
        raise SchemaValidationError("; ".join(errors))
    return Action.from_dict(data)


def _validate_device(
    device: Any,
    index: int,
    device_ids: set[str],
    device_map: dict[str, dict[str, Any]],
) -> list[str]:
    """校验一个设备对象并更新设备索引。"""
    errors: list[str] = []
    if not isinstance(device, dict):
        return [f"devices[{index}] must be an object"]
    device_id = device.get("id")
    device_type = device.get("type")
    state = device.get("state")
    if not isinstance(device_id, str) or not device_id:
        errors.append(f"devices[{index}].id must be a non-empty string")
    elif device_id in device_ids:
        errors.append(f"duplicate device id: {device_id}")
    else:
        device_ids.add(device_id)
        device_map[device_id] = device
    if device_type not in DEVICE_TYPES:
        errors.append(f"devices[{index}].type must be one of {sorted(DEVICE_TYPES)}")
    if not isinstance(device.get("room"), str) or not device.get("room"):
        errors.append(f"devices[{index}].room must be a non-empty string")
    if not isinstance(state, dict) or not state:
        errors.append(f"devices[{index}].state must be a non-empty object")
    elif device_type in DEVICE_STATE_FIELDS:
        unknown_fields = sorted(set(state) - DEVICE_STATE_FIELDS[device_type])
        if unknown_fields:
            errors.append(
                f"devices[{index}].state has unsupported fields for {device_type}: {unknown_fields}"
            )
        for field, value in state.items():
            if field in DEVICE_STATE_FIELDS[device_type] and not _valid_state_value(field, value):
                errors.append(f"devices[{index}].state.{field} has an invalid value: {value}")
    return errors


def _valid_state_value(field: str, value: Any) -> bool:
    """校验设备初始状态字段，保证状态机从合法值域开始。"""
    if field == "power":
        return value in {"on", "off"}
    if field == "brightness":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100
    if field == "color_temp":
        return isinstance(value, int) and not isinstance(value, bool) and 1500 <= value <= 9000
    if field == "temperature":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and 16 <= value <= 30
    if field == "mode":
        return value in {"cool", "heat", "auto", "off"}
    if field == "locked":
        return isinstance(value, bool)
    return False


def _validate_predicate(
    predicate: Any, index: int, device_map: dict[str, dict[str, Any]]
) -> list[str]:
    """校验一个目标谓词并确认设备引用存在。"""
    errors: list[str] = []
    if not isinstance(predicate, dict):
        return [f"goal.predicates[{index}] must be an object"]
    device_id = predicate.get("device_id")
    field = predicate.get("field")
    if device_id not in device_map:
        errors.append(f"goal.predicates[{index}].device_id does not exist: {device_id}")
    if not isinstance(field, str) or not field:
        errors.append(f"goal.predicates[{index}].field must be a non-empty string")
    elif device_id in device_map and field not in device_map[device_id].get("state", {}):
        errors.append(f"goal.predicates[{index}].field does not exist: {field}")
    if "equals" not in predicate:
        errors.append(f"goal.predicates[{index}] is missing equals")
    return errors
