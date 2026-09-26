"""校验 HomeFlow V1.2 场景中的房间、设备、动作和隐藏任务引用。"""

from __future__ import annotations

import math
from typing import Any

from .models import Scenario


DEVICE_KINDS = {"sensor", "actuator"}
DEVICE_TYPES = {
    "temperature_sensor",
    "humidity_sensor",
    "environment_sensor",
    "climate",
    "light",
    "switch",
    "fan",
}
PARAMETER_TYPES = {"boolean", "integer", "number", "string"}
OPERATORS = {"eq", "ne", "gt", "ge", "lt", "le", "in"}
SUPPORTED_ACTIONS = {"turn_on", "turn_off", "toggle", "set_mode", "set_temperature", "set_percentage"}
TASK_CATEGORIES = {
    "single_control",
    "multi_control",
    "vague_intent",
    "dangerous_refusal",
    "environment_query",
}
FINISH_OUTCOMES = {"completed", "answered", "refused"}


class SchemaValidationError(ValueError):
    """表示场景在进入 B 和 C 之前未通过静态校验。"""


def validate_scenario_dict(data: dict[str, Any]) -> list[str]:
    """返回场景的全部结构错误，空列表表示通过。"""
    if not isinstance(data, dict):
        return ["scenario must be an object"]
    errors: list[str] = []
    _require_non_empty_string(data, "scenario_id", "scenario", errors)
    home = data.get("home")
    task = data.get("task")
    config = data.get("episode_config", {})
    if not isinstance(home, dict):
        errors.append("home must be an object")
        home = {}
    if not isinstance(task, dict):
        errors.append("task must be an object")
        task = {}
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
        metadata = {}
    room_map = _validate_rooms(home.get("rooms"), errors)
    device_map = _validate_devices(home.get("devices"), room_map, errors)
    _validate_room_membership(room_map, device_map, errors)
    _validate_sensor_sources(room_map, device_map, errors)
    feasible_value = metadata.get("feasible", True)
    if not isinstance(feasible_value, bool):
        errors.append("metadata.feasible must be boolean")
    _validate_task(task, device_map, feasible_value if isinstance(feasible_value, bool) else True, errors)
    _validate_episode_config(config, errors)
    seed = data.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        errors.append("seed must be an integer or null")
    return errors


def ensure_valid_scenario(data: dict[str, Any] | Scenario) -> Scenario:
    """校验场景并返回不可变 Scenario。"""
    if isinstance(data, Scenario):
        errors = validate_scenario_dict(data.to_dict())
        if errors:
            raise SchemaValidationError("; ".join(errors))
        return data
    errors = validate_scenario_dict(data)
    if errors:
        raise SchemaValidationError("; ".join(errors))
    return Scenario.from_dict(data)


