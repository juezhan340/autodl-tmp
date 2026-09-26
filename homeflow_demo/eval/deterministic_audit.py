"""汇总 C 已完成的确定性状态、协议和轨迹审查结果。"""

from __future__ import annotations

from typing import Any

from homeflow_demo.env.models import Scenario, copy_json

from .episode_runner import EpisodeRun


def audit_episode(scenario: Scenario, run: EpisodeRun) -> dict[str, Any]:
    """把 EpisodeEvaluation 转换成语义裁判可读取的确定性摘要。"""
    evaluation = run.evaluation
    return {
        "passed": bool(evaluation.deterministic_passed),
        "physical_goal_met": bool(evaluation.goal_completion >= 1.0),
        "required_observations_met": bool(evaluation.required_observations_met),
        "state_unchanged_when_required": bool(evaluation.state_unchanged_when_required),
        "finish_contract_valid": bool(evaluation.finish_contract_valid),
        "finish_requested": bool(evaluation.terminated),
        "expected_outcome": evaluation.expected_outcome,
        "protocol_errors": _protocol_errors(run.trajectory),
        "failure_class": evaluation.failure_class,
        "replayable": bool(evaluation.trajectory_replayable),
        "scenario_id": scenario.scenario_id,
    }


def _protocol_errors(trajectory: dict[str, Any]) -> list[dict[str, Any]]:
    """从完整轨迹提取协议错误，供裁判区分策略与环境问题。"""
    errors: list[dict[str, Any]] = []
    for turn in trajectory.get("turns", []):
        for event in turn.get("tool_events", []):
            result = event.get("result", {})
            if result.get("ok") is False:
                error = result.get("error")
                if isinstance(error, dict):
                    errors.append({
                        "turn_index": turn.get("turn_index"),
                        "tool_name": event.get("tool_name"),
                        "code": error.get("code"),
                        "message": error.get("message"),
                    })
    return copy_json(errors)
