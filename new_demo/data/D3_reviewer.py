"""D3：先程序扫硬泄露，再按已装配好的该类审指令模板问 DeepSeek。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.D0_template import build_prompt, display_names_from_home, normalize_category, rooms_from_home
from new_demo.env.B_models import copy_json


HARD_TOKENS = (
    "turn_on",
    "turn_off",
    "toggle",
    "set_mode",
    "set_temperature",
    "set_percentage",
    "observe_home",
    "inspect_room",
    "inspect_device",
    "execute_action",
    "OUT_OF_SAFE_RANGE",
    "READ_ONLY_DEVICE",
    "device_id",
    "room_id",
    "reason_code",
)
ALLOWED_CODES = {"TARGET_NOT_COVERED", "EXTRA_INTENT", "HARD_LEAKAGE"}


@dataclass(frozen=True)
class ReviewResult:
    """D3 两步合计。"""

    accept: bool
    codes: tuple[str, ...]
    request_id: str | None = None
    stage: str = "program"

    def to_dict(self) -> dict[str, Any]:
        """写成失败表或草稿字段。"""
        return {
            "accept": self.accept,
            "codes": list(self.codes),
            "request_id": self.request_id,
            "stage": self.stage,
        }


class DeepSeekInstructionReviewer:
    """程序硬泄露 + 外部 DeepSeek 语义审查。"""

    def __init__(self, client: DeepSeekClient) -> None:
        """注入客户端。"""
        self.client = client

    def review(
        self,
        *,
        category: str,
        task: dict[str, Any],
        user_request: str,
        intent: str | None = None,
        home: dict[str, Any] | None = None,
    ) -> ReviewResult:
        """第一步程序，过了才调模型。home 用来告诉模型本轮有哪些房间和设备。"""
        leak_codes = program_leak_codes(user_request, task)
        if leak_codes:
            return ReviewResult(False, leak_codes, stage="program")
        code = normalize_category(category)
        request_id = f"d3_review_{code}_{uuid.uuid4().hex[:8]}"
        used_intent = intent if intent is not None else str(task.get("intent", ""))
        house = home or {}
        prompt = build_prompt(
            "review",
            code,
            {
                "intent": used_intent,
                "task": task,
                "user_request": user_request,
                "rooms": rooms_from_home(house),
                "display_names": display_names_from_home(house),
            },
        )
        _, parsed = self.client.complete_json(
            [{"role": "user", "content": prompt}],
            role="external",
            request_id=request_id,
        )
        accept = parsed.get("accept") is True
        raw_codes = parsed.get("codes") or []
        if not isinstance(raw_codes, list) or not all(isinstance(item, str) for item in raw_codes):
            return ReviewResult(False, ("INVALID_MODEL_JSON",), request_id, stage="model")
        codes = tuple(item for item in raw_codes if item in ALLOWED_CODES)
        if accept and codes:
            accept = False
        if not accept and not codes:
            codes = ("TARGET_NOT_COVERED",)
        return ReviewResult(accept, codes, request_id, stage="model")


def program_leak_codes(user_request: str, task: dict[str, Any]) -> tuple[str, ...]:
    """扫 id、动作名、reason_code、工具 JSON 碎片。"""
    text = user_request or ""
    lowered = text
    for token in HARD_TOKENS:
        if token in lowered:
            return ("HARD_LEAKAGE",)
    blob = copy_json(task)
    ids: list[str] = []
    _collect_ids(blob, ids)
    for item in ids:
        if item and item in text:
            return ("HARD_LEAKAGE",)
    if re.search(r"\{[^{}]*\"(name|arguments|device_id)\"", text):
        return ("HARD_LEAKAGE",)
    return ()


def _collect_ids(value: Any, ids: list[str]) -> None:
    """从 task JSON 里收集 device_id / room_id 字符串。"""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"device_id", "room_id"} and isinstance(item, str):
                ids.append(item)
            else:
                _collect_ids(item, ids)
    elif isinstance(value, list):
        for item in value:
            _collect_ids(item, ids)
