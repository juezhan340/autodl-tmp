"""验证 V1 场景、Oracle 轨迹和数据划分的基本契约。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from homeflow_demo.data.trajectory_format import read_jsonl
from homeflow_demo.env import HomeEpisodeEnv
from homeflow_demo.env.schema import ensure_valid_scenario


def validate_v1_dataset(root: str | Path) -> dict[str, Any]:
    """检查 V1 数据文件、场景 ID、Oracle 结果和轨迹可重放性。"""
    base = Path(root)
    all_ids: dict[str, str] = {}
    report: dict[str, Any] = {"root": str(base), "splits": {}, "errors": []}
    for split in ("train", "val", "eval"):
        scenario_path = base / f"scenarios_{split}.jsonl"
        oracle_path = base / f"oracle_trajectories_{split}.jsonl"
        if not scenario_path.exists() or not oracle_path.exists():
            report["errors"].append(f"{split}: required JSONL file is missing")
            report["splits"][split] = {
                "scenario_count": 0,
                "oracle_count": 0,
                "oracle_success_count": 0,
            }
            continue
        scenarios = read_jsonl(scenario_path)
        records = read_jsonl(oracle_path)
        if len(scenarios) != len(records):
            report["errors"].append(f"{split}: scenario/oracle count mismatch")
        success_count = 0
        for scenario, record in zip(scenarios, records):
            parsed = ensure_valid_scenario(scenario)
            scenario_id = parsed.scenario_id
            if scenario.get("metadata", {}).get("split") != split:
                report["errors"].append(f"{scenario_id}: metadata.split mismatch")
            if scenario_id in all_ids:
                report["errors"].append(f"duplicate scenario_id: {scenario_id}")
            all_ids[scenario_id] = split
            if record.get("scenario_id") != scenario_id:
                report["errors"].append(f"{scenario_id}: oracle scenario_id mismatch")
            feasible = bool(scenario.get("metadata", {}).get("feasible", True))
            if bool(record.get("feasible")) != feasible:
                report["errors"].append(f"{scenario_id}: feasible flag mismatch")
            if feasible:
                if record.get("format_version") == "v1.1-turn":
                    _validate_feasible_turn_oracle(parsed.to_dict(), record, report)
                else:
                    _validate_feasible_oracle(parsed.to_dict(), record, report)
            elif record.get("success"):
                report["errors"].append(f"{scenario_id}: infeasible scenario was marked successful")
            if record.get("success"):
                success_count += 1
        report["splits"][split] = {
            "scenario_count": len(scenarios),
            "oracle_count": len(records),
            "oracle_success_count": success_count,
        }

    report["scenario_id_count"] = len(all_ids)
    report["valid"] = not report["errors"]
    return report


def _validate_feasible_oracle(
    scenario: dict[str, Any], record: dict[str, Any], report: dict[str, Any]
) -> None:
    """重放可行 Oracle 轨迹，确认保存的数据确实由 HomeEnv 判定成功。"""
    scenario_id = str(scenario["scenario_id"])
    if not record.get("success"):
        report["errors"].append(f"{scenario_id}: feasible scenario oracle failed")
        return
    actions = record.get("actions", [])
    if not actions or actions[-1].get("name") != "finish":
        report["errors"].append(f"{scenario_id}: successful oracle must end with finish")
        return
    env = HomeEpisodeEnv()
    env.reset(scenario)
    replayed_steps = 0
    for action in actions:
        result = env.step(action)
        replayed_steps += 1
        if result.terminated or result.truncated:
            break
    final = env.final_result()
    if replayed_steps != len(actions):
        report["errors"].append(f"{scenario_id}: oracle contains actions after episode end")
    if not final.success:
        report["errors"].append(f"{scenario_id}: oracle replay did not succeed")
    saved_final = record.get("final_result", {})
    if saved_final.get("completion") != final.completion:
        report["errors"].append(f"{scenario_id}: saved completion differs from replay")
    if saved_final.get("steps") != final.steps:
        report["errors"].append(f"{scenario_id}: saved step count differs from replay")


def _validate_feasible_turn_oracle(
    scenario: dict[str, Any], record: dict[str, Any], report: dict[str, Any]
) -> None:
    """重放 V1.1 turn 轨迹，确认模型决策步和环境结果一一对应。"""
    scenario_id = str(scenario["scenario_id"])
    turns = record.get("turns", [])
    if not isinstance(turns, list) or not turns:
        report["errors"].append(f"{scenario_id}: v1.1 record must contain turns")
        return
    env = HomeEpisodeEnv()
    env.reset(scenario)
    for expected_index, turn in enumerate(turns, start=1):
        if turn.get("turn_index") != expected_index:
            report["errors"].append(f"{scenario_id}: turn_index is not contiguous")
        if "assistant_output" not in turn:
            report["errors"].append(f"{scenario_id}: turn is missing assistant_output")
            continue
        result = env.step(turn["assistant_output"])
        if len(turn.get("tool_events", [])) < 1:
            report["errors"].append(f"{scenario_id}: turn has no tool_events")
        if result.terminated or result.truncated:
            break
    final = env.final_result()
    saved_final = record.get("final_result", {})
    if not final.success:
        report["errors"].append(f"{scenario_id}: v1.1 oracle replay did not succeed")
    if saved_final.get("completion") != final.completion:
        report["errors"].append(f"{scenario_id}: saved completion differs from turn replay")
    if saved_final.get("turns", saved_final.get("steps")) != final.turns:
        report["errors"].append(f"{scenario_id}: saved turn count differs from replay")


def main() -> None:
    """解析命令行参数并打印 V1 数据验证结果。"""
    parser = argparse.ArgumentParser(description="Validate HomeFlow V1 dataset")
    parser.add_argument("--root", default="homeflow_demo/data_processed/v1", help="V1 数据目录")
    args = parser.parse_args()
    print(json.dumps(validate_v1_dataset(args.root), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
