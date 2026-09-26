"""实现 C 模块的隐藏目标评测、错误归因和 reward 汇总。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from homeflow_demo.env.models import Scenario, copy_json
from homeflow_demo.env.predicates import ConditionEvaluation, evaluate_task
from homeflow_demo.env.tool_schema import classify_error


@dataclass
class EpisodeEvaluation:
    """保存一次 episode 的统一评测结果。"""

    scenario_id: str
    success: bool
    goal_completion: float
    keep_preservation: float
    terminated: bool
    truncated: bool
    strategy_error_count: int
    environment_failure_count: int
    unresolved_error_count: int
    failure_class: str
    reward: float
    reward_components: dict[str, float]
    accepted_for_sft: bool
    rejection_reasons: list[str] = field(default_factory=list)
    trajectory_replayable: bool = False
    parse_error_count: int = 0
    post_terminal_action_count: int = 0
    finish_payload: dict[str, Any] | None = None
    expected_outcome: str | None = None
    required_observations_met: bool = True
    state_unchanged_when_required: bool = True
    finish_contract_valid: bool = True
    deterministic_passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """把评测结果转换成稳定的 JSON 字典。"""
        return {
            "scenario_id": self.scenario_id,
            "success": self.success,
            "goal_completion": self.goal_completion,
            "keep_preservation": self.keep_preservation,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "strategy_error_count": self.strategy_error_count,
            "environment_failure_count": self.environment_failure_count,
            "unresolved_error_count": self.unresolved_error_count,
            "failure_class": self.failure_class,
            "reward": self.reward,
            "reward_components": copy_json(self.reward_components),
            "accepted_for_sft": self.accepted_for_sft,
            "rejection_reasons": list(self.rejection_reasons),
            "trajectory_replayable": self.trajectory_replayable,
            "parse_error_count": self.parse_error_count,
            "post_terminal_action_count": self.post_terminal_action_count,
            "finish_payload": copy_json(self.finish_payload),
            "expected_outcome": self.expected_outcome,
            "required_observations_met": self.required_observations_met,
            "state_unchanged_when_required": self.state_unchanged_when_required,
            "finish_contract_valid": self.finish_contract_valid,
            "deterministic_passed": self.deterministic_passed,
        }


class EpisodeEvaluator:
    """读取隐藏 Scenario 目标并生成唯一的 EpisodeEvaluation。"""

    def evaluate(
        self,
        scenario: Scenario,
        runtime_state: dict[str, dict[str, Any]],
        events: Iterable[dict[str, Any]],
        *,
        terminated: bool,
        truncated: bool,
        finish_requested: bool,
        finish_payload: dict[str, Any] | None = None,
        turn_rewards: Iterable[dict[str, float]],
        parse_error_count: int = 0,
        post_terminal_action_count: int = 0,
    ) -> EpisodeEvaluation:
        """聚合隐藏目标、事件错误、终止状态和逐 turn reward。"""
        condition_result, keep_result = evaluate_task(
            scenario.task.conditions,
            scenario.task.keep,
            runtime_state,
        )
        event_list = list(events)
        expected_finish = copy_json(scenario.task.expected_finish)
        expected_outcome = expected_finish.get("outcome") if expected_finish else None
        required_observations_met = _required_observations_met(
            scenario,
            event_list,
        )
        state_unchanged_when_required = _state_unchanged(
            scenario,
            runtime_state,
        ) if expected_outcome in {"answered", "refused"} else True
        finish_contract_valid = _finish_contract_valid(
            expected_finish,
            finish_payload,
        )
        strategy_error_count = 0
        environment_failure_count = 0
        unresolved_error_count = 0
        for event in event_list:
            error = event.get("result", {}).get("error")
            code = error.get("code") if isinstance(error, dict) else None
            category = classify_error(code)
            if code is None:
                continue
            if category == "strategy_error":
                strategy_error_count += 1
            elif category == "environment_failure":
                environment_failure_count += 1
            elif category == "unresolved":
                unresolved_error_count += 1

        feasible = bool(scenario.metadata.get("feasible", True))
        success = _deterministic_success(
            feasible=feasible,
            finish_requested=finish_requested,
            terminated=terminated,
            truncated=truncated,
            condition_success=condition_result.success,
            keep_success=keep_result.success,
            expected_outcome=expected_outcome,
            required_observations_met=required_observations_met,
            state_unchanged_when_required=state_unchanged_when_required,
            finish_contract_valid=finish_contract_valid,
        )
        reward_components = _sum_reward_components(turn_rewards)
        if success:
            reward_components["terminal_success"] = reward_components.get("terminal_success", 0.0) + 1.0
        elif finish_requested and not truncated:
            reward_components["terminal_failure"] = reward_components.get("terminal_failure", 0.0) - 0.20
        reward = round(sum(reward_components.values()), 6)

        rejection_reasons: list[str] = []
        return EpisodeEvaluation(
            scenario_id=scenario.scenario_id,
            success=success,
            goal_completion=condition_result.completion,
            keep_preservation=keep_result.completion,
            terminated=terminated,
            truncated=truncated,
            strategy_error_count=strategy_error_count,
            environment_failure_count=environment_failure_count,
            unresolved_error_count=unresolved_error_count,
            failure_class=self._failure_class(
                success=success,
                truncated=truncated,
                finish_requested=finish_requested,
                strategy_error_count=strategy_error_count,
                environment_failure_count=environment_failure_count,
                unresolved_error_count=unresolved_error_count,
                condition_result=condition_result,
                keep_result=keep_result,
                feasible=feasible,
            ),
            reward=reward,
            reward_components=reward_components,
            accepted_for_sft=False,
            rejection_reasons=rejection_reasons,
            parse_error_count=parse_error_count,
            post_terminal_action_count=post_terminal_action_count,
            finish_payload=copy_json(finish_payload),
            expected_outcome=expected_outcome,
            required_observations_met=required_observations_met,
            state_unchanged_when_required=state_unchanged_when_required,
            finish_contract_valid=finish_contract_valid,
            deterministic_passed=success,
        )

    @staticmethod
    def _failure_class(
        *,
        success: bool,
        truncated: bool,
        finish_requested: bool,
        strategy_error_count: int,
        environment_failure_count: int,
        unresolved_error_count: int,
        condition_result: ConditionEvaluation,
        keep_result: ConditionEvaluation,
        feasible: bool,
    ) -> str:
        """给 episode 选择互斥的主失败类别。"""
        if success:
            return "none"
        if environment_failure_count:
            return "environment_failure"
        if unresolved_error_count:
            return "unresolved_error"
        if strategy_error_count:
            return "strategy_error"
        if not feasible:
            return "task_definition_error"
        if truncated:
            return "truncated"
        if not finish_requested:
            return "no_finish"
        if not condition_result.success:
            return "goal_not_completed"
        if not keep_result.success:
            return "keep_violated"
        return "task_not_completed"


def _sum_reward_components(turn_rewards: Iterable[dict[str, float]]) -> dict[str, float]:
    """把每个 turn 的奖励分量求和并移除浮点噪声。"""
    total: dict[str, float] = {}
    for components in turn_rewards:
        for name, value in components.items():
            total[name] = round(total.get(name, 0.0) + float(value), 6)
    return total


def _deterministic_success(
    *,
    feasible: bool,
    finish_requested: bool,
    terminated: bool,
    truncated: bool,
    condition_success: bool,
    keep_success: bool,
    expected_outcome: str | None,
    required_observations_met: bool,
    state_unchanged_when_required: bool,
    finish_contract_valid: bool,
) -> bool:
    """根据任务类别合并 C 层可机械判断的成功条件。"""
    if not feasible or not finish_requested or not terminated or truncated:
        return False
    if expected_outcome in {"answered", "refused"}:
        return required_observations_met and state_unchanged_when_required and finish_contract_valid
    if expected_outcome == "completed":
        return condition_success and keep_success and finish_contract_valid
    return condition_success and keep_success


def _required_observations_met(scenario: Scenario, events: list[dict[str, Any]]) -> bool:
    """检查任务要求的房间或设备是否被成功观察过。"""
    required = scenario.task.required_observations
    if not required:
        return True
    successful = [
        event
        for event in events
        if event.get("result", {}).get("ok") is True
    ]
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


def _state_unchanged(scenario: Scenario, runtime_state: dict[str, dict[str, Any]]) -> bool:
    """比较查询或拒绝任务的最终设备状态与初始快照。"""
    for device_id, device in scenario.home.devices.items():
        current = runtime_state.get(device_id, {})
        if current.get("state") != device.state:
            return False
    return True


def _finish_contract_valid(expected: dict[str, Any], actual: dict[str, Any] | None) -> bool:
    """检查 outcome、facts 和 reason_code 是否满足隐藏 finish 契约。"""
    if not expected:
        return True
    if not isinstance(actual, dict):
        return False
    expected_outcome = expected.get("outcome")
    if expected_outcome is not None and actual.get("outcome") != expected_outcome:
        return False
    allowed_reasons = expected.get("allowed_reason_codes", [])
    if expected_outcome == "refused":
        if actual.get("reason_code") not in allowed_reasons:
            return False
    expected_facts = expected.get("facts", [])
    if expected_facts:
        actual_facts = actual.get("facts")
        if not isinstance(actual_facts, list):
            return False
        if _canonical_json_list(expected_facts) != _canonical_json_list(actual_facts):
            return False
    return True


def _canonical_json_list(values: list[Any]) -> list[str]:
    """把事实数组规范化为可比较的 JSON 字符串列表。"""
    import json

    return sorted(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in values)
