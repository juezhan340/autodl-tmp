"""调用 DeepSeek 审查自然语言任务候选是否覆盖 Blueprint 语义。"""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from homeflow_demo.agents.deepseek_client import DeepSeekAPIError, DeepSeekClient

from .task_blueprints import TaskBlueprint


TASK_REVIEWER_SYSTEM = """你是 HomeFlow 任务候选审查器。
只返回 JSON，不要 markdown，不要解释，不要 emoji。
JSON 必须包含：accept、category_match、target_covered、extra_intent、soft_leakage、semantic_duplicate_group、review_codes。
你只判断候选文本是否忠于给定任务语义，不判断设备是否已经执行成功。
候选不得添加输入没有的设备目标，不得泄露内部 ID、action 名和 reason_code。
同一个结论只表达一次，审查结果保持简短。
"""


@dataclass(frozen=True)
class TaskReviewResult:
    """保存一个候选的 DeepSeek 语义审查结果。"""

    blueprint_id: str
    candidate: dict[str, Any]
    decision: dict[str, Any]
    request_id: str
    error_code: str | None = None
    error_message: str | None = None

    @property
    def accepted(self) -> bool:
        """返回审查器是否接受该候选。"""
        return self.error_code is None and self.decision.get("accept") is True

    def to_dict(self) -> dict[str, Any]:
        """转换为审查 JSONL 记录。"""
        return {
            "blueprint_id": self.blueprint_id,
            "candidate": dict(self.candidate),
            "decision": dict(self.decision),
            "request_id": self.request_id,
            "accepted": self.accepted,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class DeepSeekTaskReviewer:
    """并发调用 DeepSeek 完成任务文本语义审查。"""

    def __init__(self, client: DeepSeekClient, *, concurrency: int = 5) -> None:
        """注入客户端并限制语义审查并发。"""
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.client = client
        self.concurrency = concurrency

    def review(
        self,
        items: Iterable[tuple[TaskBlueprint, dict[str, Any]]],
    ) -> list[TaskReviewResult]:
        """并发审查候选，并保持输入顺序。"""
        pairs = list(items)
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = [executor.submit(self.review_one, blueprint, candidate) for blueprint, candidate in pairs]
            return [future.result() for future in futures]

    def review_one(
        self,
        blueprint: TaskBlueprint,
        candidate: dict[str, Any],
    ) -> TaskReviewResult:
        """审查单个自然语言候选。"""
        request_id = f"task_reviewer_{blueprint.blueprint_id}_{uuid.uuid4().hex[:8]}"
        user_payload = {
            "task_semantics": blueprint.writer_view,
            "candidate": candidate,
        }
        messages = [
            {"role": "system", "content": TASK_REVIEWER_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
        ]
        try:
            _, decision = self.client.complete_json(
                messages,
                role="task_reviewer",
                request_id=request_id,
                temperature=0.0,
            )
            normalized = _normalize_decision(decision)
            return TaskReviewResult(blueprint.blueprint_id, candidate, normalized, request_id)
        except (DeepSeekAPIError, ValueError, TypeError) as exc:
            return TaskReviewResult(
                blueprint.blueprint_id,
                candidate,
                {},
                request_id,
                error_code=getattr(exc, "code", "TASK_REVIEW_ERROR"),
                error_message=str(exc),
            )


def _normalize_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """校验审查器最小输出字段并补齐可选字段。"""
    required = ("accept", "category_match", "target_covered", "extra_intent", "soft_leakage")
    if any(not isinstance(decision.get(key), bool) for key in required):
        raise ValueError("task reviewer response has invalid boolean fields")
    return {
        "accept": decision["accept"],
        "category_match": decision["category_match"],
        "target_covered": decision["target_covered"],
        "extra_intent": decision["extra_intent"],
        "soft_leakage": decision["soft_leakage"],
        "semantic_duplicate_group": decision.get("semantic_duplicate_group"),
        "review_codes": decision.get("review_codes", []),
    }
