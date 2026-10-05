"""执行已批准的100任务GRPO第一阶段，micro16累计1，成功后自动评测固定200任务。"""

from __future__ import annotations

import argparse
import gc
import math
import random
import statistics
import time
from collections import Counter
from pathlib import Path

from runtime import HERE, REPO_ROOT, annotate_json_tree, digest, file_sha256, load_config, read_jsonl, write_json, write_jsonl
from live import LiveProgress, utc_now
from model_math import activate, adapter_digest, load_model
from rollout import BatchService, HFBackend, generate_group, pack_calls
from trajectory import preprocess
from reward import assign_advantages, judge_rows, score
from smoke import memory_snapshot, precompute_logps, reset_memory, train_once

CATEGORIES = ("T1", "T2", "T3", "T4", "T5")


def select_stage_tasks(config):
    """五类各20项随机抽样再打乱；验证和测试group绝不进入训练。"""
    if config["train_tasks"] != 100 or config["tasks_per_category"] != 20 or config["test_tasks"] != 200:
        raise ValueError("this entry is restricted to 100 training tasks and 200 test tasks")
    if config["micro_batch"] != 16 or config["accumulation"] != 1:
        raise ValueError("approved stage requires micro16 accumulation1; no automatic fallback")
    root = Path(config["sft_data"])
    tasks = read_jsonl(root / "train_scenarios.jsonl")
    rng = random.Random(config["seed"])
    selected = []
    for category in CATEGORIES:
        candidates = [row for row in tasks if row["category"] == category]
        selected.extend(rng.sample(candidates, config["tasks_per_category"]))
    rng.shuffle(selected)
    forbidden = {row["group_id"] for split in ("validation", "test") for row in read_jsonl(root / f"{split}_scenarios.jsonl")}
    if len({row["group_id"] for row in selected}) != 100 or any(row["group_id"] in forbidden for row in selected):
        raise ValueError("training selection overlaps validation/test or repeats groups")
    return selected


def reward_statistics(rows, evidence, scores, advantages, generations):
    """聚合真实奖励与严格过程指标，安全覆盖分不伪造成各分项之和。"""
    rewards = [row["total_reward"] for row in scores]
    if any(value is None or not math.isfinite(value) for value in rewards):
        raise ValueError("pending reward cannot become a training metric")
    names = {name for row in scores for name in row["terms"]}
    tied = sum(all(abs(value) < 1e-10 for value in advantages[start:start + generations]) for start in range(0, len(rows), generations))
    return {"reward_mean": statistics.mean(rewards), "reward_min": min(rewards), "reward_max": max(rewards), "reward_std": statistics.pstdev(rewards), "reward_terms": {name: statistics.mean(row["terms"].get(name, 0.0) for row in scores) for name in names}, "success_rate": sum(row["terms"].get("success", 0) > 0 for row in scores) / len(rows), "false_finish_rate": sum(row["false_finish"] for row in evidence) / len(rows), "unsafe_rate": sum(bool(row["unsafe_events"]) for row in evidence) / len(rows), "budget_rate": sum(row["budget_exhausted"] for row in evidence) / len(rows), "ordinary_errors": sum(row["error_count"] for row in evidence), "tied_group_rate": tied / (len(rows) / generations), "recent_rewards": [{"sample_id": row["rollout_id"], "category": row["category"], "reward": scored["total_reward"], "errors": item["error_count"], "false_finish": item["false_finish"], "unsafe": bool(item["unsafe_events"])} for row, item, scored in zip(rows[-8:], evidence[-8:], scores[-8:])]}


def save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, name, selection, reference_hash):
    """只在阶段结束或非零更新后异常时保存可审计检查点，不逐批保存大权重。"""
    import torch
    destination = Path(run_dir) / name
    model.save_pretrained(destination, selected_adapters=["policy"])
    tokenizer.save_pretrained(destination / "policy")
    torch.save({"optimizer": optimizer.state_dict(), "torch_rng": torch.get_rng_state(), "cuda_rng": torch.cuda.get_rng_state_all(), "python_rng": random.getstate()}, destination / "training_state.pt")
    write_json(destination / "stage_state.json", {"config_sha256": digest(config), "selection_sha256": digest(selection), "global_step": progress.state["global_step"], "optimizer_updates": progress.state["optimizer_updates"], "reference_sha256": reference_hash, "policy_sha256": adapter_digest(model, "policy"), "saved_at": utc_now(), "automatic_resume_supported": False})
    annotate_json_tree(destination)
    write_json(Path(run_dir) / "checkpoint_index.json", [{"name": name, "adapter": str(destination / "policy"), "global_step": progress.state["global_step"], "optimizer_updates": progress.state["optimizer_updates"]}])
    return destination / "policy"


