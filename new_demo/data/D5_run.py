"""D5：停闸确认后，把蓝图编成 Scenario，交给 C.run，写入轨迹总表。"""

from __future__ import annotations

from typing import Any

from new_demo.env.B_models import copy_json
from new_demo.eval.C_episode_runner import EpisodeRunner
from new_demo.data.D0_template import normalize_category


def blueprint_to_scenario(blueprint: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    """蓝图六项里 user_request 在顶层；probe 不进 Scenario。"""
    return {
        "scenario_id": scenario_id,
        "blueprint_id": blueprint["blueprint_id"],
        "home": copy_json(blueprint["home"]),
        "user_request": blueprint["user_request"],
        "task": copy_json(blueprint["task"]),
        "episode_config": {"max_turns": 10, "max_tool_calls_per_turn": 1},
    }


def run_one(blueprint: dict[str, Any], policy: Any, scenario_id: str) -> dict[str, Any]:
    """跑一条轨迹。D5 不算 C 标签、不调 D6。"""
    scenario = blueprint_to_scenario(blueprint, scenario_id)
    result = EpisodeRunner(policy).run(scenario)
    code = normalize_category(str(blueprint.get("category", "T1")))
    d6_init = "跳过" if code in {"T1", "T2"} else "待审"
    return {
        "scenario": scenario,
        "record": copy_json(result.record),
        "labels": result.labels.to_dict(),
        "category": code,
        "d6": d6_init,
        "d6_votes": [],
    }