def _validate_rooms(raw_rooms: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    """校验房间数组并建立 room_id 索引。"""
    if not isinstance(raw_rooms, list) or not raw_rooms:
        errors.append("home.rooms must be a non-empty list")
        return {}
    rooms: dict[str, dict[str, Any]] = {}
    for index, room in enumerate(raw_rooms):
        path = f"home.rooms[{index}]"
        if not isinstance(room, dict):
            errors.append(f"{path} must be an object")
            continue
        room_id = room.get("room_id")
        _require_non_empty_string(room, "room_id", path, errors)
        _require_non_empty_string(room, "display_name", path, errors)
        if isinstance(room_id, str) and room_id:
            if room_id in rooms:
                errors.append(f"duplicate room_id: {room_id}")
            rooms[room_id] = room
        device_ids = room.get("device_ids", [])
        if not isinstance(device_ids, list) or not all(isinstance(item, str) for item in device_ids):
            errors.append(f"{path}.device_ids must be string[]")
        elif len(device_ids) != len(set(device_ids)):
            errors.append(f"{path}.device_ids contains duplicates")
    return rooms


def _validate_devices(
    raw_devices: Any,
    rooms: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    """校验设备数组、状态和动作 schema 并建立索引。"""
    if not isinstance(raw_devices, list) or not raw_devices:
        errors.append("home.devices must be a non-empty list")
        return {}
    devices: dict[str, dict[str, Any]] = {}
    for index, device in enumerate(raw_devices):
        path = f"home.devices[{index}]"
        if not isinstance(device, dict):
            errors.append(f"{path} must be an object")
            continue
        for name in ("device_id", "room_id", "display_name", "kind", "device_type"):
            _require_non_empty_string(device, name, path, errors)
        device_id = device.get("device_id")
        if isinstance(device_id, str) and device_id:
            if device_id in devices:
                errors.append(f"duplicate device_id: {device_id}")
            devices[device_id] = device
        room_id = device.get("room_id")
        if not isinstance(room_id, str) or room_id not in rooms:
            errors.append(f"{path}.room_id does not exist: {device.get('room_id')}")
        kind = device.get("kind")
        device_type = device.get("device_type")
        if not isinstance(kind, str) or kind not in DEVICE_KINDS:
            errors.append(f"{path}.kind must be sensor or actuator")
        if not isinstance(device_type, str) or device_type not in DEVICE_TYPES:
            errors.append(f"{path}.device_type is unsupported: {device.get('device_type')}")
        _validate_device_kind(device, path, errors)
        if not isinstance(device.get("state"), dict) or not device.get("state"):
            errors.append(f"{path}.state must be a non-empty object")
        else:
            _validate_device_state(device, path, errors)
        if not isinstance(device.get("available", True), bool):
            errors.append(f"{path}.available must be boolean")
        actions = device.get("actions", [])
        if not isinstance(actions, list):
            errors.append(f"{path}.actions must be a list")
            actions = []
        if kind == "sensor" and actions:
            errors.append(f"{path}.actions must be empty for sensor")
        if kind == "actuator" and not actions:
            errors.append(f"{path}.actions must be non-empty for actuator")
        _validate_actions(actions, path, errors)
        if isinstance(device.get("state"), dict):
            _validate_action_state_mappings(device, actions, path, errors)
    return devices


def _validate_device_kind(device: dict[str, Any], path: str, errors: list[str]) -> None:
    """确保传感器和执行器使用相符的 device_type。"""
    sensor_types = {"temperature_sensor", "humidity_sensor", "environment_sensor"}
    device_type = device.get("device_type")
    if not isinstance(device_type, str):
        return
    if device_type in sensor_types and device.get("kind") != "sensor":
        errors.append(f"{path}.device_type requires kind=sensor")
    if device_type in {"climate", "light", "switch", "fan"} and device.get("kind") != "actuator":
        errors.append(f"{path}.device_type requires kind=actuator")


def _validate_device_state(device: dict[str, Any], path: str, errors: list[str]) -> None:
    """校验 V1.2 常用传感器和执行设备状态字段及值域。"""
    state = device["state"]
    device_type = device.get("device_type")
    if not isinstance(device_type, str):
        return
    expected_fields = {
        "temperature_sensor": {"temperature"},
        "humidity_sensor": {"humidity"},
        "environment_sensor": {"temperature", "humidity"},
        "climate": {"on", "mode", "target"},
        "light": {"on"},
        "switch": {"on"},
        "fan": {"on", "level"},
    }.get(device_type)
    if expected_fields is not None and not set(state).issubset(expected_fields):
        errors.append(f"{path}.state contains fields unsupported by {device_type}")
    if device_type == "temperature_sensor" and "temperature" not in state:
        errors.append(f"{path}.state.temperature is required")
    if device_type == "humidity_sensor" and "humidity" not in state:
        errors.append(f"{path}.state.humidity is required")
    if device_type == "environment_sensor" and not {"temperature", "humidity"}.issubset(state):
        errors.append(f"{path}.state must contain temperature and humidity")
    for field, value in state.items():
        if field == "temperature" and not (-50 <= value <= 80 if _is_number(value) else False):
            errors.append(f"{path}.state.temperature must be between -50 and 80")
        elif field == "humidity" and not (0 <= value <= 100 if _is_number(value) else False):
            errors.append(f"{path}.state.humidity must be between 0 and 100")
        elif field == "on" and not isinstance(value, bool):
            errors.append(f"{path}.state.on must be boolean")
        elif field == "mode" and (
            not isinstance(value, str) or value not in {"off", "cool", "heat", "auto"}
        ):
            errors.append(f"{path}.state.mode is invalid")
        elif field == "target" and not (7 <= value <= 32 if _is_number(value) else False):
            errors.append(f"{path}.state.target must be between 7 and 32")
        elif field == "level" and not (0 <= value <= 100 if _is_number(value) else False):
            errors.append(f"{path}.state.level must be between 0 and 100")


def _validate_actions(actions: list[Any], device_path: str, errors: list[str]) -> None:
    """校验一个设备公开动作的参数结构和重复名称。"""
    names: set[str] = set()
    for index, action in enumerate(actions):
        path = f"{device_path}.actions[{index}]"
        if not isinstance(action, dict):
            errors.append(f"{path} must be an object")
            continue
        name = action.get("action")
        if not isinstance(name, str) or not name:
            errors.append(f"{path}.action must be a non-empty string")
        elif name not in SUPPORTED_ACTIONS:
            errors.append(f"{path}.action is unsupported: {name}")
        elif name in names:
            errors.append(f"{device_path}.actions contains duplicate action: {name}")
        else:
            names.add(name)
        params = action.get("params", {})
        if not isinstance(params, dict):
            errors.append(f"{path}.params must be an object")
            continue
        for param_name, spec in params.items():
            _validate_parameter_schema(param_name, spec, path, errors)
        _validate_action_signature(name, params, path, errors)


def _validate_action_signature(
    action_name: Any,
    params: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    """确保规范动作使用执行器能够安全读取的固定参数签名。"""
    expected_params = {
        "turn_on": set(),
        "turn_off": set(),
        "toggle": set(),
        "set_mode": {"mode"},
        "set_temperature": {"value"},
        "set_percentage": {"value"},
    }
    if not isinstance(action_name, str) or action_name not in expected_params:
        return
    expected = expected_params[action_name]
    if set(params) != expected:
        errors.append(f"{path}.params must be exactly {sorted(expected)} for {action_name}")
        return
    if action_name == "set_mode":
        spec = params.get("mode", {})
        if not isinstance(spec, dict):
            return
        if spec.get("type") != "string" or not isinstance(spec.get("enum"), list):
            errors.append(f"{path}.params.mode must be a string enum")
        elif not spec["enum"] or not all(
            isinstance(item, str) and item in {"off", "cool", "heat", "auto"}
            for item in spec["enum"]
        ):
            errors.append(f"{path}.params.mode enum contains unsupported mode")
    if action_name == "set_temperature":
        spec = params.get("value", {})
        if not isinstance(spec, dict):
            return
        if spec.get("type") != "number" or not all(
            _is_number(spec.get(name)) for name in ("minimum", "maximum", "step")
        ):
            errors.append(f"{path}.params.value must define number minimum/maximum/step")
        elif spec["minimum"] < 7 or spec["maximum"] > 32:
            errors.append(f"{path}.params.value range must stay within [7, 32]")
    if action_name == "set_percentage":
        spec = params.get("value", {})
        if not isinstance(spec, dict):
            return
        if spec.get("type") not in {"integer", "number"} or not all(
            _is_number(spec.get(name)) for name in ("minimum", "maximum", "step")
        ):
            errors.append(f"{path}.params.value must define numeric minimum/maximum/step")
        elif spec["minimum"] < 0 or spec["maximum"] > 100:
            errors.append(f"{path}.params.value range must stay within [0, 100]")


def _validate_action_state_mappings(
    device: dict[str, Any],
    actions: list[Any],
    path: str,
    errors: list[str],
) -> None:
    """确保每个公开动作都能映射到设备已有状态字段。"""
    state_fields = set(device.get("state", {}))
    action_fields = {
        "turn_on": "on",
        "turn_off": "on",
        "toggle": "on",
        "set_mode": "mode",
        "set_temperature": "target",
        "set_percentage": "level",
    }
    if not isinstance(actions, list):
        return
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = action.get("action")
        if not isinstance(name, str):
            continue
        field = action_fields.get(name)
        if field and field not in state_fields:
            errors.append(f"{path}.actions action {name} requires state field {field}")


def _validate_parameter_schema(name: Any, spec: Any, path: str, errors: list[str]) -> None:
    """校验一个动作参数的类型、范围、步长和枚举。"""
    if not isinstance(name, str) or not name:
        errors.append(f"{path}.params key must be a non-empty string")
        return
    if not isinstance(spec, dict):
        errors.append(f"{path}.params.{name} must be an object")
        return
    parameter_type = spec.get("type")
    if not isinstance(parameter_type, str) or parameter_type not in PARAMETER_TYPES:
        errors.append(f"{path}.params.{name}.type is unsupported")
    if "required" in spec and not isinstance(spec["required"], bool):
        errors.append(f"{path}.params.{name}.required must be boolean")
    minimum = spec.get("minimum")
    maximum = spec.get("maximum")
    if minimum is not None and not _is_number(minimum):
        errors.append(f"{path}.params.{name}.minimum must be numeric")
    if maximum is not None and not _is_number(maximum):
        errors.append(f"{path}.params.{name}.maximum must be numeric")
    if _is_number(minimum) and _is_number(maximum) and minimum > maximum:
        errors.append(f"{path}.params.{name} minimum exceeds maximum")
    step = spec.get("step")
    if step is not None and (not _is_number(step) or step <= 0):
        errors.append(f"{path}.params.{name}.step must be positive")
    if "enum" in spec and (not isinstance(spec["enum"], list) or not spec["enum"]):
        errors.append(f"{path}.params.{name}.enum must be a non-empty list")


def _validate_room_membership(
    rooms: dict[str, dict[str, Any]],
    devices: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """确认 Room.device_ids 与 Device.room_id 双向一致。"""
    indexed_membership: dict[str, str] = {}
    for room_id, room in rooms.items():
        device_ids = room.get("device_ids", [])
        if not isinstance(device_ids, list):
            continue
        for device_id in device_ids:
            if not isinstance(device_id, str):
                continue
            if device_id not in devices:
                errors.append(f"room {room_id} references unknown device: {device_id}")
            elif devices[device_id].get("room_id") != room_id:
                errors.append(f"room {room_id} contains device assigned to another room: {device_id}")
            if device_id in indexed_membership:
                errors.append(f"device appears in multiple rooms: {device_id}")
            indexed_membership[device_id] = room_id
    for device_id, device in devices.items():
        if indexed_membership.get(device_id) != device.get("room_id"):
            errors.append(f"device is missing from its room device_ids: {device_id}")


def _validate_sensor_sources(
    rooms: dict[str, dict[str, Any]],
    devices: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """限制每个房间最多一个温度源和一个湿度源，避免摘要真值冲突。"""
    for room_id, room in rooms.items():
        temperature_sources = 0
        humidity_sources = 0
        device_ids = room.get("device_ids", [])
        if not isinstance(device_ids, list):
            continue
        for device_id in device_ids:
            if not isinstance(device_id, str):
                continue
            state = devices.get(device_id, {}).get("state", {})
            temperature_sources += int("temperature" in state)
            humidity_sources += int("humidity" in state)
        if temperature_sources > 1:
            errors.append(f"room {room_id} has multiple temperature sources")
        if humidity_sources > 1:
            errors.append(f"room {room_id} has multiple humidity sources")


def _validate_task(
    task: dict[str, Any],
    devices: dict[str, dict[str, Any]],
    feasible: bool,
    errors: list[str],
) -> None:
    """校验用户请求、V2 任务类别和 conditions/keep 的设备字段引用。"""
    _require_non_empty_string(task, "user_request", "task", errors)
    category = task.get("category")
    if category is not None and (not isinstance(category, str) or category not in TASK_CATEGORIES):
        errors.append(f"task.category is unsupported: {category}")
    blueprint_id = task.get("blueprint_id")
    if blueprint_id is not None and (not isinstance(blueprint_id, str) or not blueprint_id):
        errors.append("task.blueprint_id must be a non-empty string or null")
    conditions = task.get("conditions", [])
    keep = task.get("keep", [])
    if not isinstance(conditions, list):
        errors.append("task.conditions must be a list")
        conditions = []
    expected_finish = task.get("expected_finish", {})
    if not isinstance(expected_finish, dict):
        errors.append("task.expected_finish must be an object")
        expected_finish = {}
    expected_outcome = expected_finish.get("outcome")
    if expected_outcome is not None and expected_outcome not in FINISH_OUTCOMES:
        errors.append(f"task.expected_finish.outcome is unsupported: {expected_outcome}")
    if feasible and not conditions and expected_outcome not in {"answered", "refused"}:
        errors.append("task.conditions must be non-empty for feasible scenarios")
    if not isinstance(keep, list):
        errors.append("task.keep must be a list")
        keep = []
    for group_name, items in (("conditions", conditions), ("keep", keep)):
        for index, item in enumerate(items):
            _validate_condition(item, f"task.{group_name}[{index}]", devices, errors)
    required_observations = task.get("required_observations", [])
    if not isinstance(required_observations, list):
        errors.append("task.required_observations must be a list")
    else:
        for index, item in enumerate(required_observations):
            _validate_required_observation(item, f"task.required_observations[{index}]", devices, errors)
    _validate_expected_finish(expected_finish, devices, "task.expected_finish", errors)


def _validate_required_observation(
    item: Any,
    path: str,
    devices: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """校验查询或拒绝任务要求模型先读取的观察对象。"""
    if not isinstance(item, dict):
        errors.append(f"{path} must be an object")
        return
    kind = item.get("kind")
    if kind == "room":
        if not isinstance(item.get("room_id"), str) or not item.get("room_id"):
            errors.append(f"{path}.room_id must be a non-empty string")
    elif kind == "device":
        device_id = item.get("device_id")
        if not isinstance(device_id, str) or device_id not in devices:
            errors.append(f"{path}.device_id does not exist: {device_id}")
    else:
        errors.append(f"{path}.kind must be room or device")


def _validate_expected_finish(
    expected: dict[str, Any],
    devices: dict[str, dict[str, Any]],
    path: str,
    errors: list[str],
) -> None:
    """校验结构化 finish 的隐藏答案和拒绝理由集合。"""
    facts = expected.get("facts", [])
    if not isinstance(facts, list):
        errors.append(f"{path}.facts must be a list")
    else:
        for index, fact in enumerate(facts):
            fact_path = f"{path}.facts[{index}]"
            if not isinstance(fact, dict):
                errors.append(f"{fact_path} must be an object")
                continue
            subject_id = fact.get("subject_id")
            if not isinstance(subject_id, str) or subject_id not in devices:
                errors.append(f"{fact_path}.subject_id does not exist: {subject_id}")
            if not isinstance(fact.get("field"), str) or not fact.get("field"):
                errors.append(f"{fact_path}.field must be a non-empty string")
    reason_codes = expected.get("allowed_reason_codes", [])
    if not isinstance(reason_codes, list) or not all(isinstance(item, str) and item for item in reason_codes):
        errors.append(f"{path}.allowed_reason_codes must be string[]")


def _validate_condition(
    condition: Any,
    path: str,
    devices: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """校验一个隐藏条件引用的设备、字段、操作符和值。"""
    if not isinstance(condition, dict):
        errors.append(f"{path} must be an object")
        return
    device_id = condition.get("device_id")
    field = condition.get("field")
    if not isinstance(device_id, str) or device_id not in devices:
        errors.append(f"{path}.device_id does not exist: {device_id}")
    if not isinstance(field, str) or not field:
        errors.append(f"{path}.field must be a non-empty string")
    elif isinstance(device_id, str) and device_id in devices and field not in devices[device_id].get("state", {}):
        errors.append(f"{path}.field does not exist on {device_id}: {field}")
    operator = condition.get("operator", "eq")
    if not isinstance(operator, str) or operator not in OPERATORS:
        errors.append(f"{path}.operator is unsupported")
    if "value" not in condition and "equals" not in condition:
        errors.append(f"{path} is missing value")
    elif operator == "in" and not isinstance(
        condition.get("value", condition.get("equals")), list
    ):
        errors.append(f"{path}.value must be a list for operator=in")


def _validate_episode_config(config: Any, errors: list[str]) -> None:
    """校验 C 模块使用的回合和工具调用上限。"""
    if not isinstance(config, dict):
        errors.append("episode_config must be an object")
        return
    max_turns = config.get("max_turns", 8)
    max_calls = config.get("max_tool_calls_per_turn", 4)
    if not isinstance(max_turns, int) or isinstance(max_turns, bool) or not 1 <= max_turns <= 64:
        errors.append("episode_config.max_turns must be an integer in [1, 64]")
    if not isinstance(max_calls, int) or isinstance(max_calls, bool) or not 1 <= max_calls <= 64:
        errors.append("episode_config.max_tool_calls_per_turn must be an integer in [1, 64]")


def _require_non_empty_string(
    data: dict[str, Any],
    name: str,
    path: str,
    errors: list[str],
) -> None:
    """向错误列表加入缺失或空字符串字段问题。"""
    if not isinstance(data.get(name), str) or not data.get(name):
        errors.append(f"{path}.{name} must be a non-empty string")


def _is_number(value: Any) -> bool:
    """判断值是否为排除布尔值的整数或浮点数。"""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
