"""全量验证 V1.2 场景、Oracle 轨迹、数据隔离和确定性重放。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from homeflow_demo.data.build_v1_2_dataset import DEFAULT_OUTPUT_DIR, SPLIT_COUNTS
from homeflow_demo.data.planner import run_oracle_episode
from homeflow_demo.data.scenario_generator import TASK_KINDS
from homeflow_demo.data.trajectory_format import read_jsonl
from homeflow_demo.env.schema import ensure_valid_scenario
from homeflow_demo.eval.trajectory_quality import replay_trajectory


def validate_v1_2_dataset(root: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """检查所有文件、场景、轨迹、split 隔离和重复执行一致性。"""
    base = Path(root)
    report: dict[str, Any] = {"root": str(base), "splits": {}, "errors": []}
    all_ids: dict[str, str] = {}
    for split, expected_count in SPLIT_COUNTS.items():
        scenario_path = base / f"scenarios_{split}.jsonl"
        oracle_path = base / f"oracle_trajectories_{split}.jsonl"
        if not scenario_path.exists() or not oracle_path.exists():
            report["errors"].append(f"{split}: required JSONL file is missing")
            continue
        scenarios = read_jsonl(scenario_path)
        records = read_jsonl(oracle_path)
        if len(scenarios) != expected_count:
            report["errors"].append(
                f"{split}: expected {expected_count} scenarios, got {len(scenarios)}"
            )
        if len(records) != len(scenarios):
            report["errors"].append(f"{split}: scenario/oracle count mismatch")
        task_kinds: set[str] = set()
        replay_count = 0
        deterministic_count = 0
        for scenario_data, record in zip(scenarios, records):
            scenario = ensure_valid_scenario(scenario_data)
            scenario_id = scenario.scenario_id
            task_kind = str(scenario.metadata.get("task_kind"))
            task_kinds.add(task_kind)
            if scenario.metadata.get("split") != split:
                report["errors"].append(f"{scenario_id}: metadata.split mismatch")
            if scenario_id in all_ids:
                report["errors"].append(
                    f"{scenario_id}: duplicate across {all_ids[scenario_id]} and {split}"
                )
            all_ids[scenario_id] = split
            if record.get("scenario_id") != scenario_id:
                report["errors"].append(f"{scenario_id}: oracle scenario_id mismatch")
                continue
            if record.get("format_version") != "v1.2-turn":
                report["errors"].append(f"{scenario_id}: format_version mismatch")
            if replay_trajectory(scenario, record):
                replay_count += 1
            else:
                report["errors"].append(f"{scenario_id}: trajectory replay mismatch")
            rerun = run_oracle_episode(scenario)
            if rerun.get("evaluation") == record.get("evaluation") and rerun.get("final_state") == record.get("final_state"):
                deterministic_count += 1
            else:
                report["errors"].append(f"{scenario_id}: repeated run differs")
            _validate_evaluation_contract(scenario_data, record, report["errors"])
        missing_kinds = sorted(set(TASK_KINDS) - task_kinds)
        if missing_kinds:
            report["errors"].append(f"{split}: missing task kinds {missing_kinds}")
        report["splits"][split] = {
            "scenario_count": len(scenarios),
            "oracle_count": len(records),
            "task_kind_count": len(task_kinds),
            "replay_count": replay_count,
            "deterministic_count": deterministic_count,
        }
    report["scenario_id_count"] = len(all_ids)
    report["valid"] = not report["errors"]
    return report


def _validate_evaluation_contract(
    scenario: dict[str, Any],
    record: dict[str, Any],
    errors: list[str],
) -> None:
    """确认可行任务被接收、不可行任务被拒绝且错误归因符合类型。"""
    scenario_id = str(scenario["scenario_id"])
    evaluation = record.get("evaluation")
    if not isinstance(evaluation, dict):
        errors.append(f"{scenario_id}: evaluation is missing")
        return
    feasible = bool(scenario["metadata"].get("feasible", True))
    if feasible:
        if not evaluation.get("success") or not evaluation.get("accepted_for_sft"):
            errors.append(f"{scenario_id}: feasible Oracle trajectory was not accepted")
        if not evaluation.get("trajectory_replayable"):
            errors.append(f"{scenario_id}: accepted trajectory lacks quality replay flag")
    else:
        if evaluation.get("success") or evaluation.get("accepted_for_sft"):
            errors.append(f"{scenario_id}: infeasible trajectory was accepted")
        if not evaluation.get("rejection_reasons"):
            errors.append(f"{scenario_id}: rejected trajectory has no reason")
    if scenario["metadata"].get("task_kind") == "sensor_readonly":
        if evaluation.get("strategy_error_count") != 1:
            errors.append(f"{scenario_id}: sensor readonly error was not classified")


def main() -> None:
    """解析命令行参数并打印全量验证报告。"""
    parser = argparse.ArgumentParser(description="Validate HomeFlow V1.2 dataset")
    parser.add_argument("--root", default=str(DEFAULT_OUTPUT_DIR), help="V1.2 数据目录")
    args = parser.parse_args()
    report = validate_v1_2_dataset(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
