"""A 的最小接口。V1 用脚本策略；D5 用 DeepSeekPolicy，role=A。"""

from __future__ import annotations

import json
from typing import Any, Protocol

from new_demo.agents.DeepSeek_client import DeepSeekClient, _parse_json_object
from new_demo.data.D0_template import build_a_prompt
from new_demo.env.B_models import copy_json


class Policy(Protocol):
    """C 每轮调用的助手口。"""

    def respond(self, context: dict[str, Any]) -> Any:
        """根据当前 observation 和历史产生一次 assistant 响应。"""


class ScriptPolicy:
    """按预先写好的响应列表依次作答，供测试和 Oracle 式演示。"""

    def __init__(self, responses: list[Any]) -> None:
        """保存本回合要依次吐出的响应。"""
        self._responses = list(responses)
        self._index = 0

    def respond(self, context: dict[str, Any]) -> Any:
        """吐出下一条预设响应；用完就报错，避免静默空转。"""
        if self._index >= len(self._responses):
            raise RuntimeError(f"ScriptPolicy has no response for turn {context.get('turn_index')}")
        item = self._responses[self._index]
        self._index += 1
        return item


class DeepSeekPolicy:
    """D5 里的 A。每轮看 context，role=A，不限 token。"""

    def __init__(self, client: DeepSeekClient) -> None:
        """注入共用客户端。"""
        self.client = client

    def respond(self, context: dict[str, Any]) -> Any:
        """把本轮观察填进固定 A 提示词，收回一个工具 JSON。"""
        observation = context.get("observation") or {}
        values = {
            "user_request": observation.get("user_request", ""),
            "turn_index": context.get("turn_index"),
            "max_turns": context.get("max_turns"),
            "last_tool_result": observation.get("last_tool_result"),
            "protocol_feedback": context.get("protocol_feedback"),
            "tools": context.get("tools") or observation.get("tools"),
            "history": context.get("history"),
        }
        prompt = build_a_prompt(values)
        scenario_id = observation.get("scenario_id", "sc")
        request_id = f"a_{scenario_id}_turn_{context.get('turn_index')}"
        try:
            response = self.client.complete(
                [{"role": "user", "content": prompt}],
                role="A",
                request_id=request_id,
            )
        except Exception as exc:
            return f"A_POLICY_ERROR: {exc}"
        try:
            parsed = _parse_json_object(response.content)
        except (ValueError, json.JSONDecodeError):
            return response.content
        return copy_json(parsed)
