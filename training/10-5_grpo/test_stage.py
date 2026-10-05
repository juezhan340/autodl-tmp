"""离线检查100任务第一阶段、只读监控和固定200任务评测边界。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from runtime import HERE, load_config, write_json, write_jsonl
from run_stage import reward_statistics, select_stage_tasks
from start import build_command
from dashboard_server import snapshot
from live import read_metrics
from evaluate_stage import final_success, summarize


def test_stage_config_and_selection():
    """用户批准16×1，五类各20，选择可复现且与原划分隔离。"""
    config = load_config(HERE / "stage1_config.json")
    assert config["micro_batch"] == 16 and config["accumulation"] == 1
    if not Path(config["sft_data"]).exists():
        pytest.skip("server training split unavailable")
    tasks = select_stage_tasks(config)
    assert len(tasks) == 100 and tasks == select_stage_tasks(config)
    assert all(sum(row["category"] == category for row in tasks) == 20 for category in ("T1", "T2", "T3", "T4", "T5"))
    config["micro_batch"] = 8
    with pytest.raises(ValueError, match="no automatic fallback"):
        select_stage_tasks(config)


def test_training_launch_requires_two_confirmations():
    """没有训练和API确认都不能构造正式命令，更不会隐式做冒烟。"""
    with pytest.raises(ValueError):
        build_command("train", HERE / "stage1_config.json", 6008, "/tmp/example", True, False)
    command = build_command("train", HERE / "stage1_config.json", 6008, "/tmp/example", True, True)
    assert command[2].endswith("run_stage.py") and "--confirm-stage-training" in command
    assert "smoke.py" not in " ".join(command)


def test_monitor_waiting_and_dead_process(tmp_path):
    """监控只看active_run，不引用历史冒烟；死亡进程显示中断且隐藏身份。"""
    config = load_config(HERE / "stage1_config.json")
    config["output_root"] = str(tmp_path)
    assert snapshot(config, {})["training"]["status"] == "not_started"
    run = tmp_path / "active"
    write_json(tmp_path / "active_run.json", {"run_dir": str(run)})
    write_json(run / "training_status.json", {"status": "running", "pid": -1, "process_identity": "missing", "phase": "rollout"})
    data = snapshot(config, {})
    assert data["training"]["status"] == "interrupted"
    assert "pid" not in data["training"] and "process_identity" not in data["training"]
    assert data["config"]["micro_batch"] == 16


def test_metrics_ignores_only_partial_tail(tmp_path):
    """正在追加的一半行不能让页面503，完整错误行必须报错。"""
    path = tmp_path / "metrics.jsonl"
    path.write_text('{"global_step":1}\n{"global', encoding="utf-8")
    assert read_metrics(path) == [{"global_step": 1}]
    path.write_text('{bad}\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_metrics(path)


def test_reward_metrics_and_pending():
    """同分组与严重违规独立统计，待审reward禁止进入曲线。"""
    rows = [{"rollout_id": str(index), "category": "T2"} for index in range(4)]
    evidence = [{"false_finish": False, "unsafe_events": [], "budget_exhausted": False, "error_count": 0} for _ in rows]
    scores = [{"total_reward": 6., "terms": {"success": 3.}} for _ in rows]
    stats = reward_statistics(rows, evidence, scores, [0.] * 4, 4)
    assert stats["reward_mean"] == 6 and stats["tied_group_rate"] == 1 and stats["success_rate"] == 1
    scores[0]["total_reward"] = None
    with pytest.raises(ValueError, match="pending"):
        reward_statistics(rows, evidence, scores, [0.] * 4, 4)


def test_final_evaluation_uses_original_c_and_d6():
    """查询C全过但D6错仍失败，系统缺票保持null；汇总不使用训练reward。"""
    row = {"category": "T5", "labels": {"C-1": True, "C-2": True, "C-3": True, "C-4": True}, "d6": "错"}
    assert final_success(row) is False
    row["d6"] = "system_failure"
    assert final_success(row) is None
    row["final_success"] = None
    summary = summarize([row], {})
    assert summary["pending_semantic_total"] == 1 and summary["full_success_total"] == 0
    assert summary["few_shot"] and "embedded" in summary["few_shot_mode"]
