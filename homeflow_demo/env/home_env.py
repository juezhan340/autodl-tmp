"""实现只负责家庭工具执行的 HomeFlow V1.2 B 模块。"""

from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any

from .models import EnvStepResult, Scenario, ToolCall, ToolEvent, copy_json
from .schema import ensure_valid_scenario
from .state_engine import StateEngine
from .tool_schema import (
    available_tools,
    error_envelope,
    policy_result_view,
    success_envelope,
    validate_tool_call_shape,
)


class HomeEnv:
    """接收规范化 ToolCall，维护家庭运行状态并返回统一工具结果。"""

    def __init__(self) -> None:
        """创建尚未加载 Scenario 的空环境。"""
        self._scenario: Scenario | None = None
        self._engine: StateEngine | None = None
        self._last_policy_result: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []

    def reset(
        self,
        scenario: Scenario | dict[str, Any],
        seed: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """加载场景家庭快照并返回不含隐藏任务条件的初始 observation。"""
        self._scenario = ensure_valid_scenario(scenario)
        self._engine = StateEngine(self._scenario.home)
        self._last_policy_result = None
        self._events = []
        observation = self.observation()
        info = {
            "scenario_id": self._scenario.scenario_id,
            "seed": self._scenario.seed if seed is None else seed,
            "tools": available_tools(),
        }
        return observation, info

    def step(self, call: ToolCall | dict[str, Any]) -> EnvStepResult:
        """校验并执行一个规范化家庭 ToolCall；finish 不属于本模块。"""
        self._ensure_ready()
        normalized = call if isinstance(call, ToolCall) else ToolCall.from_dict(call)
        started = perf_counter()
        validation = validate_tool_call_shape(normalized, include_finish=False)
        state_diff: dict[str, Any] = {}
        if not validation.valid:
            result = error_envelope(
                validation.code or "BAD_REQUEST",
                validation.message or "invalid tool call",
                self._elapsed_ms(started),
                validation.hint,
            )
        else:
            result, state_diff = self._execute(normalized, started)
        event = ToolEvent(
            call_id=normalized.call_id,
            tool_name=normalized.name,
            arguments=copy_json(normalized.arguments),
            result=copy_json(result),
            state_diff=copy_json(state_diff),
        )
        self._events.append(event.to_dict())
        self._last_policy_result = policy_result_view(result)
        return EnvStepResult(observation=self.observation(), event=event)

    def observation(self) -> dict[str, Any]:
        """返回用户任务、工具 schema 和上次结果，不暴露设备库存或隐藏目标。"""
        self._ensure_ready()
        return {
            "scenario_id": self._scenario.scenario_id,
            "user_request": self._scenario.task.user_request,
            "tools": available_tools(),
            "last_tool_result": copy_json(self._last_policy_result),
        }

    @property
    def runtime_state(self) -> dict[str, dict[str, Any]]:
        """向 C 的 verifier 提供当前状态深拷贝。"""
        self._ensure_ready()
        return self._engine.state

    @property
    def scenario(self) -> Scenario:
        """返回当前静态 Scenario。"""
        self._ensure_ready()
        return self._scenario

    def events(self) -> list[dict[str, Any]]:
        """返回完整工具事件审计记录。"""
        return deepcopy(self._events)

    def snapshot(self) -> dict[str, Any]:
        """保存 B 模块的场景、状态、上次结果和事件。"""
        self._ensure_ready()
        return {
            "scenario": self._scenario.to_dict(),
            "engine": self._engine.snapshot(),
            "last_policy_result": copy_json(self._last_policy_result),
            "events": deepcopy(self._events),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """从 snapshot 恢复一个独立且可继续执行的环境。"""
        scenario = ensure_valid_scenario(snapshot["scenario"])
        if self._scenario is not None and self._scenario.scenario_id != scenario.scenario_id:
            raise ValueError("snapshot scenario does not match current environment")
        self._scenario = scenario
        self._engine = StateEngine(scenario.home)
        self._engine.restore(snapshot["engine"])
        self._last_policy_result = copy_json(snapshot.get("last_policy_result"))
        self._events = deepcopy(snapshot.get("events", []))

    def fork(self) -> "HomeEnv":
        """复制当前环境，保证多条 rollout 的状态互相隔离。"""
        child = HomeEnv()
        child.restore(self.snapshot())
        return child

    def _execute(self, call: ToolCall, started: float) -> tuple[dict[str, Any], dict[str, Any]]:
        """分发四个家庭语义工具并统一成功或失败结果。"""
        if call.name == "observe_home":
            return success_envelope(self._engine.observe_home(), self._elapsed_ms(started)), {}
        if call.name == "inspect_room":
            validation, data = self._engine.inspect_room(str(call.arguments["room_id"]))
        elif call.name == "inspect_device":
            validation, data = self._engine.inspect_device(str(call.arguments["device_id"]))
        else:
            validation, data, state_diff = self._engine.execute_action(
                str(call.arguments["device_id"]),
                str(call.arguments["action"]),
                copy_json(call.arguments["params"]),
            )
            if validation.valid:
                return success_envelope(data or {}, self._elapsed_ms(started)), state_diff
            return (
                error_envelope(
                    validation.code or "SERVICE_ERROR",
                    validation.message or "action execution failed",
                    self._elapsed_ms(started),
                    validation.hint,
                ),
                {},
            )
        if validation.valid:
            return success_envelope(data or {}, self._elapsed_ms(started)), {}
        return (
            error_envelope(
                validation.code or "SERVICE_ERROR",
                validation.message or "tool execution failed",
                self._elapsed_ms(started),
                validation.hint,
            ),
            {},
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        """使用单调时钟计算非负调用耗时。"""
        return max(0.0, (perf_counter() - started) * 1000.0)

    def _ensure_ready(self) -> None:
        """在 reset 前调用环境时给出明确错误。"""
        if self._scenario is None or self._engine is None:
            raise RuntimeError("HomeEnv.reset must be called before use")
