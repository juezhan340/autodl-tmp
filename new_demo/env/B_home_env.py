"""B 模块：只执行四个家庭工具，不处理 finish，不算成功。"""

from __future__ import annotations

from typing import Any

from .B_models import EnvStepResult, Scenario, ToolCall, ToolEvent, copy_json
from .B_schema import ensure_valid_scenario
from .B_state_engine import StateEngine
from .B_tool_schema import (
    available_tools,
    error_envelope,
    policy_result_view,
    success_envelope,
    validate_tool_call_shape,
)


class HomeEnv:
    """接收规范化 ToolCall，维护家庭运行状态。"""

    def __init__(self) -> None:
        """创建尚未加载 Scenario 的空环境。"""
        self._scenario: Scenario | None = None
        self._engine: StateEngine | None = None
        self._last_policy_result: dict[str, Any] | None = None

    def reset(self, scenario: Scenario | dict[str, Any]) -> dict[str, Any]:
        """校验并复制 home，返回不含隐藏任务的初始 observation。"""
        self._scenario = ensure_valid_scenario(scenario)
        self._engine = StateEngine(self._scenario.home)
        self._last_policy_result = None
        return self.observation()

    def step(self, call: ToolCall | dict[str, Any]) -> EnvStepResult:
        """执行一个家庭工具；finish 不是本模块的 name。"""
        self._ensure_ready()
        normalized = call if isinstance(call, ToolCall) else ToolCall.from_dict(call)
        validation = validate_tool_call_shape(normalized, include_finish=False)
        state_diff: dict[str, Any] = {}
        if not validation.valid:
            result = error_envelope(
                validation.code or "BAD_REQUEST",
                validation.message or "invalid tool call",
                validation.hint,
            )
        else:
            result, state_diff = self._execute(normalized)
        event = ToolEvent(
            call_id=normalized.call_id,
            tool_name=normalized.name,
            arguments=copy_json(normalized.arguments),
            result=copy_json(result),
            state_diff=copy_json(state_diff),
        )
        self._last_policy_result = policy_result_view(result)
        return EnvStepResult(observation=self.observation(), event=event)

    def observation(self) -> dict[str, Any]:
        """给 A 看：用户话、工具 schema、上次结果；无 task、无设备库存。"""
        self._ensure_ready()
        return {
            "scenario_id": self._scenario.scenario_id,
            "user_request": self._scenario.user_request,
            "tools": available_tools(),
            "last_tool_result": copy_json(self._last_policy_result),
        }

    @property
    def runtime_state(self) -> dict[str, dict[str, Any]]:
        """给 final_state 和 C-2，不含 actions。"""
        self._ensure_ready()
        return self._engine.state

    @property
    def scenario(self) -> Scenario:
        """返回当前静态 Scenario。"""
        self._ensure_ready()
        return self._scenario

    def _execute(self, call: ToolCall) -> tuple[dict[str, Any], dict[str, Any]]:
        """按 name 路由到四个家庭工具。"""
        if call.name == "observe_home":
            return success_envelope(self._engine.observe_home()), {}
        if call.name == "inspect_room":
            validation, data = self._engine.inspect_room(str(call.arguments["room_id"]))
            if validation.valid:
                return success_envelope(data or {}), {}
            return error_envelope(
                validation.code or "SERVICE_ERROR",
                validation.message or "tool execution failed",
                validation.hint,
            ), {}
        if call.name == "inspect_device":
            validation, data = self._engine.inspect_device(str(call.arguments["device_id"]))
            if validation.valid:
                return success_envelope(data or {}), {}
            return error_envelope(
                validation.code or "SERVICE_ERROR",
                validation.message or "tool execution failed",
                validation.hint,
            ), {}
        validation, data, state_diff = self._engine.execute_action(
            str(call.arguments["device_id"]),
            str(call.arguments["action"]),
            copy_json(call.arguments["params"]),
        )
        if validation.valid:
            return success_envelope(data or {}), state_diff
        return (
            error_envelope(
                validation.code or "SERVICE_ERROR",
                validation.message or "action execution failed",
                validation.hint,
            ),
            {},
        )

    def _ensure_ready(self) -> None:
        """reset 之前调用环境就报错。"""
        if self._scenario is None or self._engine is None:
            raise RuntimeError("HomeEnv.reset must be called before use")
