"""跑完后读隐藏 task 和五项记录，打 C-1..C-4。不调大模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from new_demo.env.B_models import Scenario, StateCondition, copy_json


@dataclass(frozen=True)
class CLabels:
    """四步程序审查，不并进五项回合记录。"""

    protocol: bool
    final_state: bool
    observations: bool
    finish_contract: bool

    def to_dict(self) -> dict[str, bool]:
        """输出 C-1..C-4 的稳定键名。"""
        return {
            "C-1": self.protocol,
            "C-2": self.final_state,
            "C-3": self.observations,
            "C-4": self.finish_contract,
        }

    @property
    def all_true(self) -> bool:
        """四步是否全过。"""
        return self.protocol and self.final_state and self.observations and self.finish_contract


class EpisodeEvaluator:
    """根据五项记录和隐藏 task 生成 C 标签。"""

    def evaluate(
        self,
        scenario: Scenario,
        *,
        turns: list[dict[str, Any]],
        final_state: dict[str, dict[str, Any]],
        finish: dict[str, Any] | None,
        protocol: dict[str, Any],
        too_many_tool_calls: bool,
    ) -> CLabels:
        """C-1 协议、C-2 终态、C-3 观察、C-4 finish 契约。"""
        protocol_ok = (
            bool(protocol.get("finish_requested"))
            and not bool(protocol.get("truncated"))
            and not too_many_tool_calls
        )
        expected = copy_json(scenario.task.expected_finish) or {}
        expected_outcome = expected.get("outcome")
        conditions_ok = _conditions_hold(scenario.task.conditions, final_state)
        keep_ok = _conditions_hold(scenario.task.keep, final_state)
        unchanged = _state_unchanged(scenario, final_state)
        if expected_outcome == "refused":
            final_state_ok = conditions_ok and keep_ok and unchanged
        else:
            final_state_ok = conditions_ok and keep_ok
        observations_ok = _required_observations_met(scenario, turns)
        finish_ok = _finish_contract_valid(expected, finish)
        return CLabels(
            protocol=protocol_ok,
            final_state=final_state_ok,
            observations=observations_ok,
            finish_contract=finish_ok,
        )


def _conditions_hold(
    conditions: tuple[StateCondition, ...],
    runtime_state: dict[str, dict[str, Any]],
) -> bool:
    """空数组算过；否则每个条件都要成立。"""
    for condition in conditions:
        actual = runtime_state.get(condition.device_id, {}).get("state", {}).get(condition.field)
        if not _compare(actual, condition.operator, condition.value):
            return False
    return True


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """受限比较；类型不对就 False。"""
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


def _state_unchanged(scenario: Scenario, runtime_state: dict[str, dict[str, Any]]) -> bool:
    """拒绝任务要求终态相对 s0 没被改。"""
    for device_id, device in scenario.home.devices.items():
        current = runtime_state.get(device_id, {})
        if current.get("state") != device.state:
            return False
    return True


def _required_observations_met(scenario: Scenario, turns: list[dict[str, Any]]) -> bool:
    """required_observations 都要有一次成功 inspect；空数组过。"""
    required = scenario.task.required_observations
    if not required:
        return True
    events: list[dict[str, Any]] = []
    for turn in turns:
        events.extend(turn.get("events") or [])
    successful = [event for event in events if event.get("result", {}).get("ok") is True]
    for item in required:
        kind = item.get("kind")
        if kind == "room":
            if not any(
                event.get("tool_name") == "inspect_room"
                and event.get("arguments", {}).get("room_id") == item.get("room_id")
                for event in successful
            ):
                return False
        elif kind == "device":
            if not any(
                event.get("tool_name") == "inspect_device"
                and event.get("arguments", {}).get("device_id") == item.get("device_id")
                for event in successful
            ):
                return False
        else:
            return False
    return True


def _finish_contract_valid(expected: dict[str, Any], actual: dict[str, Any] | None) -> bool:
    """completed/refused 对齐；只有 summary 失败；不要 facts。"""
    if not expected:
        return actual is not None
    if not isinstance(actual, dict):
        return False
    if "facts" in actual:
        return False
    expected_outcome = expected.get("outcome")
    if expected_outcome is not None and actual.get("outcome") != expected_outcome:
        return False
    allowed_reasons = expected.get("allowed_reason_codes", [])
    if expected_outcome == "refused":
        if actual.get("reason_code") not in allowed_reasons:
            return False
    if expected_outcome == "completed" and actual.get("reason_code"):
        return False
    return True
