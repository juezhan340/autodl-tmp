"""只读总表，标签全过的复制进数据集。不改总表。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def copy_success(trajectories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """C 四步全 true，且 D6 为 对 或 跳过。"""
    kept: list[dict[str, Any]] = []
    for row in trajectories:
        labels = row.get("labels") or {}
        if not all(labels.get(key) is True for key in ("C-1", "C-2", "C-3", "C-4")):
            continue
        d6 = row.get("d6")
        if d6 in {"对", "跳过"}:
            kept.append(row)
    stats = {
        "total": len(trajectories),
        "copied": len(kept),
        "left_in_table": len(trajectories),
    }
    return kept, stats


def write_dataset(
    trajectories: list[dict[str, Any]],
    output_dir: str | Path,
) -> dict[str, int]:
    """写入 D_dataset.jsonl 和 D_manifest.json。总表文件不在这里改。"""
    kept, stats = copy_success(trajectories)
    root = Path(output_dir)
    processed = root / "data_processed"
    processed.mkdir(parents=True, exist_ok=True)
    with (processed / "D_dataset.jsonl").open("w", encoding="utf-8") as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (processed / "D_manifest.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return stats
