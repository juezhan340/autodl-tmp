"""批量生成 V1 场景、Oracle 轨迹和数据清单。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from homeflow_demo.data.planner import run_oracle_episode
from homeflow_demo.data.scenario_generator import ScenarioGenerator
from homeflow_demo.data.trajectory_format import write_jsonl
from homeflow_demo.env.schema import ensure_valid_scenario


def build_v1_dataset(output_dir: str | Path, seed: int = 20260921) -> dict[str, Any]:
    """生成 V1 三个 split 的场景、Oracle 轨迹和统计 manifest。"""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    generator = ScenarioGenerator(seed=seed)
    split_counts = {"train": 80, "val": 20, "eval": 40}
    stats: dict[str, Any] = {
        "seed": seed,
        "format_version": "v1.1-turn",
        "splits": {},
        "files": {},
    }

    for split, count in split_counts.items():
        scenarios = generator.generate(count, split)
        for scenario in scenarios:
            ensure_valid_scenario(scenario)
        scenario_path = root / f"scenarios_{split}.jsonl"
        write_jsonl(scenario_path, scenarios)
        oracle_records = [run_oracle_episode(scenario) for scenario in scenarios]
        oracle_path = root / f"oracle_trajectories_{split}.jsonl"
        write_jsonl(oracle_path, oracle_records)
        stats["splits"][split] = _split_stats(scenarios, oracle_records)
        stats["files"][split] = {
            "scenarios": str(scenario_path),
            "oracle_trajectories": str(oracle_path),
        }

    manifest_path = root / "manifest.json"
    stats["files"]["manifest"] = str(manifest_path)
    manifest_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return stats


def _split_stats(scenarios: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    """计算一个 split 的结构校验和 Oracle 成功统计。"""
    feasible = sum(bool(item.get("metadata", {}).get("feasible", True)) for item in scenarios)
    oracle_success = sum(bool(record["success"]) for record in records)
    task_kinds = sorted({item["metadata"]["task_kind"] for item in scenarios})
    return {
        "scenario_count": len(scenarios),
        "feasible_count": feasible,
        "infeasible_count": len(scenarios) - feasible,
        "oracle_success_count": oracle_success,
        "oracle_success_rate_over_all": oracle_success / len(scenarios) if scenarios else 0.0,
        "task_kinds": task_kinds,
        "unique_scenario_ids": len({item["scenario_id"] for item in scenarios}),
    }


def main() -> None:
    """解析命令行参数并生成 V1 数据。"""
    parser = argparse.ArgumentParser(description="Build HomeFlow V1 local dataset")
    parser.add_argument("--output-dir", default="homeflow_demo/data_processed/v1", help="V1 数据输出目录")
    parser.add_argument("--seed", type=int, default=20260921, help="场景生成随机种子")
    args = parser.parse_args()
    stats = build_v1_dataset(args.output_dir, seed=args.seed)
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
