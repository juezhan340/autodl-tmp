"""配额模式：每类凑满成功条数，不超过尝试上限。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from new_demo.data.PIPE_pipeline import run_quota_pipeline


def _ok_row(category: str, attempt: int) -> dict[str, Any]:
    """造一条能进集的假轨迹。"""
    sid = f"sc_{category}_{attempt:03d}"
    return {
        "scenario": {"scenario_id": sid, "user_request": "测"},
        "record": {"scenario_id": sid, "turns": [], "finish": {"outcome": "completed", "summary": "ok"}},
        "labels": {"C-1": True, "C-2": True, "C-3": True, "C-4": True},
        "category": category,
        "d6": "跳过",
        "d6_votes": [],
    }


def _sample(success_when) -> Any:
    """按 attempt 决定成败的假 runner。"""

    def sample_fn(job: dict[str, Any]) -> dict[str, Any]:
        """测试用，不调模型。"""
        category = str(job["category"])
        attempt = int(job["attempt"])
        ok = bool(success_when(category, attempt))
        blueprint = {
            "blueprint_id": job["blueprint_id"],
            "category": category,
            "home": {},
            "task": {},
            "user_request": f"{category}-{attempt}",
        }
        traj = _ok_row(category, attempt) if ok else {
            **_ok_row(category, attempt),
            "labels": {"C-1": True, "C-2": False, "C-3": True, "C-4": True},
        }
        return {
            "draft": {"category": category, "attempt": attempt, "home_seed": job.get("home_seed")},
            "passed": True,
            "failure": None if ok else {"category": category, "stage": "D5", "error_code": "C-2"},
            "blueprint": blueprint,
            "trajectory": traj,
            "success": ok,
        }

    return sample_fn


def test_quota_stops_at_target(tmp_path: Path) -> None:
    """一直成功时，每类只跑满目标条数，不把 100 次用完。"""
    stats = run_quota_pipeline(
        target_success=2,
        max_attempts=8,
        seed=11,
        output_dir=tmp_path,
        client=None,
        categories=("T1", "T2"),
        workers_per_category=3,
        sample_fn=_sample(lambda cat, attempt: True),
    )
    assert stats["copied"] == 4
    assert stats["per_category"]["T1"]["success"] == 2
    assert stats["per_category"]["T2"]["success"] == 2
    assert stats["per_category"]["T1"]["attempts"] == 2
    assert stats["per_category"]["T2"]["attempts"] == 2
    text = (tmp_path / "data_processed" / "D_dataset.jsonl").read_text(encoding="utf-8")
    assert "sc_T1_001" in text
    assert "sc_T1_003" not in text


def test_quota_respects_max_attempts(tmp_path: Path) -> None:
    """一直失败时用尽尝试次数，进集为 0。"""
    stats = run_quota_pipeline(
        target_success=3,
        max_attempts=4,
        seed=12,
        output_dir=tmp_path,
        client=None,
        categories=("T3",),
        workers_per_category=2,
        sample_fn=_sample(lambda cat, attempt: False),
    )
    assert stats["copied"] == 0
    assert stats["per_category"]["T3"]["attempts"] == 4
    assert stats["per_category"]["T3"]["success"] == 0
    assert stats["blueprint_count"] == 4
    assert (tmp_path / "data_processed" / "D5_trajectories.jsonl").read_text(encoding="utf-8").count("\n") == 4


def test_quota_retries_after_failures(tmp_path: Path) -> None:
    """奇数次失败、偶数次成功，目标 2 则跑 4 次。"""
    stats = run_quota_pipeline(
        target_success=2,
        max_attempts=10,
        seed=13,
        output_dir=tmp_path,
        client=None,
        categories=("T5",),
        workers_per_category=2,
        sample_fn=_sample(lambda cat, attempt: attempt % 2 == 0),
    )
    assert stats["copied"] == 2
    assert stats["per_category"]["T5"]["attempts"] == 4
    assert stats["per_category"]["T5"]["success"] == 2


def test_quota_refuses_existing_dir(tmp_path: Path) -> None:
    """输出目录已有蓝图就拒绝，避免覆盖旧批次。"""
    processed = tmp_path / "data_processed"
    processed.mkdir(parents=True)
    (processed / "D4_blueprints.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        run_quota_pipeline(
            target_success=1,
            max_attempts=1,
            seed=1,
            output_dir=tmp_path,
            client=None,
            categories=("T1",),
            workers_per_category=1,
            sample_fn=_sample(lambda cat, attempt: True),
        )
    except RuntimeError as exc:
        assert "already has data" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
