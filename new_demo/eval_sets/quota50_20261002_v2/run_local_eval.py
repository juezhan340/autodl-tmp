"""本地模型评测脚本：读评测任务集，按 workers 并发跑 C.run，输出 C-1..C-4 结果。"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from new_demo.agents.A_policy import DeepSeekPolicy
from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.eval.C_episode_runner import EpisodeRunner


def load_jsonl(path: str | Path) -> list[dict]:
    """读一行一个 JSON 对象的文件。"""
    rows: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_env(path: Path, base_url: str, model: str) -> None:
    """写一份指向本地 OpenAI 兼容服务的配置。"""
    text = "\n".join(
        [
            "DEEPSEEK_API_KEY=local",
            f"DEEPSEEK_BASE_URL={base_url}",
            f"DEEPSEEK_MODEL={model}",
            f"DEEPSEEK_A_MODEL={model}",
            "DEEPSEEK_TIMEOUT=900",
            "DEEPSEEK_MAX_RETRIES=1",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def build_scenario(task_row: dict, gold_row: dict, max_turns: int) -> dict:
    """把任务行与答案行拼回 C.run 的 Scenario，并按需覆盖轮次上限。"""
    return {
        "scenario_id": task_row["task_id"],
        "blueprint_id": task_row["reference_blueprint_id"],
        "home": task_row["home"],
        "user_request": task_row["user_request"],
        "task": gold_row["task"],
        "episode_config": {"max_turns": max_turns, "max_tool_calls_per_turn": 1},
    }


def run_one(
    task_row: dict,
    gold_row: dict,
    client: DeepSeekClient,
    args: argparse.Namespace,
    out_dir: Path,
    lock: threading.Lock,
) -> dict:
    """跑一条任务，结果与轨迹各自追加落盘；单条失败不影响整批。"""
    scenario = build_scenario(task_row, gold_row, args.max_turns)
    started = time.time()
    row: dict = {"task_id": task_row["task_id"], "category": task_row["category"]}
    try:
        result = EpisodeRunner(DeepSeekPolicy(client)).run(scenario)
        record = result.record
        row.update(
            {
                "labels": result.labels.to_dict(),
                "turn_count": record.get("protocol", {}).get("turn_count"),
                "finish": record.get("finish"),
                "elapsed_sec": round(time.time() - started, 1),
            }
        )
        with lock:
            with (out_dir / "results.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            with (out_dir / "trajectories.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {"scenario": scenario, "record": record, "labels": result.labels.to_dict()},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except Exception as exc:  # 记录异常，不中断并发队列
        row.update({"error": f"{type(exc).__name__}: {exc}", "elapsed_sec": round(time.time() - started, 1)})
        with lock:
            with (out_dir / "results.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"done {row['task_id']} {row.get('labels') or row.get('error')}", flush=True)
    return row


def main() -> None:
    """解析参数，按 task_id 选任务并并发执行。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:18080")
    parser.add_argument("--model", default="qwen2.5-1.5b-instruct")
    parser.add_argument("--tasks-file", default=str(Path(__file__).with_name("tasks.jsonl")))
    parser.add_argument("--ground-truth", default=str(Path(__file__).with_name("ground_truth.jsonl")))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--task-ids", default="", help="逗号分隔，只跑这些任务")
    args = parser.parse_args()

    tasks = load_jsonl(args.tasks_file)
    golds = {row["task_id"]: row for row in load_jsonl(args.ground_truth)}
    if args.task_ids:
        wanted = [item.strip() for item in args.task_ids.split(",") if item.strip()]
        tasks = [row for row in tasks if row["task_id"] in wanted]
    elif args.limit:
        tasks = tasks[: args.limit]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_env(out_dir / "local_model.env", args.server, args.model)
    client = DeepSeekClient(env_path=out_dir / "local_model.env", raw_dir=out_dir / "api")
    for name in ("results.jsonl", "trajectories.jsonl"):
        (out_dir / name).write_text("", encoding="utf-8")

    lock = threading.Lock()
    started = time.time()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(run_one, task, golds[task["task_id"]], client, args, out_dir, lock)
            for task in tasks
        ]
        for future in as_completed(futures):
            rows.append(future.result())

    passed = [
        row
        for row in rows
        if all((row.get("labels") or {}).get(key) is True for key in ("C-1", "C-2", "C-3", "C-4"))
    ]
    summary = {
        "tasks": len(tasks),
        "c_all_pass": len(passed),
        "errors": sum(1 for row in rows if "error" in row),
        "elapsed_sec": round(time.time() - started, 1),
        "workers": args.workers,
        "max_turns": args.max_turns,
        "server": args.server,
        "model": args.model,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
