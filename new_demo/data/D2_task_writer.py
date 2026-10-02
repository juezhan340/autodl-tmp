"""D2 第一次：外部 DeepSeek 按已装配好的 T 模板写 task JSON。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.D0_template import build_prompt, normalize_category
from new_demo.env.B_models import copy_json


@dataclass(frozen=True)
class TaskWriteResult:
    """一次写 task 的结果。"""

    category: str
    task: dict[str, Any] | None
    probe: dict[str, Any] | None
    request_id: str
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """写成草稿字段。"""
        return {
            "category": self.category,
            "task": copy_json(self.task),
            "probe": copy_json(self.probe),
            "request_id": self.request_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class DeepSeekTaskWriter:
    """用 role=external 写隐藏 task，不限 token。"""

    def __init__(self, client: DeepSeekClient) -> None:
        """注入客户端。"""
        self.client = client

    def write(self, *, s0: dict[str, Any], persona: dict[str, Any], category: str) -> TaskWriteResult:
        """按该类固定模板填本轮画像和 s0。"""
        code = normalize_category(category)
        request_id = f"d2_task_{code}_{uuid.uuid4().hex[:8]}"
        prompt = build_prompt("task", code, {"persona": persona, "s0": s0})
        _, parsed = self.client.complete_json(
            [{"role": "user", "content": prompt}],
            role="external",
            request_id=request_id,
        )
        parsed = copy_json(parsed)
        probe = parsed.pop("probe", None)
        error = _task_shape_error(parsed, code, probe if isinstance(probe, dict) else None, s0)
        if error:
            return TaskWriteResult(code, None, None, request_id, "INVALID_TASK_JSON", error)
        return TaskWriteResult(
            category=code,
            task=parsed,
            probe=probe if code == "T4" and isinstance(probe, dict) else None,
            request_id=request_id,
        )


def _task_shape_error(task: dict[str, Any], category: str, probe: dict[str, Any] | None, s0: dict[str, Any] | None = None) -> str | None:
    """只做字段形状检查，不调 B。T3 还要看 s0 上条件是否已经成立。"""
    for key in ("intent", "conditions", "keep", "required_observations", "expected_finish"):
        if key not in task:
            return f"missing {key}"
    if not isinstance(task["intent"], str) or not task["intent"].strip():
        return "intent must be a non-empty string"
    if not isinstance(task["conditions"], list) or not isinstance(task["keep"], list):
        return "conditions/keep must be arrays"
    if not isinstance(task["required_observations"], list):
        return "required_observations must be an array"
    finish = task["expected_finish"]
    if not isinstance(finish, dict):
        return "expected_finish must be an object"
    if "facts" in finish or finish.get("outcome") == "answered":
        return "facts/answered are not allowed"
    outcome = finish.get("outcome")
    if category == "T3":
        held = _t3_already_holds(task, s0)
        if held:
            return held
    if category in {"T1", "T2", "T3", "T5"} and task["required_observations"]:
        return "required_observations must be empty"
    if category == "T4":
        if outcome != "refused":
            return "T4 outcome must be refused"
        if task["conditions"]:
            return "T4 conditions must be empty"
        if not task["required_observations"]:
            return "T4 required_observations must include the refused device"
        if not isinstance(probe, dict):
            return "T4 probe is required"
    else:
        if outcome != "completed":
            return f"{category} outcome must be completed"
        op_error = _operators_error(task["conditions"], {"eq", "ge", "le"}, category)
        if op_error:
            return op_error
        keep_error = _operators_error(task["keep"], {"eq"}, category)
        if keep_error:
            return keep_error
        range_error = _ge_le_value_error(task["conditions"], s0, category)
        if range_error:
            return range_error
    return None


def _operators_error(items: list[Any], allowed: set[str], category: str) -> str | None:
    """conditions 许 eq/ge/le；keep 只许 eq。"""
    for item in items:
        if not isinstance(item, dict):
            return "condition must be an object"
        operator = item.get("operator", "eq")
        if operator not in allowed:
            return f"{category} operator must be one of {sorted(allowed)}"
    return None


def _ge_le_value_error(items: list[Any], s0: dict[str, Any] | None, category: str) -> str | None:
    """ge/le 的 value 必须等于 s0 当前值，不当门槛。"""
    if not s0:
        return None
    devices = {dev.get("device_id"): dev for dev in s0.get("devices") or [] if isinstance(dev, dict)}
    for item in items:
        if not isinstance(item, dict):
            continue
        operator = item.get("operator", "eq")
        if operator not in {"ge", "le"}:
            continue
        device = devices.get(item.get("device_id"))
        if not isinstance(device, dict):
            continue
        actual = (device.get("state") or {}).get(item.get("field"))
        if _as_number(actual) is None or _as_number(item.get("value")) is None:
            return f"{category} ge/le value must equal s0 current value"
        if _as_number(actual) != _as_number(item.get("value")):
            return f"{category} ge/le value must equal s0 current value"
    return None


def _as_number(value: Any) -> float | None:
    """bool 不当数字。"""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _t3_already_holds(task: dict[str, Any], s0: dict[str, Any] | None) -> str | None:
    """eq 已经是目标，或 ge/le 已经顶到上限/下限，这条 T3 不合格。"""
    if not s0:
        return None
    items = task.get("conditions") or []
    if not items or not isinstance(items[0], dict):
        return None
    item = items[0]
    device_id = item.get("device_id")
    field = item.get("field")
    operator = item.get("operator", "eq")
    value = item.get("value")
    devices = {dev.get("device_id"): dev for dev in s0.get("devices") or [] if isinstance(dev, dict)}
    device = devices.get(device_id)
    if not isinstance(device, dict):
        return None
    actual = (device.get("state") or {}).get(field)
    if operator == "eq":
        if actual is None or value is None:
            return None
        if actual == value:
            return "T3 condition already holds on s0"
        return None
    if operator not in {"ge", "le"}:
        return None
    actual_n = _as_number(actual)
    if actual_n is None:
        return None
    minimum, maximum, _step = _dict_field_range(device, str(field))
    if operator == "ge" and maximum is not None and actual_n >= float(maximum) - 1e-9:
        return "T3 condition already holds on s0"
    if operator == "le" and minimum is not None and actual_n <= float(minimum) + 1e-9:
        return "T3 condition already holds on s0"
    return None


def _dict_field_range(device: dict[str, Any], field: str) -> tuple[float | None, float | None, float | None]:
    """从 s0 设备 JSON 读连续量范围。"""
    action_name = {"target": "set_temperature", "level": "set_percentage"}.get(field)
    param = "value"
    if not action_name:
        return None, None, None
    for action in device.get("actions") or []:
        if not isinstance(action, dict) or action.get("action") != action_name:
            continue
        spec = (action.get("params") or {}).get(param) or {}
        return spec.get("minimum"), spec.get("maximum"), spec.get("step")
    return None, None, None

