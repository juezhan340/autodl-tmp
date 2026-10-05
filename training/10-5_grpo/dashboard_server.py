"""在6008提供GRPO只读工作台，读取运行状态，不导入模型或暴露轨迹和密钥。"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from runtime import HERE, load_config
from live import process_identity, read_metrics, read_optional, utc_now


class GPUReader:
    """缓存显卡读数并跟踪NVML观测峰值，避免每个浏览器重复查卡。"""

    def __init__(self):
        """服务不使用CUDA，只读nvidia-smi；峰值是采样观测而非连续精确峰值。"""
        self.lock = threading.Lock()
        self.updated = 0.0
        self.peak = 0.0
        self.value = {"available": False}

    def read(self):
        """每3秒最多查询一次；GPU查询失败仍允许显示训练状态。"""
        with self.lock:
            if time.monotonic() - self.updated >= 3:
                try:
                    result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True, timeout=3)
                    name, used, total, utilization, temperature = [part.strip() for part in result.stdout.splitlines()[0].split(",")]
                    self.peak = max(self.peak, float(used))
                    self.value = {"available": True, "name": name, "used_mib": float(used), "total_mib": float(total), "utilization": float(utilization), "temperature": float(temperature), "observed_peak_mib": self.peak}
                except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                    self.value = {"available": False}
                self.updated = time.monotonic()
            return dict(self.value)


def snapshot(config, gpu):
    """只公开聚合指标，历史冒烟和原始工具参数不会进入公网页面。"""
    root = Path(config["output_root"])
    active = read_optional(root / "active_run.json", {})
    run = Path(active["run_dir"]) if active.get("run_dir") else None
    if run:
        config = read_optional(run / "run_config.json", {}).get("config", config)
    status = read_optional(run / "training_status.json", {"status": "not_started", "phase": "waiting"}) if run else {"status": "not_started", "phase": "waiting"}
    status = dict(status)
    if status["status"] in ("starting", "running") and process_identity(status.get("pid")) != status.get("process_identity"):
        status.update(status="interrupted", error="训练进程已退出，保留最后状态。")
    public = {key: value for key, value in status.items() if key not in ("pid", "process_identity")}
    public_config = {key: config[key] for key in ("micro_batch", "accumulation", "num_generations", "rollout_parallel", "groups_per_update", "train_tasks", "test_tasks", "max_length", "learning_rate", "beta")}
    public_config["stage_label"] = config.get("stage_label", "第一阶段 · 100任务")
    return {"server_time": utc_now(), "config": public_config, "training": public, "metrics": read_metrics(run / "metrics.jsonl") if run else [], "checkpoints": read_optional(run / "checkpoint_index.json", []) if run else [], "evaluation": read_optional(run / "evaluation/comparison.json", {}) if run else {}, "gpu": gpu}


def make_handler(config):
    """仅开放页面、状态和健康检查，禁止写操作和文件系统浏览。"""
    reader = GPUReader()

    class DashboardHandler(BaseHTTPRequestHandler):
        """通过相对API路径兼容平台HTTPS转发。"""

        def send_payload(self, code, body, kind):
            """设置禁缓存和只读安全头，HTML不加载外部资源。"""
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            """白名单路由不把配置密钥或Scenario投影到公网。"""
            try:
                path = self.path.split("?", 1)[0]
                if path in ("/", "/dashboard.html"):
                    self.send_payload(200, (HERE / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/status":
                    self.send_payload(200, json.dumps(snapshot(config, reader.read()), ensure_ascii=False, allow_nan=False).encode(), "application/json; charset=utf-8")
                elif path == "/healthz":
                    self.send_payload(200, b'{"service":"grpo-monitor","status":"ok"}', "application/json")
                else:
                    self.send_payload(404, b"Not found", "text/plain")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.send_payload(503, json.dumps({"error": type(exc).__name__}).encode(), "application/json")

        def do_HEAD(self):
            """平台健康检查使用相同响应头，不发送正文。"""
            self.do_GET()

        def do_POST(self):
            """页面不能启动、停止或改写训练。"""
            self.send_payload(405, b"Read only", "text/plain")

        def log_message(self, format, *args):
            """关闭轮询噪音，失败由HTTP状态和后台日志记录。"""
            return

    return DashboardHandler


def main():
    """监听6008，由start.py以独立会话启动。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(HERE / "stage1_config.json"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6008)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(load_config(args.config)))
    print(f"grpo-monitor listening on {args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
