"""用 V1.2 OraclePolicy 和 EpisodeRunner 生成统一参考计划与轨迹。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeflow_demo.agents.oracle_policy import OraclePolicy
from homeflow_demo.env.models import Scenario, ToolCall
from homeflow_demo.env.schema import ensure_valid_scenario
from homeflow_demo.eval.episode_runner import EpisodeRunner


@dataclass(frozen=True)
class PlanResult:
    """保存 Oracle 的规范 ToolCall 计划及任务可行性标签。"""

    feasible: bool
    calls: tuple[ToolCall, ...]
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """把参考计划转换成可审计字典。"""
        return {
            "feasible": self.feasible,
            "calls": [item.to_dict() for item in self.calls],
            "reason": self.reason,
        }


def plan_scenario(scenario: Scenario | dict[str, Any]) -> PlanResult:
    """构造按房间发现、按设备检查、按 action 执行的 Oracle 计划。"""
    parsed = scenario if isinstance(scenario, Scenario) else ensure_valid_scenario(scenario)
    policy = OraclePolicy(parsed)
    feasible = bool(parsed.metadata.get("feasible", True))
    reason = None if feasible else str(parsed.metadata.get("expected_failure", "infeasible_task"))
    return PlanResult(feasible=feasible, calls=policy.planned_calls, reason=reason)


def run_oracle_episode(scenario: Scenario | dict[str, Any]) -> dict[str, Any]:
    """让 C 驱动 Oracle 与 B 交互并返回 V1.2 标准轨迹记录。"""
    parsed = scenario if isinstance(scenario, Scenario) else ensure_valid_scenario(scenario)
    policy = OraclePolicy(parsed)
    run = EpisodeRunner(policy=policy, model_id="oracle_v1.2").run(parsed)
    record = run.to_dict()
    record["source"] = "oracle"
    record["feasible"] = bool(parsed.metadata.get("feasible", True))
    record["planned_calls"] = [item.to_dict() for item in policy.planned_calls]
    return record
