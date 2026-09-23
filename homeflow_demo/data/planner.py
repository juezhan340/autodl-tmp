"""为 V1 场景生成可验证的规则 Oracle 动作序列。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeflow_demo.env import Action, HomeEpisodeEnv
from homeflow_demo.env.models import Scenario
from homeflow_demo.env.schema import ensure_valid_scenario


@dataclass
class PlanResult:
    """保存规则规划器的可行性判断和动作序列。"""

    feasible: bool
    actions: list[Action]
    reason: str | None = None


def plan_scenario(scenario: Scenario | dict[str, Any]) -> PlanResult:
    """根据目标谓词生成有限设备范围内的规则动作计划。"""
    parsed = scenario if isinstance(scenario, Scenario) else ensure_valid_scenario(scenario)
    devices = {device["id"]: device for device in parsed.devices}
    actions: list[Action] = []
    if parsed.metadata.get("requires_query") and parsed.predicates:
        first = parsed.predicates[0]
        actions.append(Action("query_device", {"device_id": first.device_id, "fields": [first.field]}))

    for predicate in parsed.predicates:
        device = devices[predicate.device_id]
        current = device["state"].get(predicate.field)
        if current == predicate.equals:
            continue
        command = _field_to_command(device["type"], predicate.field)
        if command is None or not _value_is_allowed(command, predicate.equals):
            return PlanResult(False, [], f"unrepresentable goal: {predicate.device_id}.{predicate.field}={predicate.equals}")
        actions.append(Action("control_device", {
            "device_id": predicate.device_id,
            "command": command,
            "value": predicate.equals,
        }))

    if not actions:
        actions.append(Action("query_device", {"device_id": parsed.devices[0]["id"], "fields": []}))
    actions.append(Action("finish", {"summary": "规则规划器完成目标。"}))
    return PlanResult(True, actions)


def run_oracle_episode(scenario: Scenario | dict[str, Any]) -> dict[str, Any]:
    """执行规则计划并返回统一的 Oracle 轨迹记录。"""
    parsed = scenario if isinstance(scenario, Scenario) else ensure_valid_scenario(scenario)
    plan = plan_scenario(parsed)
    if not plan.feasible:
        return {
            "format_version": "v1.1-turn",
            "scenario_id": parsed.scenario_id,
            "source": "planner",
            "feasible": False,
            "success": False,
            "actions": [],
            "turns": [],
            "transitions": [],
            "final_result": {
                "scenario_id": parsed.scenario_id,
                "success": False,
                "completion": 0.0,
                "turns": 0,
                "steps": 0,
                "terminated": False,
                "truncated": False,
                "failure_reason": plan.reason,
                "final_state": {},
            },
            "metadata": parsed.metadata,
        }

    env = HomeEpisodeEnv()
    env.reset(parsed)
    transitions: list[dict[str, Any]] = []
    for action in plan.actions:
        result = env.step(action)
        transitions.append({
            "observation": result.observation,
            "reward": result.reward,
            "terminated": result.terminated,
            "truncated": result.truncated,
            "info": result.info,
        })
        if result.terminated or result.truncated:
            break
    final = env.final_result()
    turns = env.trajectory()
    return {
        "format_version": "v1.1-turn",
        "scenario_id": parsed.scenario_id,
        "source": "planner",
        "feasible": bool(parsed.metadata.get("feasible", True)),
        "success": final.success,
        "actions": [{"name": action.name, "arguments": action.arguments} for action in plan.actions],
        # transitions 保留为兼容字段，新的训练和 RL 代码只读取 turns。
        "transitions": transitions,
        "turns": turns,
        "final_result": {
            "scenario_id": final.scenario_id,
            "success": final.success,
            "completion": final.completion,
            "turns": final.turns,
            "steps": final.steps,
            "terminated": final.terminated,
            "truncated": final.truncated,
            "failure_reason": final.failure_reason,
            "final_state": final.final_state,
        },
        "metadata": parsed.metadata,
    }


def _field_to_command(device_type: str, field: str) -> str | None:
    """把目标字段映射为设备可执行的控制命令。"""
    return {
        ("light", "power"): "set_power",
        ("light", "brightness"): "set_brightness",
        ("light", "color_temp"): "set_color_temp",
        ("thermostat", "power"): "set_power",
        ("thermostat", "temperature"): "set_temperature",
        ("thermostat", "mode"): "set_mode",
        ("switch", "power"): "set_power",
        ("lock", "locked"): "set_locked",
    }.get((device_type, field))


def _value_is_allowed(command: str, value: Any) -> bool:
    """复用 V1 工具值域规则，判断 Oracle 是否能表达目标。"""
    if command == "set_power":
        return value in {"on", "off"}
    if command == "set_brightness":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100
    if command == "set_color_temp":
        return isinstance(value, int) and not isinstance(value, bool) and 1500 <= value <= 9000
    if command == "set_temperature":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and 16 <= value <= 30
    if command == "set_mode":
        return value in {"cool", "heat", "auto", "off"}
    if command == "set_locked":
        return isinstance(value, bool)
    return False
