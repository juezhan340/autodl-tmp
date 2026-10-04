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


def test_personas_are_one_hundred() -> None:
    """画像一百条（p01–p100），四字段，不含 sex/env_pref。"""
    rows = load_personas()
    assert len(rows) == 100
    assert rows[-1]["persona_id"] == "p100"
    assert rows[0]["persona_id"] == "p01"
    assert "occupation" in rows[0]
    assert "habits" in rows[0]
    assert "sex" not in rows[0]
    assert "env_pref" not in rows[0]


def test_request_and_review_are_split_by_t() -> None:
    """D2-2 和 D3 按 T 分文件，T1 不管 T2 的拼接规则。"""
    t1 = load_template("request", "T1")
    t2 = load_template("request", "multi_control")
    t4 = load_template("request", "T4")
    assert t1 != t2
    assert "这一条 condition 的必要信息必须在话里" in t1
    assert "conditions 有几条，话里就要有几处" in t2
    assert "把卧室空调调到三度" in t4
    r1 = load_template("review", "T1")
    r5 = load_template("review", "T5")
    assert r1 != r5
    assert "调低一点" in r1
    assert "必要信息是问状态" in r5
    assert "{{user_request}}" in r1


def test_t3_task_allows_ge_le() -> None:
    """T3 三种 operator，le/ge 相对初值。"""
    text = load_template("task", "vague_intent")
    assert "operator 只有三种" in text
    assert "比现在高" in text and "比现在低" in text
    assert '"operator":"le"' in text
    assert "身上发潮" in text


def test_t1_task_allows_range_and_empty_obs() -> None:
    """T1 准许 eq/ge/le，required_observations 必须空。"""
    text = load_template("task", "T1")
    assert "operator 只有三种" in text
    assert "required_observations 必须是空数组" in text
    assert "主灯用 on 或 mode" in text


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
