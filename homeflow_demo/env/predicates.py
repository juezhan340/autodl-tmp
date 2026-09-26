"""为 C 模块评估隐藏 conditions 和 keep 条件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import StateCondition, copy_json


@dataclass(frozen=True)
class ConditionEvaluation:
    """保存一组隐藏条件的满足比例和逐项结果。"""

    completion: float
    satisfied: tuple[dict[str, Any], ...]
    unsatisfied: tuple[dict[str, Any], ...]

    @property
    def success(self) -> bool:
        """判断条件集合是否全部满足；空集合视为通过。"""
        return not self.unsatisfied

    def to_dict(self) -> dict[str, Any]:
        """把评估结果转换为可保存字典。"""
        return {
            "completion": self.completion,
            "success": self.success,
            "satisfied": [copy_json(item) for item in self.satisfied],
            "unsatisfied": [copy_json(item) for item in self.unsatisfied],
        }


def evaluate_conditions(
    conditions: tuple[StateCondition, ...] | list[StateCondition],
    runtime_state: dict[str, dict[str, Any]],
) -> ConditionEvaluation:
    """依据当前设备状态计算隐藏条件满足比例。"""
    if not conditions:
        return ConditionEvaluation(1.0, (), ())
    satisfied: list[dict[str, Any]] = []
    unsatisfied: list[dict[str, Any]] = []
    for condition in conditions:
        actual = runtime_state.get(condition.device_id, {}).get("state", {}).get(condition.field)
        item = {
            "device_id": condition.device_id,
            "field": condition.field,
            "operator": condition.operator,
            "expected": copy_json(condition.value),
            "actual": copy_json(actual),
        }
        if _compare(actual, condition.operator, condition.value):
            satisfied.append(item)
        else:
            unsatisfied.append(item)
    return ConditionEvaluation(
        completion=len(satisfied) / len(conditions),
        satisfied=tuple(satisfied),
        unsatisfied=tuple(unsatisfied),
    )


def evaluate_task(
    conditions: tuple[StateCondition, ...],
    keep: tuple[StateCondition, ...],
    runtime_state: dict[str, dict[str, Any]],
) -> tuple[ConditionEvaluation, ConditionEvaluation]:
    """同时返回任务目标和状态保持条件评估。"""
    return evaluate_conditions(conditions, runtime_state), evaluate_conditions(keep, runtime_state)


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """执行受限比较操作；类型不兼容时稳定返回 False。"""
    try:
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "gt":
            return actual > expected
        if operator == "ge":
            return actual >= expected
        if operator == "lt":
            return actual < expected
        if operator == "le":
            return actual <= expected
        if operator == "in":
            return actual in expected
    except (TypeError, ValueError):
        return False
    return False
