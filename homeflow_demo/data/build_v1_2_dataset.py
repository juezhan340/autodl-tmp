"""构建 V1.2 场景、Oracle 轨迹和可审计数据清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from homeflow_demo.data.planner import run_oracle_episode
from homeflow_demo.data.scenario_generator import TASK_KINDS, ScenarioGenerator
from homeflow_demo.data.trajectory_format import stable_fingerprint, write_jsonl
from homeflow_demo.eval.metrics import summarize_episode_records


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data_processed" / "v1.2"
DEFAULT_GENERATED_ON = "2026-09-23"
SPLIT_COUNTS = {"train": 80, "val": 20, "eval": 40}


def build_v1_2_dataset(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    seed: int = 20260924,
    generated_on: str = DEFAULT_GENERATED_ON,
) -> dict[str, Any]:
    """生成三个 split，并保存场景、Oracle 轨迹、统计和数据指纹。"""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    generator = ScenarioGenerator(seed=seed)
    manifest: dict[str, Any] = {
        "dataset_version": "v1.2",
        "format_version": "v1.2-turn",
        "generated_on": generated_on,
        "seed": seed,
        "reward_version": "v1.2-initial",
        "split_counts": dict(SPLIT_COUNTS),
        "task_kinds": list(TASK_KINDS),
        "splits": {},
        "files": {},
    }
    fingerprints: list[str] = []

    for split, count in SPLIT_COUNTS.items():
        scenarios = generator.generate(count, split)
        records = [run_oracle_episode(scenario) for scenario in scenarios]
        scenario_name = f"scenarios_{split}.jsonl"
        oracle_name = f"oracle_trajectories_{split}.jsonl"
        write_jsonl(root / scenario_name, scenarios)
        write_jsonl(root / oracle_name, records)
        manifest["files"][split] = {
            "scenarios": scenario_name,
            "oracle_trajectories": oracle_name,
        }
        manifest["splits"][split] = _split_stats(scenarios, records)
        fingerprints.extend(stable_fingerprint(item) for item in scenarios)
        fingerprints.extend(stable_fingerprint(item) for item in records)

    manifest["dataset_fingerprint"] = _aggregate_fingerprint(fingerprints)
    manifest["files"]["manifest"] = "manifest.json"
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.md").write_text(_manifest_markdown(manifest), encoding="utf-8")
    return manifest


def _split_stats(
    scenarios: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """汇总一个 split 的任务覆盖、可行性和统一 episode 指标。"""
    task_counts: dict[str, int] = {}
    for scenario in scenarios:
        task_kind = str(scenario["metadata"]["task_kind"])
        task_counts[task_kind] = task_counts.get(task_kind, 0) + 1
    feasible_count = sum(bool(item["metadata"].get("feasible", True)) for item in scenarios)
    return {
        "scenario_count": len(scenarios),
        "feasible_count": feasible_count,
        "infeasible_count": len(scenarios) - feasible_count,
        "unique_scenario_ids": len({item["scenario_id"] for item in scenarios}),
        "task_kind_counts": dict(sorted(task_counts.items())),
        "oracle_metrics": summarize_episode_records(records),
    }


def _aggregate_fingerprint(fingerprints: list[str]) -> str:
    """按文件写入顺序合并记录指纹，得到整个数据集的稳定摘要。"""
    return hashlib.sha256("\n".join(fingerprints).encode("utf-8")).hexdigest()


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    """生成人类可读的 manifest.json 同名中文说明。"""
    split_lines = []
    for split in ("train", "val", "eval"):
        stats = manifest["splits"][split]
        metrics = stats["oracle_metrics"]
        split_lines.append(
            f"{split}: {stats['scenario_count']} 条，"
            f"Oracle 成功 {metrics['success_count']} 条，"
            f"SFT 接收 {metrics['accepted_for_sft_count']} 条"
        )
    summary = "\n".join(split_lines)
    return (
        "# `data_processed/v1.2/manifest.json` 说明\n\n"
        "该文件记录 V1.2 场景与 Oracle 轨迹的版本、规模、任务覆盖、统一评测统计和稳定指纹。\n\n"
        "```text\n"
        f"dataset_version: {manifest['dataset_version']}\n"
        f"format_version:  {manifest['format_version']}\n"
        f"seed:            {manifest['seed']}\n"
        f"{summary}\n"
        f"dataset_fingerprint: {manifest['dataset_fingerprint']}\n"
        "```\n\n"
        "场景文件是静态输入；Oracle 文件是由 C 驱动 A/B 后得到的完整 turn-level 轨迹。"
        "不可行任务保留为 rejected 轨迹，不进入 SFT。\n"
    )


def main() -> None:
    """解析命令行参数并构建 V1.2 数据。"""
    parser = argparse.ArgumentParser(description="Build HomeFlow V1.2 dataset")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="V1.2 数据输出目录")
    parser.add_argument("--seed", type=int, default=20260924, help="场景生成 seed")
    parser.add_argument(
        "--generated-on",
        default=DEFAULT_GENERATED_ON,
        help="manifest 生成日期，默认使用当前 V1.2 交付日期",
    )
    args = parser.parse_args()
    result = build_v1_2_dataset(args.output_dir, args.seed, args.generated_on)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
