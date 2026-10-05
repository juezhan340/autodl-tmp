"""独立评测已经保存的冻结checkpoint，不改训练状态或打断反馈复访。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime import HERE, REPO_ROOT, file_sha256, read_json, write_json
from live import LiveProgress, process_identity, utc_now


def evaluate(training_run, checkpoint_name, output):
    """用原固定200任务和C+D6协议评测，所有状态写独立目录。"""
    from evaluate_stage import run_evaluation
    training_run, output = Path(training_run).resolve(), Path(output).resolve()
    if checkpoint_name not in ("checkpoint-coverage500", "checkpoint-update032", "checkpoint-full500"):
        raise ValueError("checkpoint must be a saved formal milestone")
    checkpoint = training_run / checkpoint_name
    saved = read_json(checkpoint / "stage_state.json")
    adapter = checkpoint / "policy"
    source = adapter / "adapter_model.safetensors"
    before = file_sha256(source)
    config = read_json(training_run / "run_config.json")["config"]
    config = {**config, "stage_label": f"GRPO {checkpoint_name} step{saved['optimizer_updates']}", "evaluation_name": "frozen_checkpoint"}
    write_json(output / "run_config.json", {"config": config, "mode": "frozen_checkpoint_evaluation", "training_run": str(training_run), "checkpoint_name": checkpoint_name, "checkpoint_step": saved["optimizer_updates"], "adapter_file_sha256": before, "started_at": utc_now(), "training_status_modified": False})
    progress = LiveProgress(output, config)
    progress.update(status="running", phase="evaluation", source_checkpoint_step=saved["optimizer_updates"])
    try:
        result = run_evaluation(config, output, adapter, progress)
        unchanged = file_sha256(source) == before
        if not unchanged:
            raise ValueError("frozen checkpoint changed during evaluation")
        write_json(output / "evaluation_report.json", {"status": result["status"], "checkpoint_step": saved["optimizer_updates"], "checkpoint_unchanged": unchanged, "training_interrupted": False, "comparison": str(output / "evaluation/comparison.json")})
        progress.update(status="completed", phase="completed", checkpoint_unchanged=True)
        print({"phase": "evaluation_completed", "models": {name: row["full_success_total"] for name, row in result["models"].items()}, "pending": progress.state.get("evaluation_pending_semantic", 0)}, flush=True)
    except BaseException as exc:
        write_json(output / "failure.json", {"error_type": type(exc).__name__, "message": str(exc), "training_interrupted": False})
        progress.update(status="failed", phase="failed", error=str(exc))
        raise


def main():
    """显式确认后独立启动收费200评测，后台模式与对话解耦。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--checkpoint", default="checkpoint-coverage500")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--detach", action="store_true")
    parser.add_argument("--confirm-api-review", action="store_true")
    args = parser.parse_args()
    if not args.confirm_api_review:
        raise ValueError("fixed 200-task evaluation with paid D6 requires confirmation")
    if args.output:
        output = args.output.resolve()
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = args.training_run.resolve() / "checkpoint_evaluations" / (args.checkpoint + "-" + stamp)
    if args.detach:
        output.mkdir(parents=True, exist_ok=False)
        command = [sys.executable, "-u", str(HERE / "evaluate_checkpoint.py"), "--training-run", str(args.training_run.resolve()), "--checkpoint", args.checkpoint, "--output", str(output), "--confirm-api-review"]
        environment = {**os.environ, "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "PYTHONUNBUFFERED": "1"}
        with (output / "evaluate.log").open("ab") as log:
            process = subprocess.Popen(command, cwd=REPO_ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        metadata = {"pid": process.pid, "process_identity": process_identity(process.pid), "started_at": utc_now(), "command": command, "output": str(output), "training_status_modified": False}
        write_json(output / "process.json", metadata)
        print(metadata, flush=True)
    else:
        evaluate(args.training_run, args.checkpoint, output)


if __name__ == "__main__":
    main()
