"""持久化训练进度和指标，供独立监控页面只读轮询。"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from common import atomic_text, write_json


def utc_now() -> str:
    """生成带时区的更新时间，前端可以转换为浏览器本地时间。"""
    return datetime.now(timezone.utc).isoformat()


def process_identity(pid: int) -> str | None:
    """读取Linux进程启动标识并排除僵尸，避免复用PID误判存活。"""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


class TrainingProgress:
    """训练进程是状态文件与指标日志的唯一写入者。"""

    def __init__(self, run_dir: Path, config: dict, mode: str):
        """初始化本轮状态，恢复训练时保留已有指标而更新进程身份。"""
        self.run_dir = run_dir
        self.started = time.monotonic()
        self.status_path = run_dir / "training_status.json"
        self.metrics_path = run_dir / "metrics.jsonl"
        self.state = {
            "run_id": run_dir.name, "mode": mode, "status": "starting",
            "phase": "preparing", "pid": os.getpid(),
            "process_identity": process_identity(os.getpid()),
            "started_at": utc_now(), "updated_at": utc_now(),
            "epoch": 0, "global_step": 0, "max_steps": 0,
            "epochs": 2 if mode == "smoke" else config["epochs"],
            "micro_batch_size": config["micro_batch_size"],
            "gradient_accumulation_steps": 1 if mode == "smoke" else config["gradient_accumulation_steps"],
            "effective_batch": config["micro_batch_size"] * (1 if mode == "smoke" else config["gradient_accumulation_steps"]),
            "elapsed_seconds": 0, "checkpoint_count": 0, "error": None,
        }
        atomic_text(self.metrics_path.with_suffix(".md"), "# metrics.jsonl 中文说明\n\n训练进程逐次追加真实指标。每行包含时间、step、epoch，以及该次官方Trainer日志中的loss、eval_loss或learning_rate。恢复时保留历史行；同step的新日志按最新值展示。\n")
        self.update()

    def update(self, **values) -> None:
        """原子替换快照和中文说明，避免页面读取到半份JSON。"""
        self.state.update(values)
        self.state["updated_at"] = utc_now()
        self.state["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        write_json(self.status_path, self.state)

    def log(self, state, logs: dict) -> None:
        """追加Trainer真实日志，再将当前指标同步到状态快照。"""
        metrics = {key: value for key, value in logs.items() if isinstance(value, (int, float)) and math.isfinite(value)}
        row = {**metrics, "timestamp": utc_now(), "global_step": int(state.global_step), "epoch": float(state.epoch or 0)}
        with self.metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.update(**{key: value for key, value in metrics.items() if key in ("loss", "eval_loss", "learning_rate", "grad_norm")})


def make_progress_callback(progress: TrainingProgress):
    """使用官方Trainer回调记录每次优化器更新，不另写训练循环。"""
    from transformers import TrainerCallback

    class LiveProgress(TrainerCallback):
        """在训练、验证、保存之间维护可独立读取的状态。"""

        def on_train_begin(self, args, state, control, **kwargs):
            """记录真实总step，恢复时从已有global_step开始展示。"""
            progress.update(status="running", phase="training", max_steps=int(state.max_steps), global_step=int(state.global_step), epoch=float(state.epoch or 0))

        def on_step_end(self, args, state, control, **kwargs):
            """每个优化器更新后记录进度和PyTorch显存，不等待epoch结束。"""
            import torch
            memory = {}
            if torch.cuda.is_available():
                memory = {"gpu_allocated_mib": round(torch.cuda.memory_allocated() / 1024**2, 1), "gpu_reserved_mib": round(torch.cuda.memory_reserved() / 1024**2, 1), "gpu_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 1)}
            progress.update(status="running", phase="training", epoch=float(state.epoch or 0), global_step=int(state.global_step), max_steps=int(state.max_steps), **memory)

        def on_log(self, args, state, control, logs=None, **kwargs):
            """持久化loss和学习率，供页面绘制真实历史曲线。"""
            progress.log(state, logs or {})

        def on_prediction_step(self, args, state, control, **kwargs):
            """验证期间持续更新时间，避免较长验证被误认为卡住。"""
            progress.update(phase="evaluating")

        def on_evaluate(self, args, state, control, metrics=None, **kwargs):
            """验证结果由官方日志记录，此处标记进入epoch保存阶段。"""
            progress.update(phase="saving", epoch=float(state.epoch or 0))

        def on_save(self, args, state, control, **kwargs):
            """保存索引回调完成后更新已保留检查点数量。"""
            from common import read_json
            index = read_json(progress.run_dir / "checkpoint_index.json")
            progress.update(checkpoint_count=len(index), phase="training")

        def on_train_end(self, args, state, control, **kwargs):
            """Trainer结束后仍等待选定adapter落盘，暂不宣称全部完成。"""
            progress.update(phase="finalizing", epoch=float(state.epoch or 0), global_step=int(state.global_step))

    return LiveProgress()