def train_stage(config, run_dir, progress):
    """25个新采样更新批次共享optimizer；OOM直接失败，保留真实证据。"""
    import torch
    from transformers import set_seed
    if not torch.cuda.is_available():
        raise ValueError("GPU unavailable")
    tasks = select_stage_tasks(config)
    write_json(run_dir / "selected_tasks.json", {"tasks": tasks, "counts": dict(Counter(row["category"] for row in tasks)), "selection_sha256": digest(tasks), "validation_test_overlap": False})
    set_seed(config["seed"])
    source_adapter = Path(config["sft_adapter"]) / "adapter_model.safetensors"
    source_hash = file_sha256(source_adapter)
    reset_memory()
    model, tokenizer = load_model(config)
    fixed_hash = adapter_digest(model, "sft_reference")
    if adapter_digest(model, "policy") != fixed_hash:
        raise ValueError("initial policy differs from SFT reference")
    activate(model, "policy")
    optimizer = torch.optim.AdamW([parameter for parameter in model.parameters() if parameter.requires_grad], lr=config["learning_rate"], weight_decay=0.0)
    overall_allocated = memory_snapshot()["allocated_peak_mib"]
    overall_reserved = memory_snapshot()["reserved_peak_mib"]
    progress.update(status="running", reference_unchanged=True, gpu_peak_allocated_mib=overall_allocated, gpu_peak_reserved_mib=overall_reserved)
    durations = []
    try:
        for start in range(0, len(tasks), config["groups_per_update"]):
            step = start // config["groups_per_update"] + 1
            directory = run_dir / "updates" / f"update-{step:03d}"
            started = time.perf_counter()
            batch_config = {**config, "group_namespace": f"stage1-update-{step:03d}"}
            backend = HFBackend(model, tokenizer, batch_config)
            service = BatchService(backend, config["rollout_parallel"])
            rows = []
            phases = {}
            progress.update(phase="rollout", current_batch=step, judge_pending=0)
            reset_memory()
            generation_started = time.perf_counter()
            try:
                for index, task in enumerate(tasks[start:start + config["groups_per_update"]]):
                    rows.extend(generate_group(task, service, tokenizer, batch_config))
                    write_jsonl(directory / "rollouts.jsonl", rows, "当前未更新policy的新采样轨迹、真实token和独立环境记录。")
                    progress.update(tasks_completed=start + index + 1, trajectories_completed=(start + index + 1) * config["num_generations"])
            finally:
                service.close()
            rollout_seconds = time.perf_counter() - generation_started
            phases["rollout"] = memory_snapshot()
            write_json(directory / "generation_batches.json", backend.batches)
            if any(row["infrastructure_errors"] for row in rows):
                raise ValueError("rollout infrastructure failure; no reward or update")
            packed = [pack_calls(row["calls"], config["max_length"]) for row in rows]
            evidence = [preprocess(row) for row in rows]
            write_jsonl(directory / "packed_trajectories.jsonl", packed, "完整历史可见，真实采样token参与策略loss。")
            write_jsonl(directory / "evidence.jsonl", evidence, "目标、取证、错误、结束与安全的逐步重放证据。")
            progress.update(phase="reward", judge_pending=len(rows))

            def review_progress(values):
                """主线程按已完成评审数量更新页面，不把待审奖励置零。"""
                progress.update(judge_pending=values["total"] - values["completed"], api_errors=values["errors"], http_attempts_current_batch=values["http_attempts"])

            semantic = judge_rows(rows, directory / "finish_review", REPO_ROOT / ".env.deepseek", config["judge_workers"], progress_callback=review_progress)
            scores = [score(item, verdict, config) for item, verdict in zip(evidence, semantic)]
            write_jsonl(directory / "rewards.jsonl", scores, "r2各分项与总分；待审组禁止更新。")
            advantages = assign_advantages(rows, scores, config["num_generations"])
            write_json(directory / "advantages.json", {row["rollout_id"]: value for row, value in zip(rows, advantages)})
            stats = reward_statistics(rows, evidence, scores, advantages, config["num_generations"])
            progress.update(**stats, groups_scored=start + config["groups_per_update"], judge_pending=0)
            reset_memory()
            progress.update(phase="logprobs")
            old, reference, delta = precompute_logps(model, packed, tokenizer, config, require_initial_equal=progress.state["optimizer_updates"] == 0)
            phases["old_reference_logps"] = memory_snapshot()
            torch.save({"old": old, "reference": reference}, directory / "sampled_logprobs.pt")
            reset_memory()
            progress.update(phase="backward")
            update = train_once(model, packed, old, reference, advantages, tokenizer, config, directory, optimizer=optimizer, save_checkpoint=False)
            phases["train_forward_backward_step"] = memory_snapshot()
            if adapter_digest(model, "sft_reference") != fixed_hash or file_sha256(source_adapter) != source_hash:
                raise ValueError("fixed reference or source SFT changed")
            if update["micro_batches"] != 1:
                raise ValueError("micro16 accumulation1 was not honored")
            overall_allocated = max(overall_allocated, *(row["allocated_peak_mib"] for row in phases.values()))
            overall_reserved = max(overall_reserved, *(row["reserved_peak_mib"] for row in phases.values()))
            elapsed = time.perf_counter() - started
            durations.append(elapsed)
            metric = {**stats, "global_step": step, "optimizer_updates": progress.state["optimizer_updates"] + update["optimizer_updates"], "loss": update["loss_sum"], "mean_kl": update["mean_kl"], "grad_norm": update["gradient_norm_before_clip"], "learning_rate": config["learning_rate"], "clip_fraction": update["clip_fraction"], "sampled_tokens": update["sampled_policy_tokens"], "rollout_tokens_per_second": sum(sum(row["completion_lengths"]) for row in backend.batches) / rollout_seconds, "update_seconds": elapsed, "eta_seconds": statistics.mean(durations) * (progress.state["max_steps"] - step), "gpu_peak_allocated_mib": overall_allocated, "gpu_peak_reserved_mib": overall_reserved, "policy_reference_logprob_delta": delta}
            write_json(directory / "update_report.json", {**metric, "phase_memory": phases, "reference_unchanged": True, "source_sft_adapter_sha256": source_hash, "maximum_packed_length": max(len(row["input_ids"]) for row in packed), "micro_batch": 16, "accumulation": 1})
            progress.log(metric)
            print({"phase": "update_completed", "step": step, "reward_mean": metric["reward_mean"], "loss": metric["loss"], "kl": metric["mean_kl"], "allocated_peak_mib": overall_allocated, "reserved_peak_mib": overall_reserved}, flush=True)
        progress.update(phase="saving", eta_seconds=0)
        adapter = save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, "checkpoint-stage1", tasks, fixed_hash)
        write_json(run_dir / "training_report.json", {"status": "completed", "tasks": 100, "trajectories": 400, "update_batches": progress.state["global_step"], "optimizer_updates": progress.state["optimizer_updates"], "adapter": str(adapter), "source_sft_adapter_sha256": source_hash, "reference_sha256": fixed_hash, "reference_unchanged": True, "micro_batch": 16, "accumulation": 1, "gpu_peak_allocated_mib": overall_allocated, "gpu_peak_reserved_mib": overall_reserved, "full_500_task_training_started": False})
        return adapter
    except BaseException:
        if progress.state["optimizer_updates"] > 0:
            try:
                optimizer.zero_grad(set_to_none=True)
                torch.cuda.empty_cache()
                save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, "checkpoint-interrupted", tasks, fixed_hash)
            except Exception as save_error:
                write_json(run_dir / "interrupted_save_failure.json", {"error_type": type(save_error).__name__})
        raise


