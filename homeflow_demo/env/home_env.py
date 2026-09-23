"""HomeFlow Demo 的确定性智能家居 episode 环境。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import (
    Action,
    AssistantTurn,
    FinalResult,
    Scenario,
    StepResult,
    ToolEvent,
    TurnResult,
)
from .predicates import evaluate_predicates
from .schema import ensure_valid_scenario
from .state_engine import StateEngine
from .tool_schema import available_tools, normalize_assistant_turn, validate_action


class HomeEpisodeEnv:
    """提供 turn-level 决策步、原子工具审计和终局评估的最小 HomeEnv。"""

    def __init__(self) -> None:
        """创建一个尚未加载场景的空环境。"""
        self._scenario: Scenario | None = None
        self._engine: StateEngine | None = None
        self._turn_count = 0
        self._legacy_step_limit = False
        self._previous_completion = 0.0
        self._valid_action_count = 0
        self._invalid_action_count = 0
        self._terminated = False
        self._truncated = False
        self._failure_reason: str | None = None
        self._last_result: dict[str, Any] | None = None
        self._trajectory: list[dict[str, Any]] = []

    def reset(
        self, scenario: Scenario | dict[str, Any], seed: int | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """加载场景并返回初始 observation 与 episode 信息。"""
        self._legacy_step_limit = isinstance(scenario, dict) and "max_steps" in scenario
        self._scenario = scenario if isinstance(scenario, Scenario) else ensure_valid_scenario(scenario)
        self._engine = StateEngine(self._scenario.devices)
        self._turn_count = 0
        self._previous_completion = self._completion()
        self._valid_action_count = 0
        self._invalid_action_count = 0
        self._terminated = False
        self._truncated = False
        self._failure_reason = None
        self._last_result = None
        self._trajectory = []
        actual_seed = seed if seed is not None else self._scenario.seed
        observation = self._observation()
        info = {
            "scenario_id": self._scenario.scenario_id,
            "seed": actual_seed,
            "completion": self._previous_completion,
            "max_turns": self._scenario.max_turns,
            "max_tool_calls_per_turn": self._scenario.max_tool_calls_per_turn,
            "tools": available_tools(),
        }
        return observation, info

    def step(
        self,
        turn: AssistantTurn | Action | dict[str, Any] | str,
    ) -> StepResult:
        """消费一次 assistant turn，并汇总其中所有工具调用的环境反馈。"""
        self._ensure_ready()
        self._ensure_active()
        observation_before = self._observation()
        try:
            normalized = normalize_assistant_turn(turn)
        except (TypeError, ValueError) as exc:
            return self._record_invalid_turn(
                assistant_output=turn,
                error_code="INVALID_JSON" if isinstance(turn, str) else "INVALID_ASSISTANT_TURN",
                message=str(exc),
                observation_before=observation_before,
            )

        if len(normalized.tool_calls) > self._scenario.max_tool_calls_per_turn:
            return self._record_too_many_tool_calls(normalized, observation_before)

        # 没有工具调用但有文本时，按最终 assistant 回复执行隐式 finish。
        actions = list(normalized.tool_calls)
        if not actions and normalized.text:
            actions = [Action("finish", {"summary": normalized.text})]
        if not actions:
            return self._record_invalid_turn(
                assistant_output=normalized.to_dict(),
                error_code="EMPTY_ASSISTANT_TURN",
                message="assistant turn must contain a tool call or non-empty text",
                observation_before=observation_before,
                normalized_turn=normalized,
            )

        turn_index = self._turn_count + 1
        self._turn_count = turn_index
        previous_completion = self._previous_completion
        reward_components = self._empty_reward_components()
        tool_events: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []

        for tool_event_index, action in enumerate(actions):
            if self._terminated or self._truncated:
                event = ToolEvent(
                    tool_event_index=tool_event_index,
                    action=action.to_dict(),
                    valid=False,
                    ok=False,
                    result={},
                    completion_before=self._completion(),
                    completion_after=self._completion(),
                    error_code="EPISODE_ALREADY_DONE",
                    message="tool call was ignored after episode termination",
                )
                tool_events.append(event.to_dict())
                continue
            event, result, action_rewards = self._apply_action(action, tool_event_index)
            tool_events.append(event.to_dict())
            results.append(result)
            for key, value in action_rewards.items():
                reward_components[key] = reward_components.get(key, 0.0) + value

        completion_after = self._completion()
        reward_components["progress"] += 2.0 * (completion_after - previous_completion)
        self._previous_completion = completion_after
        if not self._terminated and not self._truncated and self._turn_count >= self._scenario.max_turns:
            self._truncated = True
            self._failure_reason = self._limit_failure_reason()
            reward_components["finish"] -= 0.50

        reward = self._clip_reward(sum(reward_components.values()))
        observation_after = self._observation()
        info = self._build_turn_info(
            normalized=normalized,
            actions=actions,
            results=results,
            tool_events=tool_events,
            reward_components=reward_components,
            turn_index=turn_index,
        )
        self._append_transition(
            normalized=normalized,
            actions=actions,
            observation_before=observation_before,
            observation_after=observation_after,
            reward=reward,
            info=info,
            tool_events=tool_events,
            turn_index=turn_index,
        )
        return StepResult(observation_after, reward, self._terminated, self._truncated, info)

    def snapshot(self) -> dict[str, Any]:
        """保存环境内部状态，供调试和 rollout 分支使用。"""
        self._ensure_ready()
        return {
            "scenario": deepcopy(self._scenario.to_dict()),
            "devices": self._engine.snapshot(),
            "turn_count": self._turn_count,
            "step_count": self._turn_count,
            "legacy_step_limit": self._legacy_step_limit,
            "previous_completion": self._previous_completion,
            "valid_action_count": self._valid_action_count,
            "invalid_action_count": self._invalid_action_count,
            "terminated": self._terminated,
            "truncated": self._truncated,
            "failure_reason": self._failure_reason,
            "last_result": deepcopy(self._last_result),
            "trajectory": deepcopy(self._trajectory),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """恢复同一场景的环境快照，并兼容 V1 的 step_count 字段。"""
        scenario = ensure_valid_scenario(snapshot["scenario"])
        if self._scenario is None or self._engine is None:
            self._scenario = scenario
            self._engine = StateEngine(self._scenario.devices)
        elif scenario.scenario_id != self._scenario.scenario_id:
            raise ValueError("snapshot scenario does not match current episode")
        self._engine.restore(snapshot["devices"])
        self._turn_count = int(snapshot.get("turn_count", snapshot.get("step_count", 0)))
        self._legacy_step_limit = bool(snapshot.get("legacy_step_limit", False))
        self._previous_completion = float(snapshot["previous_completion"])
        self._valid_action_count = int(snapshot["valid_action_count"])
        self._invalid_action_count = int(snapshot["invalid_action_count"])
        self._terminated = bool(snapshot["terminated"])
        self._truncated = bool(snapshot["truncated"])
        self._failure_reason = snapshot["failure_reason"]
        self._last_result = deepcopy(snapshot["last_result"])
        self._trajectory = deepcopy(snapshot["trajectory"])

    def fork(self) -> "HomeEpisodeEnv":
        """复制当前 episode，使多个 rollout 可以独立继续。"""
        self._ensure_ready()
        child = HomeEpisodeEnv()
        child.restore(self.snapshot())
        return child

    def trajectory(self) -> list[dict[str, Any]]:
        """返回按 assistant turn 记录的完整 episode 转移。"""
        return deepcopy(self._trajectory)

    def final_result(self) -> FinalResult:
        """返回当前 episode 的成功、完成度、turn 数和最终设备状态。"""
        self._ensure_ready()
        predicate_result = self._predicate_result()
        failure_reason = self._failure_reason
        if not predicate_result.success and failure_reason is None and (self._terminated or self._truncated):
            failure_reason = "TASK_NOT_COMPLETED"
        return FinalResult(
            scenario_id=self._scenario.scenario_id,
            success=predicate_result.success and self._terminated and not self._truncated,
            completion=predicate_result.completion,
            steps=self._turn_count,
            terminated=self._terminated,
            truncated=self._truncated,
            failure_reason=failure_reason,
            final_state=self._engine.devices,
        )

    @property
    def scenario(self) -> Scenario:
        """返回当前场景对象。"""
        self._ensure_ready()
        return self._scenario

    @property
    def devices(self) -> dict[str, dict[str, Any]]:
        """返回当前设备状态的只读副本。"""
        self._ensure_ready()
        return self._engine.devices

    def _apply_action(
        self, action: Action, tool_event_index: int
    ) -> tuple[ToolEvent, dict[str, Any], dict[str, float]]:
        """执行一个原子工具调用并返回审计事件、工具结果和奖励增量。"""
        completion_before = self._completion()
        assert self._engine is not None
        validation = validate_action(action, self._engine.devices)
        if not validation.valid:
            self._invalid_action_count += 1
            result = {"ok": False, "error_code": validation.error_code, "message": validation.message}
            event = ToolEvent(
                tool_event_index=tool_event_index,
                action=action.to_dict(),
                valid=False,
                ok=False,
                result=result,
                completion_before=completion_before,
                completion_after=completion_before,
                error_code=validation.error_code or "INVALID_ACTION",
                message=validation.message or "invalid action",
            )
            return event, result, {"invalid": -0.30}

        self._valid_action_count += 1
        if action.name == "query_device":
            result = self._engine.query(
                str(action.arguments["device_id"]),
                list(action.arguments.get("fields", [])),
            )
            reward_delta = {"query": 0.0}
        elif action.name == "control_device":
            result = self._engine.control(action)
            reward_delta = {"valid": 0.02 if result["changed"] else 0.0}
            if not result["changed"]:
                reward_delta["repeat"] = -0.10
        else:
            result = self._finish(action)
            reward_delta = {"finish": 1.0 if result["ok"] else -0.50}

        completion_after = self._completion()
        event = ToolEvent(
            tool_event_index=tool_event_index,
            action=action.to_dict(),
            valid=True,
            ok=bool(result.get("ok", True)),
            result=deepcopy(result),
            completion_before=completion_before,
            completion_after=completion_after,
        )
        return event, result, reward_delta

    def _finish(self, action: Action) -> dict[str, Any]:
        """处理 finish 动作，并以目标条件作为最终裁判。"""
        predicate_result = self._predicate_result()
        success = predicate_result.success
        self._terminated = True
        self._failure_reason = None if success else "FINISH_BEFORE_GOAL"
        return {
            "ok": success,
            "summary": action.arguments.get("summary", ""),
            "completion": predicate_result.completion,
            "satisfied": predicate_result.satisfied,
            "unsatisfied": predicate_result.unsatisfied,
        }

    def _record_invalid_turn(
        self,
        assistant_output: Any,
        error_code: str,
        message: str,
        observation_before: dict[str, Any],
        normalized_turn: AssistantTurn | None = None,
    ) -> StepResult:
        """记录解析失败或空 turn，不修改设备状态但消耗一个模型 turn。"""
        self._turn_count += 1
        self._invalid_action_count += 1
        reward_components = self._empty_reward_components()
        reward_components["invalid"] = -0.30
        return self._finish_turn_record(
            normalized=normalized_turn or AssistantTurn(assistant_output=assistant_output),
            actions=list(normalized_turn.tool_calls) if normalized_turn else [],
            observation_before=observation_before,
            reward_components=reward_components,
            tool_events=[],
            results=[],
            error_code=error_code,
            message=message,
        )

    def _record_too_many_tool_calls(
        self, turn: AssistantTurn, observation_before: dict[str, Any]
    ) -> StepResult:
        """拒绝超过上限的 turn，并为每个未执行调用保留审计事件。"""
        self._turn_count += 1
        self._invalid_action_count += len(turn.tool_calls)
        completion = self._completion()
        tool_events = [
            ToolEvent(
                tool_event_index=index,
                action=action.to_dict(),
                valid=False,
                ok=False,
                result={},
                completion_before=completion,
                completion_after=completion,
                error_code="TOO_MANY_TOOL_CALLS",
                message=(
                    f"turn contains {len(turn.tool_calls)} tool calls; "
                    f"maximum is {self._scenario.max_tool_calls_per_turn}"
                ),
            ).to_dict()
            for index, action in enumerate(turn.tool_calls)
        ]
        reward_components = self._empty_reward_components()
        reward_components["invalid"] = -0.30 * max(1, len(turn.tool_calls))
        return self._finish_turn_record(
            normalized=turn,
            actions=turn.tool_calls,
            observation_before=observation_before,
            reward_components=reward_components,
            tool_events=tool_events,
            results=[],
            error_code="TOO_MANY_TOOL_CALLS",
            message=tool_events[0]["message"] if tool_events else "too many tool calls",
        )

    def _finish_turn_record(
        self,
        normalized: AssistantTurn,
        actions: list[Action],
        observation_before: dict[str, Any],
        reward_components: dict[str, float],
        tool_events: list[dict[str, Any]],
        results: list[dict[str, Any]],
        error_code: str | None = None,
        message: str | None = None,
    ) -> StepResult:
        """完成异常 turn 的计数、截断判断、轨迹记录和返回值组装。"""
        if not self._terminated and not self._truncated and self._turn_count >= self._scenario.max_turns:
            self._truncated = True
            self._failure_reason = self._limit_failure_reason()
            reward_components["finish"] -= 0.50
        reward = self._clip_reward(sum(reward_components.values()))
        observation_after = self._observation()
        info = self._build_turn_info(
            normalized=normalized,
            actions=actions,
            results=results,
            tool_events=tool_events,
            reward_components=reward_components,
            turn_index=self._turn_count,
        )
        if error_code:
            info["error_code"] = error_code
            info["message"] = message or "invalid assistant turn"
            info["ok"] = False
        self._append_transition(
            normalized=normalized,
            actions=actions,
            observation_before=observation_before,
            observation_after=observation_after,
            reward=reward,
            info=info,
            tool_events=tool_events,
            turn_index=self._turn_count,
        )
        return StepResult(observation_after, reward, self._terminated, self._truncated, info)

    def _observation(self) -> dict[str, Any]:
        """构造当前时刻给模型或调试器看的 observation。"""
        self._ensure_ready()
        return {
            "scenario_id": self._scenario.scenario_id,
            "user_request": self._scenario.user_request,
            "devices": self._visible_devices(),
            "tools": available_tools(),
            "last_result": deepcopy(self._last_result),
            "turn": self._turn_count,
            "max_turns": self._scenario.max_turns,
            # 保留旧字段供 V1 调试脚本读取，数值已经按 turn 计数。
            "step": self._turn_count,
            "max_steps": self._scenario.max_turns,
        }

    def _visible_devices(self) -> list[dict[str, Any]]:
        """返回当前设备公开状态，不暴露隐藏目标条件。"""
        return [
            {
                "id": device["id"],
                "type": device["type"],
                "room": device["room"],
                "state": deepcopy(device["state"]),
            }
            for device in self._engine.devices.values()
        ]

    def _predicate_result(self):
        """计算当前设备状态对应的目标条件结果。"""
        return evaluate_predicates(self._scenario.predicates, self._engine.devices)

    def _completion(self) -> float:
        """返回当前目标完成度。"""
        return self._predicate_result().completion

    def _build_turn_info(
        self,
        normalized: AssistantTurn,
        actions: list[Action],
        results: list[dict[str, Any]],
        tool_events: list[dict[str, Any]],
        reward_components: dict[str, float],
        turn_index: int,
    ) -> dict[str, Any]:
        """组装一次模型 turn 的训练、审计和兼容信息。"""
        info: dict[str, Any] = {
            "turn_index": turn_index,
            "assistant_output": normalized.to_dict(),
            "tool_calls": [action.to_dict() for action in actions],
            "tool_events": deepcopy(tool_events),
            "results": deepcopy(results),
            "completion": self._completion(),
            "reward_components": deepcopy(reward_components),
            "turn": turn_index,
            "step": turn_index,
            "ok": all(event["ok"] for event in tool_events) if tool_events else False,
        }
        if len(actions) == 1:
            info["action"] = actions[0].to_dict()
            if results:
                info["result"] = deepcopy(results[0])
        elif actions:
            info["actions"] = [action.to_dict() for action in actions]
        if any(action.name == "finish" for action in actions):
            finish_events = [event for event in tool_events if event["action"]["name"] == "finish"]
            info["success"] = bool(finish_events and finish_events[-1]["ok"])
        invalid_events = [event for event in tool_events if not event["valid"]]
        if invalid_events:
            info["error_code"] = invalid_events[0]["error_code"]
            info["message"] = invalid_events[0]["message"]
            info["ok"] = False
        return info

    def _append_transition(
        self,
        normalized: AssistantTurn,
        actions: list[Action],
        observation_before: dict[str, Any],
        observation_after: dict[str, Any],
        reward: float,
        info: dict[str, Any],
        tool_events: list[dict[str, Any]],
        turn_index: int,
    ) -> None:
        """把一次 assistant turn 写入可复盘的单条策略转移。"""
        self._last_result = deepcopy(info.get("results", info))
        turn_result = TurnResult(
            turn_index=turn_index,
            assistant_output=normalized.to_dict(),
            tool_calls=[action.to_dict() for action in actions],
            tool_events=tool_events,
            observation_before=observation_before,
            observation_after=observation_after,
            reward=reward,
            reward_components=info["reward_components"],
            terminated=self._terminated,
            truncated=self._truncated,
        )
        record = turn_result.to_dict()
        record["turn"] = turn_index
        record["step"] = turn_index
        record["action"] = actions[0].to_dict() if len(actions) == 1 else None
        record["actions"] = [action.to_dict() for action in actions]
        record["observation"] = deepcopy(observation_after)
        record["info"] = deepcopy(info)
        self._trajectory.append(record)

    @staticmethod
    def _empty_reward_components() -> dict[str, float]:
        """返回一次 turn 的固定奖励分量初值。"""
        return {
            "progress": 0.0,
            "valid": 0.0,
            "query": 0.0,
            "repeat": 0.0,
            "finish": 0.0,
            "invalid": 0.0,
            "turn": -0.01,
        }

    def _ensure_ready(self) -> None:
        """确保 reset 已经加载场景。"""
        if self._scenario is None or self._engine is None:
            raise RuntimeError("call reset(scenario) before using HomeEpisodeEnv")

    def _limit_failure_reason(self) -> str:
        """返回兼容旧字段的截断原因。"""
        return "MAX_STEPS" if self._legacy_step_limit else "MAX_TURNS"

    def _ensure_active(self) -> None:
        """确保当前 episode 尚未结束。"""
        if self._terminated or self._truncated:
            raise RuntimeError("episode is already terminated or truncated")

    @staticmethod
    def _clip_reward(value: float) -> float:
        """把 reward 限制在稳定的 Demo 范围内。"""
        return max(-1.0, min(2.0, float(value)))
