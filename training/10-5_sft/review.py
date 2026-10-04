"""并发补审已有轨迹的D6三票，不加载本地模型，也不修改原始程序评测。"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from common import CATEGORIES, REPO_ROOT, atomic_text, digest, file_sha256, read_json, read_jsonl, write_json, write_jsonl
from evaluate import final_success
from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.D6_judge import judge_one
from new_demo.env.B_models import copy_json

MODELS = ("baseline", "epoch1", "epoch2", "epoch3")


class CountedClient(DeepSeekClient):
    """仅统计实际HTTP尝试数，不记录请求头、API key或完整请求体。"""

    def __init__(self, env_path: Path, raw_dir: Path):
        """沿用项目客户端的模型、温度、超时和重试配置。"""
        super().__init__(env_path=env_path, raw_dir=raw_dir)
        self.attempt_lock = threading.Lock()
        self.http_attempts = 0

    def _post(self, payload):
        """把网络重试也计入实际发包数，随后交给原客户端发送。"""
        with self.attempt_lock:
            self.http_attempts += 1
        return super()._post(payload)


def needs_review(row: dict) -> bool:
    """仅审C四项全过、T3/T4/T5且仍待审的轨迹。"""
    return row["category"] in ("T3", "T4", "T5") and row.get("d6") == "待审" and all(row["labels"].get(key) is True for key in ("C-1", "C-2", "C-3", "C-4"))


def summarize(rows: list[dict], original: dict) -> dict:
    """保留原生成统计，重新计算C+D6完整成功率与系统待确认数量。"""
    result = dict(original)
    per_class = {}
    for category in CATEGORIES:
        subset = [row for row in rows if row["category"] == category]
        per_class[category] = {
            "total": len(subset),
            "program_success": sum(all(row["labels"].values()) for row in subset),
            "final_success": sum(row["final_success"] is True for row in subset),
            "pending_semantic": sum(row["final_success"] is None for row in subset),
            "d6_wrong": sum(row.get("d6") == "错" for row in subset),
            "d6_system_failure": sum(row.get("d6") == "system_failure" for row in subset),
            "c_failures": dict(Counter(key for row in subset for key, passed in row["labels"].items() if not passed)),
        }
    result.update(semantic_judge="deepseek", semantic_review="posthoc_existing_trajectories", per_category=per_class)
    result["full_success_total"] = sum(row["final_success"] is True for row in rows)
    result["full_success_rate"] = result["full_success_total"] / len(rows)
    result["pending_semantic_total"] = sum(row["final_success"] is None for row in rows)
    return result


def review_job(model: str, row: dict, client: DeepSeekClient) -> dict:
    """一条任务依次投三票，线程池最多允许workers条任务同时调用API。"""
    reviewed = judge_one(copy_json(row), client)
    if reviewed["record"] != row["record"] or reviewed["labels"] != row["labels"] or reviewed["scenario"] != row["scenario"]:
        raise ValueError("semantic review modified source trajectory")
    return {"model": model, "sample_id": row["sample_id"], "source_row_sha256": digest(row), "d6": reviewed["d6"], "d6_votes": reviewed["d6_votes"], "completed_at": datetime.now(timezone.utc).isoformat()}


def load_cache(path: Path, sources: dict) -> dict:
    """恢复只读取完整缓存行，发现源轨迹版本不一致立即报错。"""
    cached = {}
    if not path.exists():
        return cached
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if raw and not raw.endswith("\n"):
        lines = lines[:-1]
        atomic_text(path, "\n".join(lines) + ("\n" if lines else ""))
    for line in lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        key = (entry["model"], entry["sample_id"])
        if key not in sources or digest(sources[key]) != entry["source_row_sha256"]:
            raise ValueError("cached semantic verdict has a different source trajectory")
        cached[key] = entry
    return cached


def run_review(source: Path, env_path: Path, workers: int, confirmed: bool, retry_system_failures: bool = False) -> dict:
    """收费API必须明确确认；产物独立保存，已完成的三票结果可以恢复。"""
    if not confirmed:
        raise ValueError("API review requires --confirm-api-review")
    if not 1 <= workers <= 100:
        raise ValueError("workers must be between 1 and 100")
    source = source.resolve()
    output = source / "semantic_review"
    client = CountedClient(env_path.resolve(), output / "api")
    if not client.api_key:
        raise ValueError("DeepSeek API key is not configured")
    rows_by_model = {name: read_jsonl(source / name / "trajectories.jsonl") for name in MODELS}
    sources = {(name, row["sample_id"]): row for name, rows in rows_by_model.items() for row in rows}
    if len(sources) != sum(len(rows) for rows in rows_by_model.values()):
        raise ValueError("duplicate model/sample ids")
    protocol = {
        "source_sha256": {name: file_sha256(source / name / "trajectories.jsonl") for name in MODELS},
        "external_model": client.external_model,
        "external_temperature": client.external_temperature,
        "api_host": urlsplit(client.base_url).hostname,
        "judge_source_sha256": file_sha256(REPO_ROOT / "new_demo/data/D6_judge.py"),
        "prompt_sha256": {category: file_sha256(REPO_ROOT / f"new_demo/data_static/D0_templates/D6_{category}.md") for category in ("T3", "T4", "T5")},
    }
    manifest_path = output / "review_manifest.json"
    if manifest_path.exists() and read_json(manifest_path) != protocol:
        raise ValueError("semantic review source or judge configuration changed")
    write_json(manifest_path, protocol)
    cache_path = output / "review_cache.jsonl"
    atomic_text(cache_path.with_suffix(".md"), "# review_cache.jsonl 中文说明\n\n每行保存模型、sample_id、原始行指纹、三票结果及时间，用于中断恢复。原始record、scenario和C标签均不修改。system_failure不算错；只有显式retry-system-failures才重投。\n")
    atomic_text(output / "api/completions.md", "# completions.jsonl 中文说明\n\n项目DeepSeek客户端记录的投票正文、request_id、模型、usage与延迟；不记录API key、请求头或完整输入。\n")
    atomic_text(output / "api/errors.md", "# errors.jsonl 中文说明\n\nAPI最终失败的request_id、错误码和非敏感错误信息；传输重试次数另计入review_summary。\n")
    cached = load_cache(cache_path, sources)
    eligible = [(name, row) for name, rows in rows_by_model.items() for row in rows if needs_review(row)]
    jobs = [(name, row) for name, row in eligible if (name, row["sample_id"]) not in cached or (retry_system_failures and cached[(name, row["sample_id"])]["d6"] == "system_failure")]
    started = time.perf_counter()
    completed = 0
    progress_path = output / "review_status.json"
    write_json(progress_path, {"status": "running", "eligible_trajectories": len(eligible), "jobs_this_invocation": len(jobs), "workers": workers, "completed_this_invocation": 0})
    print({"eligible": len(eligible), "cached": len(cached), "queued": len(jobs), "workers": workers, "planned_logical_votes": len(jobs) * 3}, flush=True)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(review_job, name, row, client) for name, row in jobs]
            for future in as_completed(futures):
                entry = future.result()
                with cache_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                cached[(entry["model"], entry["sample_id"])] = entry
                completed += 1
                write_json(progress_path, {"status": "running", "eligible_trajectories": len(eligible), "jobs_this_invocation": len(jobs), "workers": workers, "completed_this_invocation": completed, "elapsed_seconds": round(time.perf_counter() - started, 3), "http_attempts_this_invocation": client.http_attempts})
                if completed % 20 == 0 or completed == len(jobs):
                    print({"completed": completed, "queued": len(jobs), "d6_verdicts": dict(Counter(value["d6"] for value in cached.values()))}, flush=True)
    except BaseException as exc:
        write_json(progress_path, {"status": "failed", "completed_this_invocation": completed, "error_type": type(exc).__name__})
        raise
    summaries = {}
    for name, rows in rows_by_model.items():
        reviewed_rows = []
        for row in rows:
            reviewed = copy_json(row)
            entry = cached.get((name, row["sample_id"]))
            if entry:
                reviewed.update(d6=entry["d6"], d6_votes=entry["d6_votes"])
            reviewed["final_success"] = final_success(reviewed, "deepseek")
            reviewed_rows.append(reviewed)
        write_jsonl(output / name / "trajectories.jsonl", reviewed_rows, "原始轨迹及C标签不变，仅补D6三票与完整成功判定。原始程序评测保留在上一级对应模型目录。")
        summaries[name] = summarize(reviewed_rows, read_json(source / name / "summary.json"))
        write_json(output / name / "summary.json", summaries[name])
    report = {"status": "completed", "eligible_trajectories": len(eligible), "jobs_this_invocation": len(jobs), "completed_this_invocation": completed, "workers": workers, "planned_logical_votes_this_invocation": len(jobs) * 3, "http_attempts_this_invocation": client.http_attempts, "elapsed_seconds": round(time.perf_counter() - started, 3), "semantic_verdicts": dict(Counter(entry["d6"] for entry in cached.values())), "models": summaries, "original_source_files_unchanged": all(file_sha256(source / name / "trajectories.jsonl") == value for name, value in protocol["source_sha256"].items()), "local_model_reloaded": False, "parameters_updated": False}
    if not report["original_source_files_unchanged"]:
        raise ValueError("source trajectories changed during review")
    write_json(output / "review_summary.json", report)
    write_json(progress_path, {key: value for key, value in report.items() if key != "models"})
    return report


def main() -> None:
    """根目录密钥显式传给客户端，默认100条待审任务并发。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--env-path", type=Path, default=REPO_ROOT / ".env.deepseek")
    parser.add_argument("--workers", type=int, default=100)
    parser.add_argument("--confirm-api-review", action="store_true")
    parser.add_argument("--retry-system-failures", action="store_true")
    args = parser.parse_args()
    result = run_review(args.source, args.env_path, args.workers, args.confirm_api_review, args.retry_system_failures)
    print({"status": result["status"], "models": {name: {key: summary[key] for key in ("full_success_total", "full_success_rate", "pending_semantic_total")} for name, summary in result["models"].items()}}, flush=True)


if __name__ == "__main__":
    main()
