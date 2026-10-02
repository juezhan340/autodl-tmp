"""校验场景里的房间、设备、动作和隐藏任务引用。"""

from __future__ import annotations

import math
from typing import Any

from .B_models import Scenario


DEVICE_KINDS = {"sensor", "actuator"}
SENSOR_TYPES = {"temperature_sensor", "humidity_sensor", "environment_sensor"}
ACTUATOR_TYPES = {
    "climate",
    "light",
    "switch",
    "fan",
    "tv",
    "water_heater",
    "washer",
    "dishwasher",
    "oven",
    "refrigerator",
    "humidifier",
}
DEVICE_TYPES = SENSOR_TYPES | ACTUATOR_TYPES
PARAMETER_TYPES = {"boolean", "integer", "number", "string"}
OPERATORS = {"eq", "ne", "gt", "ge", "lt", "le", "in"}
SUPPORTED_ACTIONS = {"turn_on", "turn_off", "toggle", "set_mode", "set_temperature", "set_percentage"}
FINISH_OUTCOMES = {"completed", "refused"}
ACTUATOR_EXTRA_FIELDS = {"position", "current"}
ALLOWED_STATE_FIELDS = {
    "temperature_sensor": {"temperature"},
    "humidity_sensor": {"humidity"},
    "environment_sensor": {"temperature", "humidity"},
    "climate": {"on", "mode", "target"},
    "light": {"on", "level", "mode"},
    "switch": {"on"},
    "fan": {"on", "level"},
    "tv": {"on", "mode", "level"},
    "water_heater": {"on", "mode", "target"},
    "washer": {"on", "mode"},
    "dishwasher": {"on", "mode"},
    "oven": {"on", "mode", "target"},
    "refrigerator": {"on", "target"},
    "humidifier": {"on"},
}
REQUIRED_STATE_FIELDS = {
    "temperature_sensor": {"temperature"},
    "humidity_sensor": {"humidity"},
    "environment_sensor": {"temperature", "humidity"},
    "climate": {"on", "mode", "target"},
    "light": {"on"},
    "switch": {"on"},
    "fan": {"on", "level"},
    "tv": {"on", "mode", "level"},
    "water_heater": {"on", "mode", "target"},
    "washer": {"on", "mode"},
    "dishwasher": {"on", "mode"},
    "oven": {"on", "mode", "target"},
    "refrigerator": {"on", "target"},
    "humidifier": {"on"},
}


class SchemaValidationError(ValueError):
    """场景在进入 B 之前没过静态校验。"""


def validate_scenario_dict(data: dict[str, Any]) -> list[str]:
    """返回全部结构错误，空列表表示通过。"""
    if not isinstance(data, dict):
        return ["scenario must be an object"]
    errors: list[str] = []
    _require_non_empty_string(data, "scenario_id", "scenario", errors)
    _require_non_empty_string(data, "blueprint_id", "scenario", errors)
    _require_non_empty_string(data, "user_request", "scenario", errors)
    home = data.get("home")
    task = data.get("task")
    config = data.get("episode_config", {})
    if not isinstance(home, dict):
        errors.append("home must be an object")
        home = {}
    if not isinstance(task, dict):
        errors.append("task must be an object")
        task = {}
    if "user_request" in task:
        errors.append("user_request must be top-level, not inside task")
    room_map = _validate_rooms(home.get("rooms"), errors)
    device_map = _validate_devices(home.get("devices"), room_map, errors)
    _validate_room_membership(room_map, device_map, errors)
    _validate_task(task, device_map, errors)
    _validate_episode_config(config, errors)
    return errors


def ensure_valid_scenario(data: dict[str, Any] | Scenario) -> Scenario:
    """校验场景并返回不可变 Scenario。"""
    payload = data.to_dict() if isinstance(data, Scenario) else data
    errors = validate_scenario_dict(payload)
    if errors:
        raise SchemaValidationError("; ".join(errors))
    if isinstance(data, Scenario):
        return data
    return Scenario.from_dict(data)


