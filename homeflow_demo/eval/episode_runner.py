"""实现 C 模块：解析 A 响应、调度 B、记录轨迹并生成评测结果。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from homeflow_demo.env.home_env import HomeEnv
from homeflow_demo.env.models import AssistantTurn, Scenario, ToolCall, ToolEvent, copy_json
from homeflow_demo.env.tool_schema import (
    available_tools,
    classify_error,
    error_envelope,
    success_envelope,
    validate_tool_call_shape,
)

from .episode_evaluator import EpisodeEvaluation, EpisodeEvaluator
from .trajectory_quality import apply_trajectory_quality


class Policy(Protocol):
    """规定 A 模块最小响应接口。"""

    def respond(self, context: dict[str, Any]) -> Any:
        """根据当前 observation 和历史产生一次 assistant 响应。"""


@dataclass
class EpisodeRun:
    """保存 C 完成一次 episode 后的轨迹和评测。"""

    trajectory: dict[str, Any]
    evaluation: EpisodeEvaluation

    def to_dict(self) -> dict[str, Any]:
        """把运行结果转换成 JSON 可序列化字典。"""
        result = copy_json(self.trajectory)
        result["evaluation"] = self.evaluation.to_dict()
        return result


class EpisodeRunner:
    """围绕 HomeEnv 管理 A/B 多轮交互和 C 的 episode 生命周期。"""

    def __init__(
        self,
        policy: Policy,
        env: HomeEnv | None = None,
        evaluator: EpisodeEvaluator | None = None,
        model_id: str = "unknown",
    ) -> None:
        """注入 A policy、B HomeEnv 和可替换的评测器。"""
        self.policy = policy
        self.env = env or HomeEnv()
        self.evaluator = evaluator or EpisodeEvaluator()
        self.model_id = model_id

    def run(self, scenario: Scenario | dict[str, Any]) -> EpisodeRun:
        """执行完整 episode，并返回轨迹与唯一评测结果。"""
        observation, reset_info = self.env.reset(scenario)
        parsed_scenario = self.env.scenario
        history: list[dict[str, Any]] = []
        turns: list[dict[str, Any]] = []
        all_events: list[dict[str, Any]] = []
        turn_rewards: list[dict[str, float]] = []
        parse_error_count = 0
        post_terminal_action_count = 0
        finish_requested = False
        finish_payload: dict[str, Any] | None = None
        protocol_feedback: dict[str, Any] | None = None
        terminated = False
        truncated = False

        for turn_index in range(1, parsed_scenario.episode_config.max_turns + 1):
            observation_before = copy_json(observation)
            context = {
                "observation": copy_json(observation),
                "tools": available_tools(),
                "history": copy_json(history),
                "protocol_feedback": copy_json(protocol_feedback),
                "turn_index": turn_index,
                "max_turns": parsed_scenario.episode_config.max_turns,
            }
            raw_response = self.policy.respond(context)
            assistant_turn = parse_assistant_response(raw_response, turn_index)
            events: list[dict[str, Any]] = []
            reward_components: dict[str, float] = {
                "goal_progress": 0.0,
                "valid_action": 0.0,
                "strategy_error": 0.0,
                "tool_cost": 0.0,
                "environment_failure": 0.0,
            }
            before_completion = self._completion(parsed_scenario)

            if assistant_turn.parse_errors:
                parse_error_count += len(assistant_turn.parse_errors)
                events.append(self._parser_error_event(assistant_turn, turn_index))
                reward_components["strategy_error"] -= 0.10 * len(assistant_turn.parse_errors)
                protocol_feedback = self._feedback_from_event(events[-1])
            elif len(assistant_turn.tool_calls) > parsed_scenario.episode_config.max_tool_calls_per_turn:
                count = len(assistant_turn.tool_calls)
                parse_error_count += 1
                events.extend(self._too_many_calls_events(assistant_turn, turn_index))
                reward_components["strategy_error"] -= 0.10 * count
                protocol_feedback = self._feedback_from_event(events[0])
            else:
                protocol_feedback = None
                for call in assistant_turn.tool_calls:
                    if finish_requested:
                        post_terminal_action_count += 1
                        events.append(self._post_terminal_event(call, turn_index))
                        reward_components["strategy_error"] -= 0.10
                        protocol_feedback = self._feedback_from_event(events[-1])
                        continue
                    validation = validate_tool_call_shape(call, include_finish=True)
                    if not validation.valid:
                        parse_error_count += 1
                        events.append(self._shape_error_event(call, validation.code or "BAD_REQUEST", validation.message or "invalid call", validation.hint))
                        reward_components["strategy_error"] -= 0.10
                        protocol_feedback = self._feedback_from_event(events[-1])
                        continue
                    reward_components["tool_cost"] -= 0.01
                    if call.name == "finish":
                        finish_requested = True
                        finish_payload = copy_json(call.arguments)
                        terminated = True
                        event = self._finish_event(call)
                        events.append(event)
                        continue
                    step = self.env.step(call)
                    event = step.event.to_dict()
                    events.append(event)
                    category = classify_error(step.event.error_code)
                    if step.event.ok:
                        if call.name == "execute_action" and step.event.state_diff:
                            reward_components["valid_action"] += 0.02
                    elif category == "strategy_error":
                        reward_components["strategy_error"] -= 0.10
                    elif category == "environment_failure":
                        reward_components["environment_failure"] -= 0.10
                        protocol_feedback = self._feedback_from_event(events[-1])
                        truncated = True
                        break
            after_completion = self._completion(parsed_scenario)
            reward_components["goal_progress"] += round(
                after_completion - before_completion, 6
            )
            if not terminated and not truncated and turn_index >= parsed_scenario.episode_config.max_turns:
                truncated = True
            turn_reward = round(sum(reward_components.values()), 6)
            turn_rewards.append(reward_components)
            observation = self.env.observation()
            turn_record = {
                "turn_index": turn_index,
                "assistant_output": assistant_turn.to_dict(),
                "observation_before": observation_before,
                "observation_after": copy_json(observation),
                "tool_events": copy_json(events),
                "reward": turn_reward,
                "reward_components": copy_json(reward_components),
                "terminated": terminated,
                "truncated": truncated,
            }
            turns.append(turn_record)
            all_events.extend(events)
            history.append({"role": "assistant", "content": assistant_turn.to_dict()})
            history.append({"role": "tool", "content": copy_json(events)})
            if terminated or truncated:
                break

        evaluation = self.evaluator.evaluate(
            parsed_scenario,
            self.env.runtime_state,
            all_events,
            terminated=terminated,
            truncated=truncated,
            finish_requested=finish_requested,
            finish_payload=finish_payload,
            turn_rewards=turn_rewards,
            parse_error_count=parse_error_count,
            post_terminal_action_count=post_terminal_action_count,
        )
        trajectory = {
            "format_version": "v1.2-turn",
            "scenario_id": parsed_scenario.scenario_id,
            "model_id": self.model_id,
            "reset_info": copy_json(reset_info),
            "turns": turns,
            "final_result": evaluation.to_dict(),
            "final_state": self.env.runtime_state,
            "finish_payload": copy_json(finish_payload),
            "metadata": copy_json(parsed_scenario.metadata),
        }
        apply_trajectory_quality(evaluation, trajectory, parsed_scenario)
        trajectory["final_result"] = evaluation.to_dict()
        return EpisodeRun(trajectory=trajectory, evaluation=evaluation)

    def _completion(self, scenario: Scenario) -> float:
        """只为 reward shaping 读取当前隐藏条件完成度，不写入 observation。"""
        from homeflow_demo.env.predicates import evaluate_conditions

        return evaluate_conditions(scenario.task.conditions, self.env.runtime_state).completion

    @staticmethod
    def _finish_event(call: ToolCall) -> dict[str, Any]:
        """构造 runner 处理 finish 后返回给轨迹的终止事件。"""
        event = ToolEvent(
            call_id=call.call_id,
            tool_name="finish",
            arguments=copy_json(call.arguments),
            result=success_envelope(copy_json(call.arguments), 0.0),
            state_diff={},
        )
        return event.to_dict()

    @staticmethod
    def _feedback_from_event(event: dict[str, Any]) -> dict[str, Any]:
        """把本回合协议或环境错误压缩成下一回合可见反馈。"""
        result = event.get("result", {})
        error = result.get("error") if isinstance(result, dict) else None
        if not isinstance(error, dict):
            return {}
        return {
            "type": "protocol_feedback",
            "code": error.get("code"),
            "message": error.get("message"),
            "hint": error.get("hint"),
        }

    @staticmethod
    def _parser_error_event(turn: AssistantTurn, turn_index: int) -> dict[str, Any]:
        """把模型消息解析失败转换成可审计的策略错误事件。"""
        event = ToolEvent(
            call_id=f"turn_{turn_index}_parser",
            tool_name="__assistant_parser__",
            arguments={},
            result=error_envelope("INVALID_ASSISTANT_RESPONSE", "; ".join(turn.parse_errors), 0.0),
            state_diff={},
        )
        return event.to_dict()

    @staticmethod
    def _too_many_calls_events(turn: AssistantTurn, turn_index: int) -> list[dict[str, Any]]:
        """为超过上限的每个调用保留未执行审计事件。"""
        return [
            ToolEvent(
                call_id=call.call_id or f"turn_{turn_index}_call_{index}",
                tool_name=call.name,
                arguments=copy_json(call.arguments),
                result=error_envelope("TOO_MANY_TOOL_CALLS", "too many tool calls in one assistant turn", 0.0),
                state_diff={},
            ).to_dict()
            for index, call in enumerate(turn.tool_calls)
        ]

    @staticmethod
    def _shape_error_event(
        call: ToolCall,
        code: str,
        message: str,
        hint: str | None,
    ) -> dict[str, Any]:
        """把 C 的工具形状错误记录为统一事件，不进入 B。"""
        event = ToolEvent(
            call_id=call.call_id,
            tool_name=call.name,
            arguments=copy_json(call.arguments),
            result=error_envelope(code, message, 0.0, hint),
            state_diff={},
        )
        return event.to_dict()

    @staticmethod
    def _post_terminal_event(call: ToolCall, turn_index: int) -> dict[str, Any]:
        """记录 finish 后仍然出现的多余调用。"""
        event = ToolEvent(
            call_id=call.call_id or f"turn_{turn_index}_post_terminal",
            tool_name=call.name,
            arguments=copy_json(call.arguments),
            result=error_envelope("BAD_REQUEST", "tool call appeared after finish", 0.0),
            state_diff={},
        )
        return event.to_dict()

def parse_assistant_response(raw_response: Any, turn_index: int) -> AssistantTurn:
    """把常见 OpenAI 兼容响应或 JSON 响应解析为统一 AssistantTurn。"""
    if isinstance(raw_response, AssistantTurn):
        if not raw_response.tool_calls and raw_response.text and not raw_response.parse_errors:
            return AssistantTurn(
                tool_calls=(ToolCall("finish", {"summary": raw_response.text}, f"turn_{turn_index}_finish"),),
                text=raw_response.text,
                raw_response=copy_json(raw_response.raw_response),
            )
        return raw_response
    raw = raw_response
    if isinstance(raw_response, str):
        try:
            raw = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            return AssistantTurn(raw_response=raw_response, parse_errors=(f"invalid JSON: {exc.msg}",))
    if not isinstance(raw, dict):
        return AssistantTurn(raw_response=raw_response, parse_errors=("assistant response must be an object",))
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            return AssistantTurn(raw_response=copy_json(raw_response), parse_errors=("choices[0].message must be an object",))
        raw = {
            "tool_calls": message.get("tool_calls", []),
            "content": message.get("content", ""),
            "finish_reason": choice.get("finish_reason"),
        }
        if not raw["tool_calls"] and isinstance(raw.get("content"), str):
            decoded_content = _try_decode_json_tool_call(raw["content"])
            if decoded_content is not None:
                raw = decoded_content
    calls = raw.get("tool_calls", [])
    if not calls and "name" in raw:
        calls = [raw]
    if not isinstance(calls, list):
        return AssistantTurn(raw_response=raw_response, parse_errors=("tool_calls must be a list",))
    parsed: list[ToolCall] = []
    errors: list[str] = []
    for index, item in enumerate(calls):
        try:
            parsed.append(_parse_tool_call(item, turn_index, index))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"tool_calls[{index}]: {exc}")
    text = raw.get("text", "")
    if not text and isinstance(raw.get("content"), str):
        text = raw["content"]
    if text is not None and not isinstance(text, str):
        errors.append("assistant text/content must be a string")
        text = ""
    if not parsed and not errors:
        if text:
            parsed.append(
                ToolCall(
                    name="finish",
                    arguments={"summary": text},
                    call_id=f"turn_{turn_index}_finish",
                )
            )
        else:
            errors.append("assistant response contains no tool call or final text")
    return AssistantTurn(
        tool_calls=tuple(parsed),
        text=text or "",
        raw_response=copy_json(raw_response),
        parse_errors=tuple(errors),
    )


def _parse_tool_call(item: Any, turn_index: int, index: int) -> ToolCall:
    """解析一个 OpenAI function call 或统一 name/arguments 对象。"""
    if not isinstance(item, dict):
        raise TypeError("tool call must be an object")
    function = item.get("function")
    if isinstance(function, dict):
        name = function.get("name", "")
        arguments = function.get("arguments", {})
    else:
        name = item.get("name", "")
        arguments = item.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(name, str) or not name:
        raise ValueError("tool name is missing")
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    raw_call_id = item.get("id", item.get("call_id", ""))
    if not isinstance(raw_call_id, str):
        raise TypeError("tool call id/call_id must be a string")
    return ToolCall(
        name=name,
        arguments=copy_json(arguments),
        call_id=raw_call_id,
    )


def _try_decode_json_tool_call(content: str) -> dict[str, Any] | None:
    """把策略以文本返回的单个 JSON 工具调用重新交给统一解析器。"""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    if "name" in decoded or "tool_calls" in decoded:
        return decoded
    return None
