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


def test_request_writer_uses_t2_file() -> None:
    """写用户话走 D0_request_T2.md。"""
    client = FakeClient(text="睡觉前把客厅电视关掉，卧室空调调低一点，厨房冰箱别动。")
    task = {
        "intent": "睡觉前想凉一点，客厅电视关掉，卧室空调调低一点，厨房冰箱别动",
        "conditions": [
            {"device_id": "device_living_tv", "field": "on", "operator": "eq", "value": False},
            {"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 26.0},
        ],
        "keep": [{"device_id": "device_kitchen_fridge", "field": "target", "operator": "eq", "value": 4.0}],
        "required_observations": [],
        "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
    }
    result = DeepSeekRequestWriter(client).write(category="T2", task=task, home=_home())
    assert result.user_request.startswith("睡觉前")
    assert "conditions 有几条，话里就要有几处" in client.last_content
    assert "这一条 condition 的必要信息必须在话里" not in client.last_content


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
    """语义审查走 D3_review_T5.md。"""
    client = FakeClient(payload={"accept": True, "codes": []})
    result = DeepSeekInstructionReviewer(client).review(
        category="T5",
        task={
            "intent": "想知道湿不湿",
            "conditions": [],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
        user_request="卧室现在湿不湿、热不热？",
        intent="想知道湿不湿",
    )
    assert result.accept is True
    assert "必要信息是问状态" in client.last_content
    assert "必须听得出那一台设备和精确目标" not in client.last_content


def test_task_writer_allows_t1_le() -> None:
    """T1 现在允许 ge/le。"""
    client = FakeClient(
        payload={
            "intent": "进门还是热，想把卧室空调调低一点",
            "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 25.0}],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        }
    )
    result = DeepSeekTaskWriter(client).write(s0=_home(), persona={"name": "周凯"}, category="T1")
    assert result.error_code is None
    assert result.task["conditions"][0]["operator"] == "le"


def test_task_writer_rejects_t1_observations() -> None:
    """T1 带 required_observations 不合格。"""
    client = FakeClient(
        payload={
            "intent": "关灯",
            "conditions": [{"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}],
            "keep": [],
            "required_observations": [{"kind": "device", "device_id": "device_bedroom_light"}],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        }
    )
    result = DeepSeekTaskWriter(client).write(s0=_home(), persona={"name": "李梅"}, category="T1")
    assert result.error_code == "INVALID_TASK_JSON"
    assert "required_observations" in (result.error_message or "")






def test_task_writer_rejects_t3_already_true() -> None:
    """已经在下限时，T3 不能再写 le。"""
    home = _home()
    home["devices"][1]["state"]["target"] = 7.0
    client = FakeClient(
        payload={
            "intent": "屋里像蒸笼",
            "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 7.0}],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        }
    )
    result = DeepSeekTaskWriter(client).write(s0=home, persona={"name": "陈浩"}, category="T3")
    assert result.error_code == "INVALID_TASK_JSON"
    assert "already holds" in (result.error_message or "")


def test_task_writer_allows_t3_le_when_can_decrease() -> None:
    """当前 25 还能再降，T3 le 合格。"""
    client = FakeClient(
        payload={
            "intent": "屋里像蒸笼",
            "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 25.0}],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        }
    )
    result = DeepSeekTaskWriter(client).write(s0=_home(), persona={"name": "陈浩"}, category="T3")
    assert result.error_code is None


def test_task_writer_rejects_ge_value_not_s0() -> None:
    """ge/le 的 value 必须等于 s0 当前值。"""
    client = FakeClient(
        payload={
            "intent": "进门还是热，想把卧室空调调低一点",
            "conditions": [{"device_id": "device_bedroom_climate", "field": "target", "operator": "le", "value": 26.0}],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        }
    )
    result = DeepSeekTaskWriter(client).write(s0=_home(), persona={"name": "周凯"}, category="T1")
    assert result.error_code == "INVALID_TASK_JSON"
    assert "s0 current value" in (result.error_message or "")

