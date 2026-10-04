"""只读总表，标签全过的复制进数据集。不改总表。"""

from __future__ import annotations

import json
import time
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
    _write_text_retry(
        processed / "D_dataset.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept),
    )
    _write_text_retry(
        processed / "D_manifest.json",
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
    )
    return stats


def _write_text_retry(path: Path, text: str) -> None:
    """写文本文件；Windows 高频重写同一路径偶发 OSError(EINVAL)，重试 6 次。"""
    last: OSError | None = None
    for index in range(6):
        try:
            path.write_text(text, encoding="utf-8")
            return
        except OSError as exc:
            last = exc
            time.sleep(0.2 * (index + 1))
    assert last is not None
    raise last
