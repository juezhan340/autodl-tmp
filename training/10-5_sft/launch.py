"""用独立会话启动页面或已获确认的训练，记录进程身份和独立日志。"""

from __future__ import annotations

import argparse
import fcntl
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from common import HERE, REPO_ROOT, load_config, read_json, write_json
from progress import process_identity, utc_now


def build_command(service: str, config_path: Path, port: int = 6008, confirmed: bool = False, resume: str | None = None) -> list[str]:
    """构造固定入口命令，完整训练在启动子进程前就要求确认。"""
    if service not in ("dashboard", "train"):
        raise ValueError("unknown service")
    if service == "train" and not confirmed:
        raise ValueError("training requires --confirm-full-training")
    if service == "dashboard" and resume:
        raise ValueError("dashboard cannot resume training")
    command = [sys.executable, "-u", str(HERE / ("monitor.py" if service == "dashboard" else "train.py")), "--config", str(config_path)]
    if service == "dashboard":
        command.extend(["--host", "0.0.0.0", "--port", str(port)])
    else:
        command.extend(["--mode", "train", "--confirm-full-training"])
        if resume:
            command.extend(["--resume-from-checkpoint", resume])
    return command


def launch_service(service: str, config_path: Path, port: int = 6008, confirmed: bool = False, resume: str | None = None) -> dict:
    """脱离终端启动服务，锁和PID身份共同防止重复拉起。"""
    config_path = config_path.resolve()
    command = build_command(service, config_path, port, confirmed, resume)
    config = load_config(config_path)
    services = Path(config["output_root"]) / "services"
    services.mkdir(parents=True, exist_ok=True)
    metadata_path = services / f"{service}.json"
    with (services / f"{service}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if metadata_path.exists():
            previous = read_json(metadata_path)
            if previous.get("process_identity") and process_identity(previous["pid"]) == previous["process_identity"]:
                raise ValueError(f"{service} is already running with pid {previous['pid']}")
        if service == "train" and (Path(config["output_root"]) / "sft-main").exists() and not resume:
            raise ValueError("run directory exists; use explicit checkpoint resume")
        log_path = services / f"{service}.log"
        with log_path.open("ab") as log:
            process = subprocess.Popen(command, cwd=REPO_ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        metadata = {"service": service, "pid": process.pid, "process_identity": process_identity(process.pid), "started_at": utc_now(), "command": command, "log_path": str(log_path), "port": port if service == "dashboard" else None}
        write_json(metadata_path, metadata)
        if service == "dashboard":
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"dashboard exited; inspect {log_path}")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                        if response.status == 200 and read_health(response.read()):
                            time.sleep(0.2)
                            if process.poll() is None:
                                return metadata
                except OSError:
                    pass
                time.sleep(0.1)
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError("dashboard health check timed out")
        time.sleep(0.5)
        if process.poll() is not None:
            raise RuntimeError(f"training process exited; inspect {log_path}")
        return metadata


def read_health(raw: bytes) -> bool:
    """辨认本项目健康接口，避免把已有其他服务误认成本次启动。"""
    import json
    try:
        return json.loads(raw).get("service") == "sft-monitor"
    except (ValueError, AttributeError):
        return False


def main() -> None:
    """默认仅启动展示服务，训练必须指定train及确认开关。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=("dashboard", "train"), nargs="?", default="dashboard")
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--port", type=int, default=6008)
    parser.add_argument("--confirm-full-training", action="store_true")
    parser.add_argument("--resume-from-checkpoint")
    args = parser.parse_args()
    print(launch_service(args.service, args.config, args.port, args.confirm_full_training, args.resume_from_checkpoint))


if __name__ == "__main__":
    main()
