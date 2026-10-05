"""训练成功后复用原200任务生成评测，并用原D6三票与已有epoch3结果对照。"""

from __future__ import annotations

import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from runtime import HERE, REPO_ROOT, annotate_jsonl_tree, digest, file_sha256, read_json, read_jsonl, write_json, write_jsonl
from live import read_metrics
from new_demo.agents.DeepSeek_client import DeepSeekClient
from new_demo.data.D6_judge import judge_one


def final_success(row):
    """保持旧C+D6口径，语义系统失败仍待确认，不伪造成功或失败。"""
    if not all(row["labels"].get(key) is True for key in ("C-1", "C-2", "C-3", "C-4")):
        return False
    if row["category"] in ("T1", "T2"):
        return True
    if row.get("d6") not in ("对", "错"):
        return None
    return row["d6"] == "对"


def summarize(rows, original):
    """统计五类完整成功与待确认，训练奖励成功率不替代这个评测口径。"""
    result = dict(original)
    result.update(total=len(rows), full_success_total=sum(row["final_success"] is True for row in rows), pending_semantic_total=sum(row["final_success"] is None for row in rows), semantic_judge="deepseek_original_D6", few_shot=True, few_shot_mode="current_A_embedded_examples_no_extra_wrapper")
    result["full_success_rate"] = result["full_success_total"] / len(rows)
    result["per_category"] = {category: {"total": sum(row["category"] == category for row in rows), "program_success": sum(row["category"] == category and all(row["labels"].values()) for row in rows), "final_success": sum(row["category"] == category and row["final_success"] is True for row in rows), "pending_semantic": sum(row["category"] == category and row["final_success"] is None for row in rows)} for category in ("T1", "T2", "T3", "T4", "T5")}
    return result


def run_evaluation(config, run_dir, adapter, progress):
    """先完成200条greedy环境轨迹，再并发原D6评审；不在评测中更新参数。"""
    root = Path(run_dir) / "evaluation"
    output = root / "grpo_stage1"
    root.mkdir(parents=True, exist_ok=True)
    test = read_jsonl(Path(config["sft_data"]) / "test_scenarios.jsonl")
    baseline_root = Path(config["baseline_review"])
    baseline_rows = read_jsonl(baseline_root / "trajectories.jsonl")
    baseline_summary = read_json(baseline_root / "summary.json")
    if len(test) != 200 or {row["sample_id"]: digest(row["scenario"]) for row in test} != {row["sample_id"]: digest(row["scenario"]) for row in baseline_rows}:
        raise ValueError("evaluation is not the same fixed 200-task set")
    baseline_adapter = Path(baseline_summary["adapter"]) / "adapter_model.safetensors"
    if file_sha256(baseline_adapter) != file_sha256(Path(config["sft_adapter"]) / "adapter_model.safetensors"):
        raise ValueError("saved epoch3 baseline is not the SFT starting adapter")
    command = [sys.executable, "-u", str(HERE.parent / "10-5_sft/evaluate.py"), "--config", config["sft_eval_config"], "--split", "test", "--adapter", str(adapter), "--output", str(output), "--semantic-judge", "off", "--confirm-final-test"]
    write_json(root / "evaluation_protocol.json", {"test_tasks": 200, "test_sha256": digest(test), "command": command, "a_policy_sha256": file_sha256(REPO_ROOT / "new_demo/agents/A_policy.py"), "baseline_reused": str(baseline_root), "sampling": "greedy_same_as_previous_SFT_evaluation", "semantic": "original_D6_templates_three_votes", "parameters_updated": False})
    progress.update(phase="evaluation", evaluation_completed=0)
    with (root / "generation.log").open("ab") as log:
        process = subprocess.Popen(command, cwd=REPO_ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                rows = read_metrics(output / "trajectories.jsonl")
                progress.update(evaluation_completed=len(rows), evaluation_child_pid=process.pid)
                time.sleep(2)
            if process.returncode:
                raise RuntimeError(f"200-task generation exited {process.returncode}; inspect {root / 'generation.log'}")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    rows = read_jsonl(output / "trajectories.jsonl")
    if len(rows) != 200:
        raise ValueError("fixed evaluation did not finish all 200 tasks")
    original_hash = file_sha256(output / "trajectories.jsonl")
    eligible = [index for index, row in enumerate(rows) if row["category"] in ("T3", "T4", "T5") and all(row["labels"].values())]
    client = DeepSeekClient(env_path=REPO_ROOT / ".env.deepseek", raw_dir=root / "d6_api")
    if not client.api_key:
        raise ValueError("D6 key not configured")
    reviewed = list(rows)
    completed = 0
    progress.update(phase="evaluation_review", evaluation_completed=200, evaluation_review_completed=0, evaluation_review_total=len(eligible), judge_pending=len(eligible))
    with ThreadPoolExecutor(max_workers=config["evaluation_workers"]) as pool:
        futures = {pool.submit(judge_one, row, client): index for index, row in enumerate(rows) if index in eligible}
        for future in as_completed(futures):
            index = futures[future]
            item = future.result()
            if item["record"] != rows[index]["record"] or item["labels"] != rows[index]["labels"]:
                raise ValueError("D6 changed source trajectory")
            reviewed[index] = item
            completed += 1
            write_json(root / "d6_cache" / f"{item['sample_id']}.json", {"sample_id": item["sample_id"], "source_record_sha256": digest(item["record"]), "d6": item["d6"], "votes": item["d6_votes"]})
            progress.update(evaluation_review_completed=completed, judge_pending=len(eligible) - completed, api_errors=sum(row.get("d6") == "system_failure" for row in reviewed))
    for row in reviewed:
        row["final_success"] = final_success(row)
    write_jsonl(root / "reviewed_trajectories.jsonl", reviewed, "固定200原始轨迹及原D6三票；final_success=null保留系统待确认。")
    annotate_jsonl_tree(root / "d6_api")
    result = summarize(reviewed, read_json(output / "summary.json"))
    write_json(root / "grpo_summary.json", result)
    baseline = summarize(baseline_rows, baseline_summary)
    comparison = {"status": "completed" if not result["pending_semantic_total"] else "completed_with_pending", "test_tasks": 200, "models": {"SFT epoch3": baseline, "GRPO stage1": result}, "success_rate_change": result["full_success_rate"] - baseline["full_success_rate"], "improved_tasks": sum(old["final_success"] is not True and new["final_success"] is True for old, new in _align(baseline_rows, reviewed)), "regressed_tasks": sum(old["final_success"] is True and new["final_success"] is False for old, new in _align(baseline_rows, reviewed)), "raw_grpo_file_unchanged": file_sha256(output / "trajectories.jsonl") == original_hash, "semantic_verdicts": dict(Counter(row.get("d6") for row in reviewed))}
    if not comparison["raw_grpo_file_unchanged"]:
        raise ValueError("raw evaluation trajectories changed during D6")
    write_json(root / "comparison.json", comparison)
    progress.update(evaluation_status=comparison["status"], evaluation_pending_semantic=result["pending_semantic_total"], judge_pending=0)
    return comparison


def _align(baseline, current):
    """按sample_id对齐，不能假定两个评测文件顺序恰好一致。"""
    old = {row["sample_id"]: row for row in baseline}
    return [(old[row["sample_id"]], row) for row in current]
