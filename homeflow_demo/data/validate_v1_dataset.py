"""对冻结的 V1 历史 JSONL 做只读文件级完整性检查。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from homeflow_demo.data.trajectory_format import read_jsonl


DEFAULT_V1_ROOT = Path(__file__).resolve().parents[1] / "data_processed" / "v1"


def validate_v1_dataset(root: str | Path = DEFAULT_V1_ROOT) -> dict[str, Any]:
    """只检查历史文件存在、JSONL 可读、数量对应和 ID 对齐。"""
    base = Path(root)
    report: dict[str, Any] = {"root": str(base), "splits": {}, "errors": []}
    all_ids: set[str] = set()
    for split in ("train", "val", "eval"):
        scenario_path = base / f"scenarios_{split}.jsonl"
        oracle_path = base / f"oracle_trajectories_{split}.jsonl"
        if not scenario_path.exists() or not oracle_path.exists():
            report["errors"].append(f"{split}: required historical file is missing")
            continue
        scenarios = read_jsonl(scenario_path)
        records = read_jsonl(oracle_path)
        if len(scenarios) != len(records):
            report["errors"].append(f"{split}: scenario/oracle count mismatch")
        aligned = 0
        for scenario, record in zip(scenarios, records):
            scenario_id = scenario.get("scenario_id")
            if not isinstance(scenario_id, str) or not scenario_id:
                report["errors"].append(f"{split}: scenario_id is missing")
                continue
            if scenario_id in all_ids:
                report["errors"].append(f"duplicate historical scenario_id: {scenario_id}")
            all_ids.add(scenario_id)
            if record.get("scenario_id") == scenario_id:
                aligned += 1
            else:
                report["errors"].append(f"{scenario_id}: oracle ID mismatch")
        report["splits"][split] = {
            "scenario_count": len(scenarios),
            "oracle_count": len(records),
            "aligned_count": aligned,
        }
    report["scenario_id_count"] = len(all_ids)
    report["valid"] = not report["errors"]
    return report


def main() -> None:
    """解析历史目录并打印只读完整性报告。"""
    parser = argparse.ArgumentParser(description="Inspect archived HomeFlow V1 data")
    parser.add_argument("--root", default=str(DEFAULT_V1_ROOT), help="冻结的 V1 数据目录")
    args = parser.parse_args()
    print(json.dumps(validate_v1_dataset(args.root), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
