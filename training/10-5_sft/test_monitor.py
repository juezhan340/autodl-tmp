"""验证实时状态、只读接口、进程身份和独立启动确认，测试不训练模型。"""

from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from common import HERE, atomic_text, load_config, read_json, write_json
from launch import build_command, read_health
from monitor import make_handler, read_metrics, snapshot
from progress import TrainingProgress, make_progress_callback, process_identity


@pytest.fixture
def config(tmp_path):
    """将状态写到独立临时目录，不修改正式训练产物。"""
    config = load_config()
    config["output_root"] = str(tmp_path)
    return config


def test_waiting_ignores_historical_smoke(config):
    """旧冒烟训练不应成为正式训练的当前进度。"""
    write_json(Path(config["output_root"]) / "smoke-old/training_status.json", {"status": "completed"})
    data = snapshot(config, {"available": False})
    assert data["training"]["status"] == "not_started"
    assert data["metrics"] == [] and data["checkpoints"] == []
    assert data["config"]["micro_batch_size"] == 4
    assert data["config"]["gradient_accumulation_steps"] == 2
    assert data["effective_batch"] == 8


def test_progress_callback_writes_live_metrics(config):
    """无需CUDA即可模拟官方回调，证明每step状态和loss真实落盘。"""
    run = Path(config["output_root"]) / "sft-main"
    progress = TrainingProgress(run, config, "train")
    callback = make_progress_callback(progress)
    state = SimpleNamespace(epoch=0.016, global_step=1, max_steps=189)
    callback.on_train_begin(None, state, None)
    callback.on_step_end(None, state, None)
    callback.on_log(None, state, None, logs={"loss": 0.37, "learning_rate": 0.00001})
    data = snapshot(config, {"available": False})
    assert data["training"]["status"] == "running"
    assert data["training"]["global_step"] == 1
    assert data["training"]["loss"] == 0.37
    assert data["metrics"][0]["loss"] == 0.37
    assert (run / "training_status.md").exists()
    assert (run / "metrics.md").exists()


def test_incomplete_metric_tail_is_ignored(tmp_path):
    """最后一行正在写入时保留完整历史，但不吞掉完整坏行。"""
    path = tmp_path / "metrics.jsonl"
    atomic_text(path, '{"loss":0.3}\n{"loss":')
    assert read_metrics(path) == [{"loss": 0.3}]
    atomic_text(path, '{"loss":0.3}\ninvalid\n')
    with pytest.raises(ValueError):
        read_metrics(path)


def test_non_finite_metric_not_written(config):
    """NaN不会进入状态API，使整页JSON解析失败。"""
    progress = TrainingProgress(Path(config["output_root"]) / "sft-main", config, "train")
    progress.log(SimpleNamespace(epoch=0.1, global_step=1), {"grad_norm": float("nan"), "loss": 0.5})
    assert "grad_norm" not in read_metrics(progress.metrics_path)[0]


def test_pid_reuse_is_interrupted(config):
    """PID仍在但启动标识不同也必须显示中断。"""
    run = Path(config["output_root"]) / "sft-main"
    write_json(run / "training_status.json", {"status": "running", "pid": os.getpid(), "process_identity": "not-this-process"})
    assert snapshot(config, {})["training"]["status"] == "interrupted"


def test_checkpoint_public_projection(config):
    """页面保留所有epoch，且不返回原始绝对路径。"""
    run = Path(config["output_root"]) / "sft-main"
    write_json(run / "training_status.json", {"status": "completed", "best_checkpoint": "checkpoint-126"})
    write_json(run / "checkpoint_index.json", [{"path": str(run / f"checkpoint-{epoch*63}"), "epoch": epoch, "global_step": epoch*63, "adapter_sha256": "a"*64} for epoch in (1, 2, 3)])
    data = snapshot(config, {})
    assert len(data["checkpoints"]) == 3
    assert data["checkpoints"][1]["best"] is True
    assert all("path" not in row for row in data["checkpoints"])


def test_read_only_http_routes(config):
    """真实HTTP请求验证页面、状态及拒绝写入与任意文件路径。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/") as response:
            assert "SFT / TRAINING" in response.read().decode()
        with urlopen(base + "/api/status") as response:
            assert json.loads(response.read())["training"]["status"] == "not_started"
        with urlopen(Request(base + "/healthz", method="HEAD")) as response:
            assert response.status == 200 and response.read() == b""
        for path in ("/../config.json", "/.env.deepseek", "/api/train"):
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/api/train", data=b"{}", method="POST"))
        assert error.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_launch_defaults_to_monitor_without_train():
    """展示进程命令不包含训练入口或完整训练确认。"""
    command = build_command("dashboard", HERE / "config.json")
    assert str(HERE / "monitor.py") in command
    assert "--confirm-full-training" not in command
    assert command[-1] == "6008"


def test_background_training_still_requires_confirmation():
    """后台启动不能绕过完整训练确认开关。"""
    with pytest.raises(ValueError, match="confirm-full-training"):
        build_command("train", HERE / "config.json")
    command = build_command("train", HERE / "config.json", confirmed=True)
    assert "--confirm-full-training" in command


def test_process_identity_and_service_health():
    """进程身份与健康响应可验证，其他服务不能通过识别。"""
    assert process_identity(os.getpid()) is not None
    assert process_identity(999999999) is None
    assert read_health(b'{"service":"sft-monitor"}')
    assert not read_health(b'{"service":"another"}')
    assert not read_health(b'not json')