def _validate_rooms(raw_rooms: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    """校验房间数组并建 room_id 索引。"""
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
    """校验设备数组、状态和动作 schema。"""
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
        kind = device.get("kind")
        if isinstance(kind, str) and kind not in DEVICE_KINDS:
            errors.append(f"{path}.kind must be sensor or actuator")
        device_type = device.get("device_type")
        if isinstance(device_type, str) and device_type not in DEVICE_TYPES:
            errors.append(f"{path}.device_type is unsupported: {device_type}")
        if not isinstance(device.get("state"), dict):
            errors.append(f"{path}.state must be an object")
            device["state"] = {}
        if "available" in device and not isinstance(device["available"], bool):
            errors.append(f"{path}.available must be boolean")
        room_id = device.get("room_id")
        if isinstance(room_id, str) and room_id and room_id not in rooms:
            errors.append(f"{path}.room_id does not exist: {room_id}")
        _validate_device_kind(device, path, errors)
        _validate_device_state(device, path, errors)
        actions = device.get("actions", [])
        if not isinstance(actions, list):
            errors.append(f"{path}.actions must be a list")
            actions = []
        if device.get("kind") == "sensor" and actions:
            errors.append(f"{path}.actions must be empty for sensor")
        _validate_actions(actions, path, errors)
        _validate_action_state_mappings(device, actions, path, errors)
        _validate_state_against_actions(device, path, errors)
        _validate_light_capability(device, path, errors)
    return devices


def _validate_light_capability(device: dict[str, Any], path: str, errors: list[str]) -> None:
    """主灯用 mode，台灯用 level，同一盏灯不能两套都有。"""
    if device.get("device_type") != "light":
        return
    state = device.get("state") or {}
    actions = device.get("actions") or []
    names = {item.get("action") for item in actions if isinstance(item, dict)}
    has_mode = "mode" in state or "set_mode" in names
    has_level = "level" in state or "set_percentage" in names
    if has_mode and has_level:
        errors.append(f"{path} light cannot combine set_mode/mode with set_percentage/level")


def _validate_device_kind(device: dict[str, Any], path: str, errors: list[str]) -> None:
    """传感器和执行器的 device_type 必须对得上 kind。"""
    device_type = device.get("device_type")
    if not isinstance(device_type, str):
        return
    if device_type in SENSOR_TYPES and device.get("kind") != "sensor":
        errors.append(f"{path}.device_type requires kind=sensor")
    if device_type in ACTUATOR_TYPES and device.get("kind") != "actuator":
        errors.append(f"{path}.device_type requires kind=actuator")


def _validate_device_state(device: dict[str, Any], path: str, errors: list[str]) -> None:
    """校验状态键集合和基础类型；范围以该设备 actions 为准。"""
    state = device["state"]
    device_type = device.get("device_type")
    if not isinstance(device_type, str):
        return
    allowed = ALLOWED_STATE_FIELDS.get(device_type)
    required = REQUIRED_STATE_FIELDS.get(device_type)
    extra_ok = ACTUATOR_EXTRA_FIELDS if device.get("kind") == "actuator" else set()
    if allowed is not None:
        unknown = set(state) - allowed - extra_ok
        if unknown:
            errors.append(f"{path}.state contains fields unsupported by {device_type}: {sorted(unknown)}")
    if required is not None:
        missing = required - set(state)
        if missing:
            errors.append(f"{path}.state missing required fields: {sorted(missing)}")
    for field, value in state.items():
        if field == "temperature" and not (-50 <= value <= 80 if _is_number(value) else False):
            errors.append(f"{path}.state.temperature must be between -50 and 80")
        elif field == "humidity" and not (0 <= value <= 100 if _is_number(value) else False):
            errors.append(f"{path}.state.humidity must be between 0 and 100")
        elif field == "on" and not isinstance(value, bool):
            errors.append(f"{path}.state.on must be boolean")
        elif field == "mode" and (not isinstance(value, str) or not value):
            errors.append(f"{path}.state.mode must be a non-empty string")
        elif field == "target" and not (_is_number(value) and -20 <= value <= 400):
            errors.append(f"{path}.state.target must be a number in [-20, 400]")
        elif field in {"level", "position"} and not (0 <= value <= 100 if _is_number(value) else False):
            errors.append(f"{path}.state.{field} must be between 0 and 100")
        elif field == "current" and not _is_number(value):
            errors.append(f"{path}.state.current must be numeric")


def _validate_actions(actions: list[Any], device_path: str, errors: list[str]) -> None:
    """校验公开动作的参数结构和重复名。"""
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
    """规范动作必须用固定参数签名。"""
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
        enum = spec.get("enum")
        if spec.get("type") != "string" or not isinstance(enum, list) or not enum:
            errors.append(f"{path}.params.mode must be string enum")
        elif not all(isinstance(item, str) and item for item in enum):
            errors.append(f"{path}.params.mode enum must be non-empty strings")
    if action_name == "set_temperature":
        spec = params.get("value", {})
        if not isinstance(spec, dict):
            return
        if spec.get("type") != "number" or not all(
            _is_number(spec.get(name)) for name in ("minimum", "maximum", "step")
        ):
            errors.append(f"{path}.params.value must define number minimum/maximum/step")
        elif not (-20 <= spec["minimum"] < spec["maximum"] <= 400):
            errors.append(f"{path}.params.value range must stay within [-20, 400] with min < max")
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
    """公开动作必须能映射到已有状态字段。"""
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


def _validate_state_against_actions(device: dict[str, Any], path: str, errors: list[str]) -> None:
    """mode/target/level 必须落在该设备自己的 enum 或 min/max 里。"""
    state = device.get("state") or {}
    enum = _action_enum(device, "set_mode", "mode")
    if "mode" in state and enum and state["mode"] not in enum:
        errors.append(f"{path}.state.mode is not in this device set_mode enum")
    spec = _action_param_spec(device, "set_temperature", "value")
    if spec and "target" in state and _is_number(state["target"]):
        minimum = spec.get("minimum")
        maximum = spec.get("maximum")
        if _is_number(minimum) and _is_number(maximum) and not (minimum <= state["target"] <= maximum):
            errors.append(f"{path}.state.target must be within this device set_temperature range")
    spec = _action_param_spec(device, "set_percentage", "value")
    if spec and "level" in state and _is_number(state["level"]):
        minimum = spec.get("minimum")
        maximum = spec.get("maximum")
        if _is_number(minimum) and _is_number(maximum) and not (minimum <= state["level"] <= maximum):
            errors.append(f"{path}.state.level must be within this device set_percentage range")


def _action_param_spec(device: dict[str, Any], action_name: str, param_name: str) -> dict[str, Any] | None:
    """读设备某个动作的参数约束。"""
    actions = device.get("actions")
    if not isinstance(actions, list):
        return None
    for action in actions:
        if not isinstance(action, dict) or action.get("action") != action_name:
            continue
        params = action.get("params") or {}
        spec = params.get(param_name) if isinstance(params, dict) else None
        return spec if isinstance(spec, dict) else None
    return None


def _action_enum(device: dict[str, Any], action_name: str, param_name: str) -> list[Any]:
    """读设备某个动作参数的 enum。"""
    spec = _action_param_spec(device, action_name, param_name)
    enum = spec.get("enum") if spec else None
    return list(enum) if isinstance(enum, list) else []


def _validate_parameter_schema(name: Any, spec: Any, path: str, errors: list[str]) -> None:
    """校验一个动作参数的类型和范围。"""
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
    """Room.device_ids 与 Device.room_id 必须双向一致，不对不上也不翻译中文名。"""
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


def _validate_task(task: dict[str, Any], devices: dict[str, dict[str, Any]], errors: list[str]) -> None:
    """校验隐藏 task：intent、conditions、keep、观察和 expected_finish。"""
    if "intent" in task and not isinstance(task.get("intent"), str):
        errors.append("task.intent must be a string")
    for name in ("conditions", "keep"):
        items = task.get(name, [])
        if not isinstance(items, list):
            errors.append(f"task.{name} must be a list")
            continue
        for index, item in enumerate(items):
            _validate_condition(item, f"task.{name}[{index}]", devices, errors)
    required_observations = task.get("required_observations", [])
    if not isinstance(required_observations, list):
        errors.append("task.required_observations must be a list")
    else:
        for index, item in enumerate(required_observations):
            _validate_required_observation(item, f"task.required_observations[{index}]", devices, errors)
    expected_finish = task.get("expected_finish", {})
    if expected_finish is None:
        expected_finish = {}
    if not isinstance(expected_finish, dict):
        errors.append("task.expected_finish must be an object")
        return
    _validate_expected_finish(expected_finish, "task.expected_finish", errors)


def _validate_required_observation(
    item: Any,
    path: str,
    devices: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    """校验要求先 inspect 的房间或设备。"""
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


def _validate_expected_finish(expected: dict[str, Any], path: str, errors: list[str]) -> None:
    """outcome 只许 completed/refused；不要 facts、不要 answered。"""
    if "facts" in expected:
        errors.append(f"{path} must not contain facts")
    outcome = expected.get("outcome")
    if outcome is not None and outcome not in FINISH_OUTCOMES:
        errors.append(f"{path}.outcome must be completed or refused")
    reason_codes = expected.get("allowed_reason_codes", [])
    if not isinstance(reason_codes, list) or not all(isinstance(item, str) and item for item in reason_codes):
        errors.append(f"{path}.allowed_reason_codes must be string[]")
    extra = set(expected) - {"outcome", "allowed_reason_codes"}
    if extra:
        errors.append(f"{path} has unsupported keys: {sorted(extra)}")


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
    elif operator == "in" and not isinstance(condition.get("value", condition.get("equals")), list):
        errors.append(f"{path}.value must be a list for operator=in")


def _validate_episode_config(config: Any, errors: list[str]) -> None:
    """校验回合上限；新契约默认每轮 1 个工具。"""
    if not isinstance(config, dict):
        errors.append("episode_config must be an object")
        return
    max_turns = config.get("max_turns", 10)
    max_calls = config.get("max_tool_calls_per_turn", 1)
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
    """把缺失或空字符串记进错误列表。"""
    if not isinstance(data.get(name), str) or not data.get(name):
        errors.append(f"{path}.{name} must be a non-empty string")


def _is_number(value: Any) -> bool:
    """判断是否为有限数字，排除布尔。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