def main():
    """仅在双确认后执行第一阶段；失败写状态，不降批次、不自动重跑。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(HERE / "stage1_config.json"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--confirm-stage-training", action="store_true")
    parser.add_argument("--confirm-api-review", action="store_true")
    args = parser.parse_args()
    if not args.confirm_stage_training or not args.confirm_api_review:
        raise ValueError("training and API review both require confirmation")
    config = load_config(args.config)
    run_dir = args.run_dir.resolve()
    write_json(run_dir / "run_config.json", {"config": config, "config_sha256": digest(config), "started_at": utc_now(), "mode": "stage1_training", "auto_micro_fallback": False})
    progress = LiveProgress(run_dir, config)
    try:
        adapter = train_stage(config, run_dir, progress)
        gc.collect()
        import torch
        torch.cuda.empty_cache()
        if config["evaluate_after_training"]:
            from evaluate_stage import run_evaluation
            run_evaluation(config, run_dir, adapter, progress)
        progress.update(status="completed", phase="completed", eta_seconds=0, reference_unchanged=True)
    except BaseException as exc:
        import torch
        failure = {"status": "failed", "phase_at_failure": progress.state["phase"], "error_type": type(exc).__name__, "message": str(exc), "oom": isinstance(exc, torch.cuda.OutOfMemoryError), "micro_batch": config["micro_batch"], "accumulation": config["accumulation"], "auto_micro_fallback": False, "global_step": progress.state["global_step"], "optimizer_updates": progress.state["optimizer_updates"]}
        write_json(run_dir / "failure.json", failure)
        progress.update(status="failed", phase="failed", error=str(exc), error_type=type(exc).__name__, oom=failure["oom"])
        raise


if __name__ == "__main__":
    main()
