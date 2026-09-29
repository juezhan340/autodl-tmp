"""D2/D3 写手：用假客户端，不打真实 API。"""

from __future__ import annotations

from new_demo.agents.DeepSeek_client import DeepSeekResponse
from new_demo.data.D2_request_writer import DeepSeekRequestWriter
from new_demo.data.D2_task_writer import DeepSeekTaskWriter
from new_demo.data.D3_reviewer import DeepSeekInstructionReviewer
from new_demo.tests.C_test_run import _home


class FakeClient:
    """记下 role 和请求正文，按预设返回。"""

    def __init__(self, *, payload: dict | None = None, text: str = "") -> None:
        """预设 JSON 或一句中文。"""
        self.payload = payload or {}
        self.text = text
        self.last_role = None
        self.last_content = ""

    def complete(self, messages, *, role: str, request_id=None, temperature=None) -> DeepSeekResponse:
        """记下 external 调用。"""
        self.last_role = role
        self.last_content = messages[0]["content"]
        return DeepSeekResponse(request_id or "x", role, self.text, {}, {}, 1.0, "fake")

    def complete_json(self, messages, *, role: str, request_id=None, temperature=None):
        """返回预设对象。"""
        response = self.complete(messages, role=role, request_id=request_id)
        return response, dict(self.payload)


def test_task_writer_uses_t1_file_and_external_role() -> None:
    """写 task 走 T1 固定模板，role=external。"""
    client = FakeClient(
        payload={
            "intent": "要睡觉关灯",
            "conditions": [{"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        }
    )
    result = DeepSeekTaskWriter(client).write(s0=_home(), persona={"name": "李梅"}, category="T1")
    assert result.error_code is None
    assert result.task["intent"] == "要睡觉关灯"
    assert client.last_role == "external"
    assert "写一份 T1 单设备控制" in client.last_content
    assert "李梅" in client.last_content


def test_request_writer_uses_preassembled_t2_file() -> None:
    """写用户话走共用的 D0_request.md。"""
    client = FakeClient(text="孩子要睡了，灯关了，空调二十四度，客厅灯别动。")
    task = {
        "intent": "睡前",
        "conditions": [
            {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False},
            {"device_id": "device_bedroom_climate", "field": "target", "operator": "eq", "value": 24.0},
        ],
        "keep": [{"device_id": "device_living_light", "field": "on", "operator": "eq", "value": True}],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    result = DeepSeekRequestWriter(client).write(category="T2", task=task, home=_home())
    assert result.user_request.startswith("孩子要睡了")
    assert "T2：一条话里覆盖全部 condition" in client.last_content
    assert "T1：点明那一台设备" in client.last_content


def test_reviewer_program_leak_skips_model() -> None:
    """硬泄露在第一步挡掉，不调 DeepSeek。"""
    client = FakeClient(payload={"accept": True, "codes": []})
    result = DeepSeekInstructionReviewer(client).review(
        category="T1",
        task={"intent": "关灯", "conditions": [{"device_id": "device_bedroom_light"}]},
        user_request="把 device_bedroom_light 关掉",
        intent="关灯",
    )
    assert result.accept is False
    assert result.codes == ("HARD_LEAKAGE",)
    assert result.stage == "program"
    assert client.last_role is None


def test_reviewer_uses_t5_file() -> None:
    """语义审查走共用的 D3_review.md。"""
    client = FakeClient(payload={"accept": True, "codes": []})
    result = DeepSeekInstructionReviewer(client).review(
        category="T5",
        task={
            "intent": "想知道湿不湿",
            "conditions": [],
            "keep": [],
            "required_observations": [{"kind": "device", "device_id": "sensor_bedroom_env"}],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
        user_request="卧室现在湿不湿、热不热？",
        intent="想知道湿不湿",
    )
    assert result.accept is True
    assert "只问状态" in client.last_content
    assert "必须能听出那一台设备" in client.last_content
