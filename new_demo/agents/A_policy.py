"""A 的最小接口。V1 用脚本策略；D5 用 DeepSeekPolicy，role=A，不限 token。"""

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
    """D5 里的 A。一场 episode 共用一份 messages，后面只 append。"""

    def __init__(self, client: DeepSeekClient) -> None:
        """注入客户端，会话在第一轮重建。"""
        self.client = client
        self._messages: list[dict[str, str]] = []
        self._scenario_id: str | None = None

    def respond(self, context: dict[str, Any]) -> Any:
        """第一轮发 system+用户话；之后只追加模型输出和 observation。"""
        observation = context.get("observation") or {}
        scenario_id = str(observation.get("scenario_id", "sc"))
        turn_index = context.get("turn_index")
        if turn_index == 1 or scenario_id != self._scenario_id:
            self._start_episode(observation, context)
        else:
            self._append_observation(observation, context)
        request_id = f"a_{scenario_id}_turn_{turn_index}"
        try:
            response = self.client.complete(
                copy_json(self._messages),
                role="A",
                request_id=request_id,
            )
        except Exception as exc:
            return f"A_POLICY_ERROR: {exc}"
        self._messages.append({"role": "assistant", "content": response.content})
        try:
            parsed = _parse_json_object(response.content)
        except (ValueError, json.JSONDecodeError):
            return response.content
        return copy_json(parsed)

    def _start_episode(self, observation: dict[str, Any], context: dict[str, Any]) -> None:
        """建 system 和第一条 user，丢掉上一场的 messages。"""
        tools = context.get("tools") or observation.get("tools") or []
        system = build_a_prompt({"tools": tools})
        user_request = str(observation.get("user_request", ""))
        self._messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_request},
        ]
        self._scenario_id = str(observation.get("scenario_id", "sc"))

    def _append_observation(self, observation: dict[str, Any], context: dict[str, Any]) -> None:
        """把上一轮工具回执或协议错误追加成 user observation。"""
        payload = context.get("protocol_feedback")
        if payload is None:
            payload = observation.get("last_tool_result")
        text = "observation: " + json.dumps(payload, ensure_ascii=False)
        self._messages.append({"role": "user", "content": text})
