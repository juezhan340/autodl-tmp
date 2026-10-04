"""提供无训练控制接口的只读HTTP监控服务，不加载模型或占用CUDA。"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from common import HERE, digest, load_config, read_json
from progress import process_identity, utc_now


def read_optional(path: Path, fallback):
    """读取可选状态文件，训练尚未落盘时返回明确空状态。"""
    return read_json(path) if path.exists() else fallback


def read_metrics(path: Path) -> list[dict]:
    """容忍正在追加的最后半行，已完成行损坏则明确报错。"""
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if raw and not raw.endswith("\n"):
        lines = lines[:-1]
    return [json.loads(line) for line in lines if line.strip()]


class GPUReader:
    """缓存nvidia-smi结果，避免多浏览器每次轮询都新建查询进程。"""

    def __init__(self):
        """建立线程安全缓存，服务本身不导入PyTorch。"""
        self.lock = threading.Lock()
        self.updated = 0.0
        self.value = {"available": False}

    def read(self) -> dict:
        """最多每5秒查询一次第一张卡，查询失败不阻断训练页面。"""
        with self.lock:
            if time.monotonic() - self.updated >= 5:
                try:
                    result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=2, check=True)
                    name, used, total, utilization, temperature = [part.strip() for part in result.stdout.splitlines()[0].split(",")]
                    self.value = {"available": True, "name": name, "used_mib": float(used), "total_mib": float(total), "utilization": float(utilization), "temperature": float(temperature)}
                except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                    self.value = {"available": False}
                self.updated = time.monotonic()
            return dict(self.value)


def snapshot(config: dict, gpu: dict, run_dir: Path | None = None) -> dict:
    """只投影正式运行的公开统计，历史smoke不能冒充当前训练。"""
    root = Path(config["output_root"])
    run = run_dir or root / "sft-main"
    status = read_optional(run / "training_status.json", {"status": "not_started", "phase": "waiting", "epoch": 0, "global_step": 0, "max_steps": 0, "elapsed_seconds": 0})
    status = dict(status)
    if status["status"] in ("starting", "running"):
        alive = process_identity(int(status["pid"]))
        if alive is None or alive != status.get("process_identity"):
            status["status"] = "interrupted"
            status["error"] = "训练进程已退出，最后一次状态保留。"
    public_keys = ("status", "phase", "epoch", "global_step", "max_steps", "elapsed_seconds", "started_at", "updated_at", "loss", "eval_loss", "learning_rate", "grad_norm", "error", "gpu_allocated_mib", "gpu_reserved_mib", "gpu_peak_allocated_mib", "best_checkpoint", "selected_adapter")
    manifest = read_optional(root / "data/manifest.json", {})
    checkpoints = []
    best = status.get("best_checkpoint")
    for row in read_optional(run / "checkpoint_index.json", []):
        name = Path(row["path"]).name
        checkpoints.append({"name": name, "epoch": row["epoch"], "global_step": row["global_step"], "adapter_sha256": row.get("adapter_sha256", ""), "best": name == best})
    return {
        "server_time": utc_now(), "poll_seconds": 3, "run_id": run.name,
        "model": Path(config["base_model"]).parent.name,
        "config": {key: config[key] for key in ("epochs", "micro_batch_size", "gradient_accumulation_steps", "max_length", "learning_rate", "lora_r")},
        "effective_batch": config["micro_batch_size"] * config["gradient_accumulation_steps"],
        "data": {name: {"count": config[key] * 5, "per_category": config[key]} for name, key in (("train", "train_per_category"), ("validation", "validation_per_category"), ("test", "test_per_category"))},
        "data_prepared": manifest.get("provenance", {}).get("config_sha256") == digest(config),
        "training": {key: status[key] for key in public_keys if key in status},
        "metrics": read_metrics(run / "metrics.jsonl"), "checkpoints": checkpoints, "gpu": gpu,
    }


def make_handler(config: dict, run_dir: Path | None = None):
    """固定白名单路由，禁止浏览仓库、下载模型或发起训练。"""
    gpu = GPUReader()

    class MonitorHandler(BaseHTTPRequestHandler):
        """处理静态页面及只读状态API，其他路径全部拒绝。"""

        def send_payload(self, code: int, body: bytes, content_type: str) -> None:
            """统一设置长度与禁缓存响应头，避免陈旧进度和目录暴露。"""
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            """页面与状态均使用相对地址，兼容6008端口的公网HTTPS代理。"""
            path = self.path.split("?", 1)[0]
            try:
                if path in ("/", "/dashboard.html"):
                    self.send_payload(200, (HERE / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/status":
                    body = json.dumps(snapshot(config, gpu.read(), run_dir), ensure_ascii=False).encode("utf-8")
                    self.send_payload(200, body, "application/json; charset=utf-8")
                elif path == "/healthz":
                    self.send_payload(200, b'{"service":"sft-monitor","status":"ok"}', "application/json")
                else:
                    self.send_payload(404, b"Not found", "text/plain")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.send_payload(503, json.dumps({"error": type(exc).__name__}).encode(), "application/json")

        def do_POST(self):
            """页面不提供任何写操作，训练启动必须经过命令行确认。"""
            self.send_payload(405, b"Read only", "text/plain")

        def do_HEAD(self):
            """支持平台健康探测，使用同一路由和响应头但不发送正文。"""
            self.do_GET()

        def log_message(self, format, *args):
            """省略轮询访问噪音，错误信息仍通过HTTP状态返回。"""
            return

    return MonitorHandler


def main() -> None:
    """监听用户可转发的6008端口；独立后台启动由launch.py负责。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6008)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(load_config(args.config)))
    print(f"sft-monitor listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
