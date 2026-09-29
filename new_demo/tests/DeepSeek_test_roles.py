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
