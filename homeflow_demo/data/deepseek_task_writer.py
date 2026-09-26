"""调用 DeepSeek 把程序化任务蓝图改写成自然用户请求。"""

from __future__ import annotations

import concurrent.futures
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from homeflow_demo.agents.deepseek_client import DeepSeekAPIError, DeepSeekClient

from .task_blueprints import TaskBlueprint


TASK_WRITER_SYSTEM = """你是 HomeFlow 数据生成流水线的任务改写器。
只返回 JSON，不要 markdown，不要解释，不要 emoji。
JSON 格式必须是 {\"candidates\":[{\"text\":\"...\"},{\"text\":\"...\"},{\"text\":\"...\"}]}。
输入中的 category 只用于理解任务语义，不要在候选中输出 category；每个候选对象只能包含 text 字段。
每个候选只写用户自然语言请求，不写工具调用，不写 room_id、device_id、action 名、reason_code。
候选必须覆盖输入语义目标，不得增加输入没有的设备或动作目标。
同一个结论只表达一次，语言简洁，适合真实家庭用户。
"""


@dataclass(frozen=True)
class TaskWriterResult:
    """保存一个 Blueprint 的自然语言候选和 API 状态。"""

    blueprint_id: str
    candidates: tuple[dict[str, Any], ...]
    request_id: str
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSONL 可写记录。"""
        return {
            "blueprint_id": self.blueprint_id,
            "candidates": [dict(item) for item in self.candidates],
            "request_id": self.request_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class DeepSeekTaskWriter:
    """批量并发调用 DeepSeek 生成自然用户请求候选。"""

    def __init__(self, client: DeepSeekClient, *, concurrency: int = 5) -> None:
        """注入共享客户端并限制任务改写并发数。"""
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.client = client
        self.concurrency = concurrency

    def generate(self, blueprints: Iterable[TaskBlueprint]) -> list[TaskWriterResult]:
        """并发生成多个 Blueprint 的候选并按输入顺序返回。"""
        items = list(blueprints)
        if not items:
            return []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = [executor.submit(self.generate_one, blueprint) for blueprint in items]
            return [future.result() for future in futures]

    def generate_one(self, blueprint: TaskBlueprint) -> TaskWriterResult:
        """为单个 Blueprint 请求三个自然语言候选。"""
        request_id = f"task_writer_{blueprint.blueprint_id}_{uuid.uuid4().hex[:8]}"
        messages = [
            {"role": "system", "content": TASK_WRITER_SYSTEM},
            {
                "role": "user",
                "content": _json_prompt(blueprint.writer_view),
            },
        ]
        try:
            _, parsed = self.client.complete_json(
                messages,
                role="task_writer",
                request_id=request_id,
                temperature=0.7,
            )
            candidates = _normalize_candidates(parsed)
            return TaskWriterResult(blueprint.blueprint_id, tuple(candidates), request_id)
        except (DeepSeekAPIError, ValueError, TypeError) as exc:
            return TaskWriterResult(
                blueprint.blueprint_id,
                (),
                request_id,
                error_code=getattr(exc, "code", "TASK_WRITER_ERROR"),
                error_message=str(exc),
            )


def _normalize_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """把模型返回的候选列表规范化为 text 字典。"""
    raw = payload.get("candidates")
    if not isinstance(raw, list):
        raise ValueError("candidates must be an array")
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            normalized.append({"text": item})
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            normalized.append({"text": item["text"], **{key: value for key, value in item.items() if key != "text"}})
        else:
            raise ValueError("each candidate must contain string text")
    if not normalized:
        raise ValueError("candidates must not be empty")
    return normalized


def _json_prompt(value: dict[str, Any]) -> str:
    """把 writer_view 序列化为稳定的 JSON 用户提示。"""
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
