"""默认停在蓝图；未确认不得出现 sc_*。"""

from __future__ import annotations

from pathlib import Path

from new_demo.data.PIPE_pipeline import run_until_d4
from new_demo.tests.C_test_run import _home


def test_stop_after_d4_writes_blueprint_not_scenario(tmp_path: Path) -> None:
    """过的草稿发 bp_*，没有 sc_* 文件。"""
    drafts = [
        {
            "category": "single_control",
            "home": _home(),
            "user_request": "把卧室主灯关掉",
            "task": {
                "intent": "关灯",
                "conditions": [
                    {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}
                ],
                "keep": [],
                "required_observations": [],
                "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
            },
        },
        {
            "category": "single_control",
            "home": _home(),
            "user_request": "关掉幽灵灯",
            "task": {
                "intent": "幽灵",
                "conditions": [
                    {"device_id": "device_ghost", "field": "on", "operator": "eq", "value": False}
                ],
                "keep": [],
                "required_observations": [],
                "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
            },
        },
    ]
    summary = run_until_d4(drafts, tmp_path)
    assert summary["stopped_after"] == "D4"
    assert summary["blueprint_count"] == 1
    assert summary["failure_count"] == 1
    blueprints = (tmp_path / "data_processed" / "D4_blueprints.jsonl").read_text(encoding="utf-8").strip()
    assert "bp_001" in blueprints
    assert "sc_" not in blueprints
    failure = (tmp_path / "data_raw" / "D34_failures.jsonl").read_text(encoding="utf-8")
    assert "blueprint_id" not in failure
    assert not (tmp_path / "data_processed" / "D5_trajectories.jsonl").exists()
    assert (tmp_path / "reports" / "D4_preview.md").exists()
