"""根据统一评测和确定性重放结果决定轨迹能否进入 SFT。"""

from __future__ import annotations

from typing import Any

from homeflow_demo.env.home_env import HomeEnv
from homeflow_demo.env.models import Scenario, ToolCall, copy_json
from homeflow_demo.env.tool_schema import success_envelope

from .episode_evaluator import EpisodeEvaluation


def apply_trajectory_quality(
    evaluation: EpisodeEvaluation,
    trajectory: dict[str, Any],
    scenario: Scenario,
) -> EpisodeEvaluation:
    """检查轨迹结构、事件外壳和 B 状态重放并写回 SFT 门禁结果。"""
    reasons: list[str] = []
    if not evaluation.success:
        reasons.append("episode_not_successful")
    if evaluation.environment_failure_count:
        reasons.append("environment_failure")
    if evaluation.unresolved_error_count:
        reasons.append("unresolved_error")
    if evaluation.strategy_error_count:
        reasons.append("strategy_or_protocol_error")
    if evaluation.parse_error_count:
        reasons.append("assistant_parse_error")
    if evaluation.post_terminal_action_count:
        reasons.append("post_terminal_action")
    if evaluation.truncated:
        reasons.append("episode_truncated")
    if not _has_complete_events(trajectory):
        reasons.append("incomplete_tool_result")

    replayable = replay_trajectory(scenario, trajectory)
    if not replayable:
        reasons.append("trajectory_replay_mismatch")
    evaluation.trajectory_replayable = replayable
    evaluation.rejection_reasons = reasons
    evaluation.accepted_for_sft = not reasons
    return evaluation


def replay_trajectory(scenario: Scenario, trajectory: dict[str, Any]) -> bool:
    """从记录的规范 ToolCall 重放 B 并逐项比对结果和终态。"""
    try:
        env = HomeEnv()
        env.reset(scenario)
        finished = False
        for expected_turn, turn in enumerate(trajectory.get("turns", []), start=1):
            if turn.get("turn_index") != expected_turn:
                return False
            assistant_output = turn.get("assistant_output", {})
            if assistant_output.get("parse_errors"):
                return False
            calls = assistant_output.get("tool_calls", [])
            recorded_events = turn.get("tool_events", [])
            event_cursor = 0
            from .episode_runner import EpisodeRunner

            access_before_turn = env.access_state
            for call_data in calls:
                call = ToolCall.from_dict(call_data)
                if finished:
                    return False
                if call.name == "finish":
                    if event_cursor >= len(recorded_events):
                        return False
                    expected = recorded_events[event_cursor]
                    actual = {
                        "call_id": call.call_id,
                        "tool_name": "finish",
                        "arguments": copy_json(call.arguments),
                        "result": success_envelope(copy_json(call.arguments), 0.0),
                        "state_diff": {},
                    }
                    event_cursor += 1
                    if not _same_event(actual, expected):
                        return False
                    finished = True
                    continue
                dependency_error = EpisodeRunner._same_turn_dependency_error(
                    call, access_before_turn
                )
                if dependency_error is not None:
                    actual = EpisodeRunner._shape_error_event(
                        call,
                        "BAD_REQUEST",
                        dependency_error,
                        "依赖工具结果的调用必须放到下一次 assistant turn",
                    )
                else:
                    actual = env.step(call).event.to_dict()
                if event_cursor >= len(recorded_events):
                    return False
                expected = recorded_events[event_cursor]
                event_cursor += 1
                if not _same_event(actual, expected):
                    return False
            if event_cursor != len(recorded_events):
                return False
        final_result = trajectory.get("final_result", {})
        if not finished and not bool(final_result.get("truncated")):
            return False
        return env.runtime_state == trajectory.get("final_state")
    except (KeyError, TypeError, ValueError, RuntimeError):
        return False


def _has_complete_events(trajectory: dict[str, Any]) -> bool:
    """检查每个 turn 的事件格式和连续编号。"""
    turns = trajectory.get("turns")
    if not isinstance(turns, list) or not turns:
        return False
    for index, turn in enumerate(turns, start=1):
        if turn.get("turn_index") != index or not isinstance(turn.get("tool_events"), list):
            return False
        for event in turn["tool_events"]:
            result = event.get("result")
            if not isinstance(result, dict) or not all(
                key in result for key in ("ok", "data", "error", "meta")
            ):
                return False
            if not isinstance(event.get("state_diff"), dict):
                return False
    return True


def _same_event(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """比较重放事件时忽略机器相关 elapsed_ms。"""
    expected_result = copy_json(expected.get("result"))
    actual_result = copy_json(actual.get("result"))
    for result in (expected_result, actual_result):
        meta = result.get("meta")
        if isinstance(meta, dict):
            meta.pop("elapsed_ms", None)
    return (
        actual.get("call_id") == expected.get("call_id")
        and actual.get("tool_name") == expected.get("tool_name")
        and actual.get("arguments") == expected.get("arguments")
        and actual_result == expected_result
        and actual.get("state_diff") == expected.get("state_diff")
    )
