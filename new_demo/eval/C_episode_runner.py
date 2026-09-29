"""C 模块：唯一入口 run(scenario)。调度 A 和 B，写出五项记录再打 C 标签。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from new_demo.agents.A_policy import Policy
from new_demo.env.B_home_env import HomeEnv
from new_demo.env.B_models import AssistantTurn, Scenario, ToolCall, ToolEvent, copy_json
from new_demo.env.B_tool_schema import (
    available_tools,
    error_envelope,
    success_envelope,
    validate_tool_call_shape,
)

from .C_episode_evaluator import CLabels, EpisodeEvaluator


@dataclass
class EpisodeRun:
    """五项回合记录加 C 标签，标签不并进五项。"""

    record: dict[str, Any]
    labels: CLabels

    def to_dict(self) -> dict[str, Any]:
        """把一次 C.run 的结果写成可保存字典。"""
        return {
            "record": copy_json(self.record),
            "labels": self.labels.to_dict(),
        }


class EpisodeRunner:
    """围绕 HomeEnv 管理 A/B 多轮交互。"""

    def __init__(
        self,
        policy: Policy,
        env: HomeEnv | None = None,
        evaluator: EpisodeEvaluator | None = None,
    ) -> None:
        """注入 A、B 和评测器。"""
        self.policy = policy
        self.env = env or HomeEnv()
        self.evaluator = evaluator or EpisodeEvaluator()

    def run(self, scenario: Scenario | dict[str, Any]) -> EpisodeRun:
        """执行完整 episode，返回五项记录和 C-1..C-4。"""
        observation = self.env.reset(scenario)
        parsed = self.env.scenario
        history: list[dict[str, Any]] = []
        turns: list[dict[str, Any]] = []
        finish_requested = False
        finish_payload: dict[str, Any] | None = None
        protocol_feedback: dict[str, Any] | None = None
        terminated = False
        truncated = False
        too_many_tool_calls = False

        for turn_index in range(1, parsed.episode_config.max_turns + 1):
            observation_before = copy_json(observation)
            context = {
                "observation": copy_json(observation),
                "tools": available_tools(),
                "history": copy_json(history),
                "protocol_feedback": copy_json(protocol_feedback),
                "turn_index": turn_index,
                "max_turns": parsed.episode_config.max_turns,
            }
            raw_response = self.policy.respond(context)
            assistant_turn = parse_assistant_response(raw_response, turn_index)
            events: list[dict[str, Any]] = []

            if assistant_turn.parse_errors:
                events.append(self._parser_error_event(assistant_turn, turn_index))
                protocol_feedback = self._feedback_from_event(events[-1])
            elif len(assistant_turn.tool_calls) > parsed.episode_config.max_tool_calls_per_turn:
                too_many_tool_calls = True
                events.extend(self._too_many_calls_events(assistant_turn, turn_index))
                protocol_feedback = self._feedback_from_event(events[0])
            else:
                protocol_feedback = None
                for call in assistant_turn.tool_calls:
                    validation = validate_tool_call_shape(call, include_finish=True)
                    if not validation.valid:
                        events.append(
                            self._shape_error_event(
                                call,
                                validation.code or "BAD_REQUEST",
                                validation.message or "invalid call",
                                validation.hint,
                            )
                        )
                        protocol_feedback = self._feedback_from_event(events[-1])
                        continue
                    if call.name == "finish":
                        finish_requested = True
                        finish_payload = copy_json(call.arguments)
                        terminated = True
                        events.append(self._finish_event(call))
                        continue
                    step = self.env.step(call)
                    events.append(step.event.to_dict())
                    if not step.event.ok:
                        protocol_feedback = self._feedback_from_event(events[-1])

            if not terminated and turn_index >= parsed.episode_config.max_turns:
                truncated = True
            observation = self.env.observation()
            turn_record = {
                "turn": turn_index,
                "observation_before": observation_before,
                "tool_calls": [item.to_dict() for item in assistant_turn.tool_calls],
                "events": copy_json(events),
                "observation_after": copy_json(observation),
            }
            turns.append(turn_record)
            history.append({"role": "assistant", "content": assistant_turn.to_dict()})
            history.append({"role": "tool", "content": copy_json(events)})
            if terminated or truncated:
                break

        protocol = {
            "terminated": terminated,
            "truncated": truncated,
            "finish_requested": finish_requested,
            "turn_count": len(turns),
        }
        record = {
            "scenario_id": parsed.scenario_id,
            "turns": turns,
            "final_state": self.env.runtime_state,
            "finish": copy_json(finish_payload),
            "protocol": protocol,
        }
        labels = self.evaluator.evaluate(
            parsed,
            turns=turns,
            final_state=self.env.runtime_state,
            finish=finish_payload,
            protocol=protocol,
            too_many_tool_calls=too_many_tool_calls,
        )
        return EpisodeRun(record=record, labels=labels)

    @staticmethod
    def _finish_event(call: ToolCall) -> dict[str, Any]:
        """C 收下 finish 后写入轨迹，不调用 B.step。"""
        event = ToolEvent(
            call_id=call.call_id,
            tool_name="finish",
            arguments=copy_json(call.arguments),
            result=success_envelope(copy_json(call.arguments)),
            state_diff={},
        )
        return event.to_dict()

    @staticmethod
    def _feedback_from_event(event: dict[str, Any]) -> dict[str, Any]:
        """把本轮错误回执做成下一轮 protocol_feedback。"""
        result = event.get("result") or {}
        error = result.get("error") or {}
        return {
            "ok": bool(result.get("ok")),
            "code": error.get("code"),
            "message": error.get("message"),
            "hint": error.get("hint"),
        }

    @staticmethod
    def _parser_error_event(turn: AssistantTurn, turn_index: int) -> dict[str, Any]:
        """解析失败消耗一个 turn，不执行工具。"""
        event = ToolEvent(
            call_id=f"turn_{turn_index}_parse",
            tool_name="invalid",
            arguments={},
            result=error_envelope(
                "INVALID_ASSISTANT_RESPONSE",
                "; ".join(turn.parse_errors),
                "return one tool call or finish",
            ),
            state_diff={},
        )
        return event.to_dict()

    @staticmethod
    def _too_many_calls_events(turn: AssistantTurn, turn_index: int) -> list[dict[str, Any]]:
        """一轮两个工具：本轮不执行，消耗 turn。"""
        event = ToolEvent(
            call_id=f"turn_{turn_index}_too_many",
            tool_name="invalid",
            arguments={"count": len(turn.tool_calls)},
            result=error_envelope(
                "TOO_MANY_TOOL_CALLS",
                f"got {len(turn.tool_calls)} tool calls, max is 1",
                "each turn may contain at most one tool call",
            ),
            state_diff={},
        )
        return [event.to_dict()]

    @staticmethod
    def _shape_error_event(
        call: ToolCall,
        code: str,
        message: str,
        hint: str | None,
    ) -> dict[str, Any]:
        """工具名或参数形状不对，不进 B。"""
        event = ToolEvent(
            call_id=call.call_id,
            tool_name=call.name,
            arguments=copy_json(call.arguments),
            result=error_envelope(code, message, hint),
            state_diff={},
        )
        return event.to_dict()


def parse_assistant_response(raw_response: Any, turn_index: int) -> AssistantTurn:
    """把 OpenAI 兼容响应、JSON 或纯文本收成 AssistantTurn。"""
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
        except json.JSONDecodeError:
            return AssistantTurn(
                tool_calls=(ToolCall("finish", {"summary": raw_response}, f"turn_{turn_index}_finish"),),
                text=raw_response,
                raw_response=raw_response,
            )
    if not isinstance(raw, dict):
        return AssistantTurn(raw_response=raw_response, parse_errors=("assistant response must be an object",))
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            return AssistantTurn(
                raw_response=copy_json(raw_response),
                parse_errors=("choices[0].message must be an object",),
            )
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
    """解析 OpenAI function call 或 name/arguments 对象。"""
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
    call_id = raw_call_id or f"turn_{turn_index}_{index}"
    return ToolCall(name=name, arguments=copy_json(arguments), call_id=call_id)


def _try_decode_json_tool_call(content: str) -> dict[str, Any] | None:
    """把文本里的单个 JSON 工具调用再交给统一解析器。"""
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
