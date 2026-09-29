"""总表不删失败；全过才进 dataset。"""

from __future__ import annotations

from pathlib import Path

from new_demo.data.D6_judge import judge_one
from new_demo.data.D_copy_dataset import copy_success, write_dataset


def _row(*, labels: dict, category: str, d6: str) -> dict:
    """造一条轨迹总表记录。"""
    return {
        "scenario": {"user_request": "测"},
        "record": {"scenario_id": "sc_x", "turns": [], "finish": {"outcome": "completed", "summary": "ok"}},
        "labels": labels,
        "category": category,
        "d6": d6,
        "d6_votes": [],
    }


PASS = {"C-1": True, "C-2": True, "C-3": True, "C-4": True}
FAIL = {"C-1": True, "C-2": False, "C-3": True, "C-4": True}


def test_copy_only_full_pass(tmp_path: Path) -> None:
    """C 未过或 D6 为错/失败的不进数据集，总表条数不变。"""
    rows = [
        _row(labels=PASS, category="T1", d6="跳过"),
        _row(labels=PASS, category="T3", d6="对"),
        _row(labels=PASS, category="T3", d6="错"),
        _row(labels=FAIL, category="T1", d6="跳过"),
        _row(labels=PASS, category="T4", d6="system_failure"),
    ]
    kept, stats = copy_success(rows)
    assert stats["total"] == 5
    assert stats["copied"] == 2
    assert len(rows) == 5
    write_dataset(rows, tmp_path)
    text = (tmp_path / "data_processed" / "D_dataset.jsonl").read_text(encoding="utf-8")
    assert text.count("\n") == 2


class SeqClient:
    """按顺序返回 verdict JSON。"""

    def __init__(self, payloads: list[dict]) -> None:
        """预设票。"""
        self.payloads = list(payloads)

    def complete_json(self, messages, *, role: str, request_id=None, temperature=None):
        """吐下一票。"""
        from new_demo.agents.DeepSeek_client import DeepSeekResponse

        parsed = self.payloads.pop(0)
        resp = DeepSeekResponse("r", role, str(parsed), {}, {}, 1.0, "fake")
        return resp, parsed


def test_d6_majority_and_parse_failure() -> None:
    """2 对 1 错算过；有效票不足 3 为 system_failure。"""
    row = _row(labels=PASS, category="T3", d6="待审")
    judged = judge_one(row, SeqClient([{"verdict": "对"}, {"verdict": "对"}, {"verdict": "错"}]))
    assert judged["d6"] == "对"
    row2 = _row(labels=PASS, category="T4", d6="待审")
    judged2 = judge_one(row2, SeqClient([{"verdict": "maybe"}, {"verdict": "对"}, {"verdict": "对"}]))
    assert judged2["d6"] == "system_failure"
    t1 = _row(labels=PASS, category="T1", d6="跳过")
    assert judge_one(t1, SeqClient([]))["d6"] == "跳过"
