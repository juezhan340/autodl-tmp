"""D2 第二次：按已经装配好的该类用户指令模板写一句中文。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.D0_template import build_prompt, display_names_from_home, normalize_category


@dataclass(frozen=True)
class RequestWriteResult:
    """一句用户请求。"""

    user_request: str | None
    request_id: str
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """写成草稿字段。"""
        return {
            "user_request": self.user_request,
            "request_id": self.request_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class DeepSeekRequestWriter:
    """用 role=external 写口语请求，不限 token。"""

    def __init__(self, client: DeepSeekClient) -> None:
        """注入客户端。"""
        self.client = client

    def write(
        self,
        *,
        category: str,
        task: dict[str, Any],
        home: dict[str, Any],
        intent: str | None = None,
    ) -> RequestWriteResult:
        """填 intent/task/display_names。T 规则已在文件里。"""
        code = normalize_category(category)
        request_id = f"d2_request_{code}_{uuid.uuid4().hex[:8]}"
        used_intent = intent if intent is not None else str(task.get("intent", ""))
        prompt = build_prompt(
            "request",
            code,
            {
                "intent": used_intent,
                "task": task,
                "display_names": display_names_from_home(home),
            },
        )
        response = self.client.complete(
            [{"role": "user", "content": prompt}],
            role="external",
            request_id=request_id,
        )
        text = _one_sentence(response.content)
        if not text:
            return RequestWriteResult(None, request_id, "INVALID_REQUEST_TEXT", "empty user_request")
        return RequestWriteResult(text, request_id)


def _one_sentence(content: str) -> str:
    """去掉围栏和首尾引号，只留一句。"""
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    if (text.startswith("“") and text.endswith("”")) or (text.startswith('"') and text.endswith('"')):
        text = text[1:-1].strip()
    return text.replace("\n", "").strip()
