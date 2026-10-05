"""维护GRPO唯一写入者状态、指标和进程身份，供独立只读页面读取。"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from runtime import helpers, read_json, write_json


def utc_now():
    """使用带时区时间，浏览器按用户本地时区显示。"""
    return datetime.now(timezone.utc).isoformat()


def process_identity(pid):
    """同时检查启动标识和非僵尸状态，避免PID被复用。"""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


def read_optional(path, fallback):
    """尚未生成状态时返回空状态，损坏的正式数据不静默吞掉。"""
    return read_json(path) if Path(path).exists() else fallback


def read_metrics(path):
    """只读取已完成的JSONL行，忽略正在追加的末尾半行。"""
    path = Path(path)
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if raw and not raw.endswith("\n"):
        lines = lines[:-1]
    return [json.loads(line) for line in lines if line.strip()]


class LiveProgress:
    """训练主进程独占写状态；监控与评测通过主进程报告进度。"""

    def __init__(self, run_dir, config):
        """初始化独立运行快照，未完成的任务不假报reward或成功率。"""
        self.run_dir = Path(run_dir)
        self.started = time.monotonic()
        self.state = {"status": "starting", "phase": "loading", "pid": os.getpid(), "process_identity": process_identity(os.getpid()), "started_at": utc_now(), "run_id": self.run_dir.name, "tasks_completed": 0, "tasks_total": config["train_tasks"], "trajectories_completed": 0, "trajectories_total": config["train_tasks"] * config["num_generations"], "groups_scored": 0, "global_step": 0, "max_steps": config["train_tasks"] // config["groups_per_update"], "optimizer_updates": 0, "evaluation_completed": 0, "evaluation_total": config["test_tasks"], "error": None, "recent_rewards": []}
        if config.get("training_entry") == "train_full.py":
            self.state.update(max_steps=config["max_updates"], candidate_groups=0, candidate_budget=config["candidate_group_budget"], trajectories_total=config["candidate_group_budget"] * config["num_generations"], selected_trajectories=0, skipped_windows=0)
        helpers.atomic_text(self.run_dir / "metrics.md", "# metrics.jsonl 中文说明\n\n每个更新批次的真实奖励、优势信号、loss/KL、显存和耗时；评测条目另存。\n")
        self.update()

    def update(self, **values):
        """原子落盘JSON与同名说明，不让浏览器读到一半状态。"""
        self.state.update(values)
        self.state.update(updated_at=utc_now(), elapsed_seconds=round(time.monotonic() - self.started, 3))
        write_json(self.run_dir / "training_status.json", self.state)

    def log(self, metrics):
        """逐更新追加真实历史，页面曲线不使用合成训练数据。"""
        row = {"timestamp": utc_now(), **metrics}
        with (self.run_dir / "metrics.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        self.update(**metrics)
