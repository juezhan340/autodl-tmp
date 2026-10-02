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


def test_generate_until_d4_workers_keep_order(tmp_path: Path) -> None:
    """workers=2 仍按提交顺序收条，并停在 D4。"""
    from new_demo.agents.DeepSeek_client import DeepSeekResponse
    from new_demo.data.PIPE_pipeline import generate_until_d4

    class FakeClient:
        """并发写 task/request/review 都给能过形状的假数据。"""

        def complete(self, messages, *, role: str, request_id=None, temperature=None) -> DeepSeekResponse:
            return DeepSeekResponse(request_id or "x", role, "把卧室主灯关掉。", {}, {}, 1.0, "fake")

        def complete_json(self, messages, *, role: str, request_id=None, temperature=None):
            response = self.complete(messages, role=role, request_id=request_id)
            if "审查" in messages[0]["content"] or "user_request" in messages[0]["content"] and "accept" in messages[0]["content"]:
                payload = {"accept": True, "codes": []}
            elif "verdict" in messages[0]["content"]:
                payload = {"verdict": "对"}
            else:
                payload = {
                    "intent": "关灯",
                    "conditions": [
                        {"device_id": "device_bedroom_light", "field": "on", "operator": "eq", "value": False}
                    ],
                    "keep": [],
                    "required_observations": [],
                    "expected_finish": {"outcome": "completed", "allowed_reason_codes": []},
                }
            return response, payload

    summary = generate_until_d4(
        count_per_category=1,
        seed=7,
        output_dir=tmp_path,
        client=FakeClient(),
        categories=("T1", "T5"),
        workers=2,
    )
    assert summary["attempt_count"] == 2
    assert summary["workers"] == 2
    assert summary["stopped_after"] == "D4"
    assert not (tmp_path / "data_processed" / "D5_trajectories.jsonl").exists()

