"""实现不调用外部模型的任务候选静态校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .task_blueprints import TaskBlueprint


@dataclass(frozen=True)
class TaskValidation:
    """保存一个候选请求的程序化校验结果。"""

    accepted: bool
    normalized_text: str
    codes: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换成可以写入 JSONL 的校验记录。"""
        return {
            "accepted": self.accepted,
            "normalized_text": self.normalized_text,
            "codes": list(self.codes),
            "details": dict(self.details),
        }


def validate_task_candidate(
    blueprint: TaskBlueprint,
    candidate: dict[str, Any],
    *,
    seen_texts: dict[str, str] | None = None,
) -> TaskValidation:
    """完成候选 schema、硬泄露和精确去重检查。"""
    codes: list[str] = []
    if not isinstance(candidate, dict):
        return TaskValidation(False, "", ("CANDIDATE_NOT_OBJECT",), {})
    text = candidate.get("text")
    if not isinstance(text, str) or not text.strip():
        return TaskValidation(False, "", ("EMPTY_TEXT",), {})
    extra_fields = sorted(set(candidate) - {"text"})
    if extra_fields:
        codes.append("CANDIDATE_EXTRA_FIELDS")
    normalized = _normalize_text(text)
    if len(normalized) > 300:
        codes.append("TEXT_TOO_LONG")
    hard_tokens = _hard_leak_tokens(blueprint)
    leaked = sorted(token for token in hard_tokens if token and token in text)
    if leaked:
        codes.append("HARD_LEAKAGE")
    if _looks_like_tool_json(text):
        codes.append("TOOL_SCHEMA_LEAKAGE")
    duplicate_of = None
    if seen_texts is not None and normalized in seen_texts:
        duplicate_of = seen_texts[normalized]
        codes.append("EXACT_DUPLICATE")
    details = {"hard_leak_tokens": leaked}
    if extra_fields:
        details["extra_fields"] = extra_fields
    if duplicate_of:
        details["duplicate_of"] = duplicate_of
    return TaskValidation(not codes, normalized, tuple(codes), details)


def register_candidate(
    registry: dict[str, str],
    validation: TaskValidation,
    *,
    scenario_id: str,
) -> None:
    """把通过的候选登记到跨 split 精确去重索引。"""
    if validation.accepted and validation.normalized_text:
        registry.setdefault(validation.normalized_text, scenario_id)


def _normalize_text(text: str) -> str:
    """压缩大小写和空白，供精确重复检查使用。"""
    return re.sub(r"\s+", " ", text.strip().casefold())


def _hard_leak_tokens(blueprint: TaskBlueprint) -> set[str]:
    """收集不应出现在用户语言中的内部标识和动作名。"""
    tokens = {blueprint.blueprint_id}
    for room in blueprint.home.get("rooms", []):
        tokens.add(str(room.get("room_id", "")))
    for device in blueprint.home.get("devices", []):
        tokens.add(str(device.get("device_id", "")))
        for action in device.get("actions", []):
            tokens.add(str(action.get("action", "")))
    for code in blueprint.task.get("expected_finish", {}).get("allowed_reason_codes", []):
        tokens.add(str(code))
    return {token for token in tokens if token}


def _looks_like_tool_json(text: str) -> bool:
    """识别把内部工具调用直接写进用户请求的明显情况。"""
    lowered = text.casefold()
    return any(token in lowered for token in ("device_id", "room_id", '"name"', '"arguments"'))
