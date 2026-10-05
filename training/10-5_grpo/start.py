"""以独立会话启动GRPO监控或已获确认的第一阶段训练，避免绑定对话与SSH。"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from runtime import HERE, REPO_ROOT, load_config, read_json, write_json
from live import process_identity, utc_now


def build_command(service, config_path, port, run_dir=None, confirmed=False, api_confirmed=False):
    """显式确认训练与收费API；不提供隐式降micro或GPU冒烟分支。"""
    if service not in ("dashboard", "train"):
        raise ValueError("unknown service")
    if service == "train" and (not confirmed or not api_confirmed):
        raise ValueError("stage training and API review require explicit confirmations")
    entry = HERE / ("dashboard_server.py" if service == "dashboard" else "run_stage.py")
    command = [sys.executable, "-u", str(entry), "--config", str(config_path)]
    if service == "dashboard":
        command.extend(["--port", str(port), "--host", "0.0.0.0"])
    else:
        command.extend(["--run-dir", str(run_dir), "--confirm-stage-training", "--confirm-api-review"])
    return command


def launch(service, config_path, port=6008, confirmed=False, api_confirmed=False):
    """锁、PID启动身份和独立日志防止重复启动；返回真实进程信息。"""
    config_path = Path(config_path).resolve()
    config = load_config(config_path)
    root = Path(config["output_root"])
    services = root / "services"
    services.mkdir(parents=True, exist_ok=True)
    metadata_path = services / f"{service}.json"
    with (services / f"{service}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if metadata_path.exists():
            previous = read_json(metadata_path)
            if previous.get("process_identity") and process_identity(previous["pid"]) == previous["process_identity"]:
                raise ValueError(f"{service} is already running")
        run_dir = None
        if service == "train":
            if not confirmed or not api_confirmed:
                raise ValueError("both confirmations are required before creating a run")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            run_dir = root / (config["stage_name"] + "-" + stamp)
            run_dir.mkdir()
            write_json(root / "active_run.json", {"run_dir": str(run_dir), "created_at": utc_now()})
        command = build_command(service, config_path, port, run_dir, confirmed, api_confirmed)
        log_path = run_dir / "train.log" if run_dir else services / "dashboard.log"
        environment = dict(os.environ)
        environment.update(OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", PYTHONUNBUFFERED="1")
        with log_path.open("ab") as log:
            process = subprocess.Popen(command, cwd=REPO_ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        metadata = {"service": service, "pid": process.pid, "process_identity": process_identity(process.pid), "started_at": utc_now(), "command": command, "run_dir": str(run_dir) if run_dir else None, "log_path": str(log_path), "port": port if service == "dashboard" else None}
        write_json(metadata_path, metadata)
        if service == "dashboard":
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"dashboard exited; inspect {log_path}")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                        if json.loads(response.read()).get("service") == "grpo-monitor":
                            return metadata
                except OSError:
                    pass
                time.sleep(.1)
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError("dashboard health check timed out")
        time.sleep(.5)
        if process.poll() is not None:
            raise RuntimeError(f"training exited; inspect {log_path}")
        return metadata


def main():
    """默认仅启动监控，训练必须指定train和两项确认。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=("dashboard", "train"), nargs="?", default="dashboard")
    parser.add_argument("--config", default=str(HERE / "stage1_config.json"))
    parser.add_argument("--port", type=int, default=6008)
    parser.add_argument("--confirm-stage-training", action="store_true")
    parser.add_argument("--confirm-api-review", action="store_true")
    args = parser.parse_args()
    print(launch(args.service, args.config, args.port, args.confirm_stage_training, args.confirm_api_review))


if __name__ == "__main__":
    main()
