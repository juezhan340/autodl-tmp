"""D5 编 Scenario、跑 C，失败也留，不调 D6。"""

from __future__ import annotations

from new_demo.agents.A_policy import ScriptPolicy
from new_demo.data.D5_run import run_one
from new_demo.tests.C_test_run import _call, _climate_success_calls, _home


def test_d5_assigns_sc_and_skips_d6_for_t1() -> None:
    """scenario_id 不等于 blueprint_id；T1 的 D6 初值是跳过。"""
    blueprint = {
        "blueprint_id": "bp_001",
        "category": "T1",
        "home": _home(),
        "user_request": "卧室太热了，把空调调到 24 度",
        "task": {
            "intent": "觉得卧室太热，想睡觉",
            "conditions": [
                {"device_id": "device_bedroom_climate", "field": "target", "operator": "eq", "value": 24.0}
            ],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    }
    row = run_one(blueprint, ScriptPolicy(_climate_success_calls()), "sc_001")
    assert row["scenario"]["scenario_id"] == "sc_001"
    assert row["scenario"]["blueprint_id"] == "bp_001"
    assert row["d6"] == "跳过"
    assert row["labels"]["C-1"] is True
    assert "probe" not in row["scenario"]


def test_continue_from_d5_copies_t1(tmp_path) -> None:
    """停闸后用脚本策略跑 T1，D6 跳过，复制进数据集。"""
    import json
    from new_demo.data.PIPE_pipeline import continue_from_d5, _write_jsonl
    from new_demo.tests.D2_D3_test_writers import FakeClient

    blueprint = {
        "blueprint_id": "bp_001",
        "category": "T1",
        "home": _home(),
        "user_request": "卧室太热了，把空调调到 24 度",
        "task": {
            "intent": "觉得卧室太热，想睡觉",
            "conditions": [
                {"device_id": "device_bedroom_climate", "field": "target", "operator": "eq", "value": 24.0}
            ],
            "keep": [],
            "required_observations": [],
            "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
        },
    }
    processed = tmp_path / "data_processed"
    processed.mkdir(parents=True)
    _write_jsonl(processed / "D4_blueprints.jsonl", [blueprint])
    stats = continue_from_d5(
        tmp_path,
        FakeClient(payload={"verdict": "对"}),
        policy=ScriptPolicy(_climate_success_calls()),
    )
    assert stats["trajectories"] == 1
    assert stats["copied"] == 1
    text = (processed / "D5_trajectories.jsonl").read_text(encoding="utf-8")
    row = json.loads(text)
    assert row["record"]["scenario_id"] == "sc_001"
    assert row["d6"] == "跳过"
    assert "sc_001" in (processed / "D_dataset.jsonl").read_text(encoding="utf-8")
