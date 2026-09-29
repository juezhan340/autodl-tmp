"""提示词：T1–T5 预装配固定文件；运行时只填本轮材料。"""

from __future__ import annotations

import pytest

from new_demo.data.D0_template import (
    build_prompt,
    load_personas,
    load_template,
    normalize_category,
    render_template,
)
from new_demo.data.D3_reviewer import program_leak_codes


def test_personas_are_twenty() -> None:
    """画像二十条，四字段，不含 sex/env_pref。"""
    rows = load_personas()
    assert len(rows) == 20
    assert rows[0]["persona_id"] == "p01"
    assert "occupation" in rows[0]
    assert "habits" in rows[0]
    assert "sex" not in rows[0]
    assert "env_pref" not in rows[0]


def test_request_and_review_are_shared_files() -> None:
    """D2-2 和 D3 各一份全文，不按 T 拆。"""
    t1 = load_template("request", "T1")
    t2 = load_template("request", "multi_control")
    assert t1 == t2
    assert "T1：点明那一台设备" in t1
    assert "T3：可以不点设备名" in t1
    r1 = load_template("review", "T1")
    r5 = load_template("review", "T5")
    assert r1 == r5
    assert "T3：可以不点设备" in r1
    assert "只问状态" in r1
    assert "{{user_request}}" in r1


def test_t3_task_allows_ge_le() -> None:
    """T3 任务模板写明 eq/ge/le，例子是 le。"""
    text = load_template("task", "vague_intent")
    assert "operator 只许 eq、ge、le" in text
    assert '"operator":"le"' in text


def test_runtime_only_fills_placeholders() -> None:
    """运行时只替换 {{ }}，不拼接 T 规则。"""
    prompt = build_prompt(
        "task",
        "T1",
        {"persona": {"name": "测试人"}, "s0": {"rooms": []}},
    )
    assert "测试人" in prompt
    assert "{{persona}}" not in prompt
    assert "{{s0}}" not in prompt
    assert "写一份 T1 单设备控制" in prompt


def test_missing_placeholder_raises() -> None:
    """本轮材料缺键就失败，不静默留空。"""
    with pytest.raises(KeyError):
        render_template("本轮画像：\n{{persona}}\n", {})


def test_program_leak_catches_device_id() -> None:
    """D3 第一步能扫到 task 里的 device_id。"""
    task = {
        "intent": "关灯",
        "conditions": [{"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}],
    }
    codes = program_leak_codes("把 device_bedroom_light 关掉", task)
    assert codes == ("HARD_LEAKAGE",)
    assert program_leak_codes("把卧室主灯关掉", task) == ()
    assert program_leak_codes("帮我 set_temperature", task) == ("HARD_LEAKAGE",)


def test_normalize_accepts_long_and_short_names() -> None:
    """single_control 和 T1 指向同一套文件。"""
    assert normalize_category("single_control") == "T1"
    assert normalize_category("T5") == "T5"
