"""提供按房间发现流程工作的确定性 V1.2 Oracle 策略。"""

from __future__ import annotations

from typing import Any

from homeflow_demo.env.models import Scenario, ToolCall
from homeflow_demo.env.schema import ensure_valid_scenario


class OraclePolicy:
    """根据已验证的 Scenario 逐步发现设备并产生规范工具调用。"""

    def __init__(self, scenario: Scenario | dict[str, Any]) -> None:
        """保存 Oracle 的参考任务，并生成只供 Oracle 使用的计划。"""
        self.scenario = ensure_valid_scenario(scenario)
        self._calls = self._build_plan()
        self._cursor = 0

    def respond(self, context: dict[str, Any]) -> dict[str, Any]:
        """按每回合一个工具调用输出 OpenAI function-call 兼容消息。"""
        if self._cursor >= len(self._calls):
            call = ToolCall("finish", {"summary": "参考计划已完成。"}, f"oracle_{self._cursor}")
        else:
            call = self._calls[self._cursor]
        self._cursor += 1
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
            ],
        }

    @property
    def planned_calls(self) -> tuple[ToolCall, ...]:
        """暴露只读参考调用序列，供数据构建和轨迹审计使用。"""
        return tuple(self._calls)

    def _build_plan(self) -> list[ToolCall]:
        """生成先看全局、再查房间和设备、最后执行的可重放计划。"""
        calls: list[ToolCall] = []
        targets = list(self.scenario.task.conditions)
        infeasible_sensor_target = self._sensor_target()
        context_device_ids = [
            str(item) for item in self.scenario.metadata.get("context_device_ids", [])
        ]
        target_device_ids = list(
            dict.fromkeys(context_device_ids + [item.device_id for item in targets])
        )
        if infeasible_sensor_target and infeasible_sensor_target[0] not in target_device_ids:
            target_device_ids.append(infeasible_sensor_target[0])

        calls.append(self._call("observe_home", {}, 0))
        if self.scenario.metadata.get("task_kind") == "missing_device":
            room_id = str(self.scenario.metadata.get("target_room_id", ""))
            if room_id:
                calls.append(self._call("inspect_room", {"room_id": room_id}, len(calls)))
        for device_id in target_device_ids:
            device = self.scenario.home.devices[device_id]
            if not any(call.name == "inspect_room" and call.arguments.get("room_id") == device.room_id for call in calls):
                calls.append(self._call("inspect_room", {"room_id": device.room_id}, len(calls)))
            calls.append(self._call("inspect_device", {"device_id": device_id}, len(calls)))

        if infeasible_sensor_target:
            device_id, field, value = infeasible_sensor_target
            action, params = _action_for_target(field, value, sensor=True)
            calls.append(
                self._call(
                    "execute_action",
                    {"device_id": device_id, "action": action, "params": params},
                    len(calls),
                )
            )
        else:
            for condition in targets:
                device = self.scenario.home.devices[condition.device_id]
                current = device.state.get(condition.field)
                if condition.operator == "eq" and current == condition.value:
                    continue
                action, params = _action_for_target(condition.field, condition.value)
                if action not in {item.action for item in device.actions}:
                    continue
                calls.append(
                    self._call(
                        "execute_action",
                        {"device_id": condition.device_id, "action": action, "params": params},
                        len(calls),
                    )
                )
        calls.append(self._call("finish", {"summary": "已按房间和设备信息完成可执行目标。"}, len(calls)))
        return calls

    def _sensor_target(self) -> tuple[str, str, Any] | None:
        """找出不可行任务中要求写入只读传感器的目标。"""
        for condition in self.scenario.task.conditions:
            device = self.scenario.home.devices[condition.device_id]
            if device.kind == "sensor":
                return condition.device_id, condition.field, condition.value
        return None

    @staticmethod
    def _call(name: str, arguments: dict[str, Any], index: int) -> ToolCall:
        """生成可追踪且确定的 Oracle call_id。"""
        return ToolCall(name, arguments, f"oracle_call_{index:03d}")


def _action_for_target(
    field: str,
    value: Any,
    *,
    sensor: bool = False,
) -> tuple[str, dict[str, Any]]:
    """把状态目标映射到统一 action 和参数。"""
    if sensor:
        if field == "temperature":
            return "set_temperature", {"value": value}
        if field == "humidity":
            return "set_percentage", {"value": value}
        return "turn_on", {}
    if field == "on":
        return ("turn_on" if value else "turn_off"), {}
    if field == "target":
        return "set_temperature", {"value": value}
    if field == "mode":
        return "set_mode", {"mode": value}
    if field == "level":
        return "set_percentage", {"value": value}
    raise ValueError(f"Oracle has no action mapping for target field: {field}")
