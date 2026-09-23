"""定义 V1 轨迹记录和 JSONL 序列化格式。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class TrajectoryRecord:
    """保存一条按 assistant turn 组织的 HomeEnv 完整轨迹。"""

    scenario_id: str
    source: str
    feasible: bool
    success: bool
    actions: list[dict[str, Any]]
    transitions: list[dict[str, Any]]
    final_result: dict[str, Any]
    metadata: dict[str, Any]
    format_version: str = "v1.1-turn"
    turns: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_events(self) -> list[dict[str, Any]]:
        """返回轨迹中所有 turn 内工具事件的扁平视图。"""
        return [event for turn in self.turns for event in turn.get("tool_events", [])]

    def to_dict(self) -> dict[str, Any]:
        """转换成可以直接写入 JSONL 的字典。"""
        return asdict(self)


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """以 UTF-8 JSONL 写入记录并返回写入条数。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件并返回字典列表。"""
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
    return records
