"""定义 V1.2 轨迹记录与稳定 JSONL 序列化工具。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class TrajectoryRecord:
    """保存一条 C 模块输出的 V1.2 turn-level 轨迹。"""

    scenario_id: str
    model_id: str
    source: str
    feasible: bool
    turns: list[dict[str, Any]]
    final_state: dict[str, Any]
    evaluation: dict[str, Any]
    metadata: dict[str, Any]
    reset_info: dict[str, Any] = field(default_factory=dict)
    format_version: str = "v1.2-turn"

    def to_dict(self) -> dict[str, Any]:
        """转换为可直接写入 JSONL 的字典。"""
        return asdict(self)


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """以 UTF-8 JSONL 稳定写入记录并返回条数。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """读取 JSONL 并在错误中保留文件和行号。"""
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL record must be an object at {path}:{line_number}")
            records.append(record)
    return records


def stable_fingerprint(record: dict[str, Any]) -> str:
    """忽略运行耗时后计算稳定 SHA-256，用于数据清单和重复检测。"""
    payload = json.dumps(
        _without_runtime_diagnostics(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _without_runtime_diagnostics(value: Any) -> Any:
    """递归移除不可复现的 elapsed_ms，保留其他语义字段。"""
    if isinstance(value, dict):
        return {
            str(key): _without_runtime_diagnostics(item)
            for key, item in value.items()
            if key != "elapsed_ms"
        }
    if isinstance(value, list):
        return [_without_runtime_diagnostics(item) for item in value]
    return value
