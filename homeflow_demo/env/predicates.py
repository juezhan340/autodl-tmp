"""评估设备状态是否满足任务目标。"""

from __future__ import annotations

from typing import Any

from .models import GoalPredicate, PredicateResult


def evaluate_predicates(
    predicates: list[GoalPredicate], devices: dict[str, dict[str, Any]]
) -> PredicateResult:
    """计算目标谓词满足比例并返回满足与未满足明细。"""
    if not predicates:
        return PredicateResult(completion=0.0, satisfied=[], unsatisfied=[])

    satisfied: list[dict[str, Any]] = []
    unsatisfied: list[dict[str, Any]] = []
    for predicate in predicates:
        actual = devices.get(predicate.device_id, {}).get("state", {}).get(predicate.field)
        item = {
            "device_id": predicate.device_id,
            "field": predicate.field,
            "expected": predicate.equals,
            "actual": actual,
        }
        if actual == predicate.equals:
            satisfied.append(item)
        else:
            unsatisfied.append(item)
    return PredicateResult(
        completion=len(satisfied) / len(predicates),
        satisfied=satisfied,
        unsatisfied=unsatisfied,
    )

