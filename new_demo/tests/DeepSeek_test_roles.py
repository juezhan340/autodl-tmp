"""A 与 external 请求体都不带 max_tokens。"""

from __future__ import annotations

from pathlib import Path

from new_demo.agents.DeepSeek_client import DeepSeekClient


class SpyClient(DeepSeekClient):
    """拦截 _post，不发网络。"""

    def __init__(self, env_path: Path) -> None:
        """读临时 env。"""
        super().__init__(env_path=env_path)
        self.payloads: list[dict] = []

    def _post(self, payload):
        """记下请求体并返回空 JSON 对象。"""
        self.payloads.append(dict(payload))
        return {"choices": [{"message": {"content": "{}"}}]}


def test_neither_role_sends_max_tokens(tmp_path: Path) -> None:
    """两路请求都不含 max_tokens。"""
    env = tmp_path / ".env.deepseek"
    env.write_text("DEEPSEEK_API_KEY=test-key\nDEEPSEEK_MODEL=deepseek-chat\n", encoding="utf-8")
    client = SpyClient(env)
    client.complete([{"role": "user", "content": "hi"}], role="A", request_id="a1")
    client.complete_json([{"role": "user", "content": "{}"}], role="external", request_id="e1")
    assert client.payloads[0]["model"]
    assert "max_tokens" not in client.payloads[0]
    assert "max_tokens" not in client.payloads[1]


def test_a_policy_appends_messages(tmp_path: Path) -> None:
    """第一轮 system+user；第二轮只追加 observation，不重贴规则。"""
    from new_demo.agents.A_policy import DeepSeekPolicy

    env = tmp_path / ".env.deepseek"
    env.write_text("DEEPSEEK_API_KEY=test-key\nDEEPSEEK_MODEL=deepseek-chat\n", encoding="utf-8")
    client = SpyClient(env)
    policy = DeepSeekPolicy(client)
    tools = [{"name": "observe_home", "description": "x", "parameters": {"type": "object", "properties": {}}}]
    first = policy.respond(
        {
            "turn_index": 1,
            "tools": tools,
            "observation": {
                "scenario_id": "sc_x",
                "user_request": "把主灯调暗",
                "last_tool_result": None,
            },
        }
    )
    assert first == {}
    assert client.payloads[0]["messages"][0]["role"] == "system"
    assert client.payloads[0]["messages"][1]["role"] == "user"
    assert client.payloads[0]["messages"][1]["content"] == "把主灯调暗"
    assert "你是智能家居助手" in client.payloads[0]["messages"][0]["content"]
    policy.respond(
        {
            "turn_index": 2,
            "tools": tools,
            "observation": {
                "scenario_id": "sc_x",
                "user_request": "把主灯调暗",
                "last_tool_result": {"ok": True, "data": {"rooms": []}},
            },
        }
    )
    second = client.payloads[1]["messages"]
    assert second[0]["role"] == "system"
    assert second[1]["content"] == "把主灯调暗"
    assert second[-1]["role"] == "user"
    assert second[-1]["content"].startswith("observation:")
    assert second.count({"role": "system", "content": second[0]["content"]}) == 1
