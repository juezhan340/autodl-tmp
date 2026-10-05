"""直接执行500任务池反馈采样GRPO，micro16累计2并在结束后评测固定200项。"""

from __future__ import annotations

import argparse
import gc
import time
from collections import Counter
from pathlib import Path

from runtime import HERE, REPO_ROOT, digest, file_sha256, load_config, read_json, read_jsonl, write_json, write_jsonl
from live import LiveProgress, utc_now
from model_math import activate, adapter_digest, load_model
from reward import assign_advantages, judge_rows, score
from rollout import BatchService, HFBackend, generate_group, pack_calls
from run_stage import reward_statistics, save_checkpoint
from sampler import FeedbackSampler, select_groups
from smoke import memory_snapshot, precompute_logps, reset_memory, train_once
from trajectory import preprocess


def restore_optimizer(model, config):
    """恢复自有第一阶段AdamW状态，并核对动量形状和冻结参数边界。"""
    import torch
    activate(model, "policy")
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=config["learning_rate"], weight_decay=0.0)
    saved = torch.load(config["optimizer_checkpoint"], map_location="cpu", weights_only=False)
    optimizer.load_state_dict(saved["optimizer"])
    for group in optimizer.param_groups:
        group["lr"] = config["learning_rate"]
        for parameter in group["params"]:
            for key in ("exp_avg", "exp_avg_sq"):
                value = optimizer.state[parameter].get(key)
                if value is None or value.shape != parameter.shape:
                    raise ValueError("saved AdamW moment does not match the policy parameter")
    return optimizer


def collect_chunk(model, tokenizer, config, run_dir, sampler, candidates, progress):
    """当前policy冻结时四组一批生成和并发复核，每组独立落盘。"""
    version = progress.state["optimizer_updates"]
    remaining = min(4, config["candidate_window"] - len(candidates), config["candidate_group_budget"] - sampler.candidates)
    excluded = {item["task"]["sample_id"] for item in candidates}
    tasks = []
    for _ in range(remaining):
        task = sampler.draw(excluded)
        tasks.append(task)
        excluded.add(task["sample_id"])
    # 覆盖期任务天然唯一；复访阶段将同窗候选排除，避免抽到重复组。
    if len({task["sample_id"] for task in tasks}) != len(tasks):
        raise ValueError("duplicate tasks in one candidate chunk")
    backend = HFBackend(model, tokenizer, config)
    service = BatchService(backend, config["rollout_parallel"])
    chunk = []
    progress.update(phase="rollout", current_policy_version=version, judge_pending=0)
    try:
        for index, task in enumerate(tasks):
            identifier = sampler.candidates + index + 1
            namespace = f"full-v{version:03d}-candidate{identifier:04d}"
            rows = generate_group(task, service, tokenizer, {**config, "group_namespace": namespace})
            for row in rows:
                row["rollout_id"] = namespace + "-" + row["rollout_id"]
            directory = run_dir / "candidates" / f"candidate-{identifier:04d}"
            write_jsonl(directory / "rollouts.jsonl", rows, "当前policy新G4轨迹、真实采样token和独立环境记录。")
            if any(row["infrastructure_errors"] for row in rows):
                raise ValueError("rollout infrastructure error cannot become a task reward")
            packed = [pack_calls(row["calls"], config["max_length"]) for row in rows]
            evidence = [preprocess(row) for row in rows]
            write_jsonl(directory / "packed_trajectories.jsonl", packed, "环境观察保留上下文但不监督，只用真实生成token。")
            write_jsonl(directory / "evidence.jsonl", evidence, "逐步骤环境重放及可判定奖励账本。")
            chunk.append({"candidate_id": identifier, "directory": directory, "task": task, "policy_version": version, "rows": rows, "packed": packed, "evidence": evidence})
            progress.update(trajectories_generated=sampler.candidates * config["num_generations"] + (index + 1) * config["num_generations"])
    finally:
        service.close()
    review_root = run_dir / "candidate_reviews" / f"chunk-{chunk[0]['candidate_id']:04d}"
    write_json(review_root / "generation_batches.json", backend.batches)
    all_rows = [row for item in chunk for row in item["rows"]]
    progress.update(phase="reward", judge_pending=len(all_rows))

    def report_review(values):
        """只报告复核实际进度，pending不得伪造成0奖励。"""
        progress.update(judge_pending=values["total"] - values["completed"], api_errors=values["errors"], http_attempts_current_batch=values["http_attempts"])

    semantics = judge_rows(all_rows, review_root, REPO_ROOT / ".env.deepseek", config["judge_workers"], progress_callback=report_review)
    for index, item in enumerate(chunk):
        judgments = semantics[index * config["num_generations"]:(index + 1) * config["num_generations"]]
        scores = [score(evidence, verdict, config) for evidence, verdict in zip(item["evidence"], judgments)]
        advantages = assign_advantages(item["rows"], scores, config["num_generations"])
        feedback = sampler.record(item["task"], scores, version)
        item.update(scores=scores, advantages=advantages, **feedback)
        write_jsonl(item["directory"] / "rewards.jsonl", scores, "沿用r2，安全门控优先，无效调用与调用成本不扣分。")
        write_json(item["directory"] / "advantages.json", {row["rollout_id"]: value for row, value in zip(item["rows"], advantages)})
        write_json(item["directory"] / "candidate_status.json", {"candidate_id": item["candidate_id"], "sample_id": item["task"]["sample_id"], "policy_version": version, "selected": False, **feedback})
        candidates.append(item)
    sampler.save(run_dir)
    chunk_scores = [row for item in chunk for row in item["scores"]]
    chunk_evidence = [row for item in chunk for row in item["evidence"]]
    chunk_advantages = [value for item in chunk for value in item["advantages"]]
    stats = reward_statistics(all_rows, chunk_evidence, chunk_scores, chunk_advantages, config["num_generations"])
    memory = memory_snapshot()
    progress.update(**stats, **sampler.snapshot(), judge_pending=0, candidate_window_size=len(candidates), candidate_informative_groups=sum(item["bucket"] == "informative" for item in candidates), gpu_peak_allocated_mib=max(progress.state["gpu_peak_allocated_mib"], memory["allocated_peak_mib"]), gpu_peak_reserved_mib=max(progress.state["gpu_peak_reserved_mib"], memory["reserved_peak_mib"]))
    print({"phase": "candidate_chunk", **sampler.snapshot(), "policy_version": version, "window_informative": progress.state["candidate_informative_groups"]}, flush=True)


def train_full(config, run_dir, progress):
    """同policy候选采样后完整选8组更新，预算有限且必须覆盖500项。"""
    import torch
    from transformers import set_seed
    if (config["micro_batch"], config["accumulation"], config["groups_per_update"], config["num_generations"]) != (16, 2, 8, 4):
        raise ValueError("formal run requires micro16 accumulation2 with eight G4 groups")
    if not torch.cuda.is_available():
        raise ValueError("GPU unavailable")
    sampler = FeedbackSampler(config)
    write_jsonl(run_dir / "selected_tasks.jsonl", sampler.order, "剩余400项优先，再刷新旧100项，覆盖后反馈复访；仅train500。")
    set_seed(config["seed"])
    source = Path(config["sft_adapter"]) / "adapter_model.safetensors"
    source_hash = file_sha256(source)
    reset_memory()
    model, tokenizer = load_model(config)
    reference_hash = adapter_digest(model, "sft_reference")
    optimizer = restore_optimizer(model, config)
    write_json(run_dir / "initialization.json", {"policy_adapter": config["policy_adapter"], "policy_sha256": adapter_digest(model, "policy"), "reference_adapter": config["sft_adapter"], "reference_sha256": reference_hash, "optimizer_restored": True, "seed": config["seed"], "reference_is_original_sft": True})
    peaks = memory_snapshot()
    progress.update(status="running", reference_unchanged=True, gpu_peak_allocated_mib=peaks["allocated_peak_mib"], gpu_peak_reserved_mib=peaks["reserved_peak_mib"])
    windows, selected_total, skipped = 0, progress.state.get("selected_trajectories", 0), progress.state.get("skipped_windows", 0)
    coverage_saved = False
    try:
        while sampler.candidates < config["candidate_group_budget"]:
            if len(sampler.covered) == config["train_tasks"] and progress.state["optimizer_updates"] >= config["max_updates"]:
                break
            windows += 1
            started = time.perf_counter()
            candidates = []
            reset_memory()
            while len(candidates) < config["candidate_window"] and sampler.candidates < config["candidate_group_budget"]:
                collect_chunk(model, tokenizer, config, run_dir, sampler, candidates, progress)
                informative = sum(item["bucket"] == "informative" for item in candidates)
                if len(candidates) >= config["groups_per_update"] and informative >= config["target_informative_groups"]:
                    break
                if progress.state["optimizer_updates"] >= config["max_updates"]:
                    break
            phases = {"candidate_rollout": memory_snapshot()}
            directory = run_dir / "windows" / f"window-{windows:03d}"
            chosen = select_groups(candidates, config["groups_per_update"], config["target_informative_groups"])
            has_signal = any(item["bucket"] == "informative" for item in chosen)
            allowed = len(chosen) == config["groups_per_update"] and has_signal and progress.state["optimizer_updates"] < config["max_updates"]
            reason = "selected" if allowed else "update_budget_reached" if progress.state["optimizer_updates"] >= config["max_updates"] else "incomplete_tail" if len(chosen) < config["groups_per_update"] else "all_advantages_zero"
            write_json(directory / "selection.json", {"policy_version": progress.state["optimizer_updates"], "candidate_ids": [item["candidate_id"] for item in candidates], "selected_candidate_ids": [item["candidate_id"] for item in chosen] if allowed else [], "reason": reason, "candidate_buckets": dict(Counter(item["bucket"] for item in candidates)), "discarded_before_next_policy": True})
            if allowed:
                rows = [row for item in chosen for row in item["rows"]]
                packed = [row for item in chosen for row in item["packed"]]
                evidence = [row for item in chosen for row in item["evidence"]]
                scores = [row for item in chosen for row in item["scores"]]
                advantages = assign_advantages(rows, scores, config["num_generations"])
                if len({item["policy_version"] for item in chosen}) != 1 or chosen[0]["policy_version"] != progress.state["optimizer_updates"]:
                    raise ValueError("stale candidates cannot be used for a new policy update")
                write_jsonl(directory / "rollouts.jsonl", rows, "同一采样policy版本下采用的8个完整G4组，共32条。")
                write_jsonl(directory / "packed_trajectories.jsonl", packed, "完整轨迹上下文及真实policy token mask。")
                write_json(directory / "advantages.json", {row["rollout_id"]: value for row, value in zip(rows, advantages)})
                reset_memory()
                progress.update(phase="logprobs")
                old, reference, delta = precompute_logps(model, packed, tokenizer, config, require_initial_equal=False)
                phases["old_reference_logps"] = memory_snapshot()
                torch.save({"old": old, "reference": reference}, directory / "sampled_logprobs.pt")
                reset_memory()
                progress.update(phase="backward")
                update = train_once(model, packed, old, reference, advantages, tokenizer, config, directory, optimizer=optimizer, save_checkpoint=False)
                phases["train_forward_backward_step"] = memory_snapshot()
                if update["micro_batches"] != 2 or update["optimizer_updates"] != 1:
                    raise ValueError("formal 32-trajectory update did not produce one optimizer step")
                if adapter_digest(model, "sft_reference") != reference_hash or file_sha256(source) != source_hash:
                    raise ValueError("fixed reference or source adapter changed")
                selected_total += len(rows)
                step = progress.state["optimizer_updates"] + 1
                stats = reward_statistics(rows, evidence, scores, advantages, config["num_generations"])
                peaks = {key: max(peaks[key], *(value[key] for value in phases.values())) for key in peaks}
                metric = {**stats, **sampler.snapshot(), "global_step": step, "optimizer_updates": step, "selected_trajectories": selected_total, "window": windows, "skipped_windows": skipped, "candidate_window_size": len(candidates), "selected_informative_groups": sum(item["bucket"] == "informative" for item in chosen), "selected_structural_groups": sum(item["bucket"] == "informative" and item["structural_variation"] for item in chosen), "selection_rate": config["groups_per_update"] / len(candidates), "loss": update["loss_sum"], "mean_kl": update["mean_kl"], "grad_norm": update["gradient_norm_before_clip"], "clip_fraction": update["clip_fraction"], "sampled_tokens": update["sampled_policy_tokens"], "learning_rate": config["learning_rate"], "update_seconds": time.perf_counter() - started, "gpu_peak_allocated_mib": peaks["allocated_peak_mib"], "gpu_peak_reserved_mib": peaks["reserved_peak_mib"], "policy_reference_logprob_delta": delta}
                write_json(directory / "update_report.json", {**metric, "phase_memory": phases, "micro_batch": 16, "accumulation": 2, "maximum_packed_length": max(len(row["input_ids"]) for row in packed), "reference_unchanged": True})
                progress.log(metric)
                for item in chosen:
                    write_json(item["directory"] / "candidate_status.json", {"candidate_id": item["candidate_id"], "sample_id": item["task"]["sample_id"], "policy_version": item["policy_version"], "selected": True, "update": step, "bucket": item["bucket"], "structural_variation": item["structural_variation"]})
                print({"phase": "update_completed", "step": step, "informative_groups": metric["selected_informative_groups"], "candidates": sampler.candidates, "covered": len(sampler.covered), "reward": metric["reward_mean"], "kl": metric["mean_kl"], "allocated_peak_mib": peaks["allocated_peak_mib"], "reserved_peak_mib": peaks["reserved_peak_mib"]}, flush=True)
                if step == 32:
                    save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, "checkpoint-update032", sampler.tasks, reference_hash)
                del old, reference
            else:
                skipped += 1
                progress.update(skipped_windows=skipped, last_skip_reason=reason)
                print({"phase": "window_skipped", "reason": reason, **sampler.snapshot()}, flush=True)
            if len(sampler.covered) == config["train_tasks"] and not coverage_saved:
                save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, "checkpoint-coverage500", sampler.tasks, reference_hash)
                coverage_saved = True
            candidates.clear()
            if allowed:
                chosen.clear()
                del rows, packed, evidence, scores, advantages
        if len(sampler.covered) != config["train_tasks"]:
            raise ValueError("budget ended before all 500 training tasks were covered")
        progress.update(phase="saving")
        adapter = save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, "checkpoint-full500", sampler.tasks, reference_hash)
        write_json(run_dir / "training_report.json", {"status": "completed", **sampler.snapshot(), "optimizer_updates": progress.state["optimizer_updates"], "selected_trajectories": selected_total, "skipped_windows": skipped, "adapter": str(adapter), "micro_batch": 16, "accumulation": 2, "reference_unchanged": True, "source_sft_adapter_sha256": source_hash, "gpu_peak_allocated_mib": peaks["allocated_peak_mib"], "gpu_peak_reserved_mib": peaks["reserved_peak_mib"]})
        return adapter
    except BaseException:
        if progress.state["optimizer_updates"] > 0:
            try:
                optimizer.zero_grad(set_to_none=True)
                torch.cuda.empty_cache()
                save_checkpoint(model, tokenizer, optimizer, run_dir, config, progress, "checkpoint-interrupted", sampler.tasks, reference_hash)
            except Exception as save_error:
                write_json(run_dir / "interrupted_save_failure.json", {"error_type": type(save_error).__name__})
        raise


def main():
    """直接正式训练，不提供测试分支；结束释放模型后自动评测。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(HERE / "full_config.json"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--confirm-stage-training", action="store_true")
    parser.add_argument("--confirm-api-review", action="store_true")
    args = parser.parse_args()
    if not args.confirm_stage_training or not args.confirm_api_review:
        raise ValueError("training and API review require explicit confirmation")
    config = load_config(args.config)
    run_dir = args.run_dir.resolve()
    write_json(run_dir / "run_config.json", {"config": config, "config_sha256": digest(config), "started_at": utc_now(), "mode": "formal500_feedback_sampling", "auto_micro_fallback": False})
    progress = LiveProgress(run_dir, config)
    try:
        if config.get("resume_run"):
            previous = Path(config["resume_run"])
            saved = read_json(previous / "training_status.json")
            checkpoint_state = read_json(Path(config["policy_adapter"]).parent / "stage_state.json")
            if saved["optimizer_updates"] != checkpoint_state["optimizer_updates"]:
                raise ValueError("resume progress does not match saved optimizer checkpoint")
            for key in ("global_step", "optimizer_updates", "selected_trajectories", "skipped_windows"):
                progress.state[key] = saved[key]
            inherited = [{**row, "inherited_from": str(previous)} for row in read_jsonl(previous / "metrics.jsonl")]
            write_jsonl(run_dir / "metrics.jsonl", inherited, "继承中断前已完成更新的真实指标，随后追加续跑更新。")
            write_json(run_dir / "resume_manifest.json", {"source_run": str(previous), "checkpoint": config["policy_adapter"], "completed_updates": saved["optimizer_updates"], "discard_uncommitted_candidates": True, "new_logprob_path": "checkpointed_128_token_full_vocabulary_FP32"})
        adapter = train_full(config, run_dir, progress)
        gc.collect()
        import torch
        torch.cuda.empty_cache()
        if config["evaluate_after_training"]:
            from evaluate_stage import run_evaluation
            run_evaluation(config, run_dir, adapter, progress)
        progress.update(status="completed", phase="completed", eta_seconds=0)
    except BaseException as exc:
        import torch
        write_json(run_dir / "failure.json", {"status": "failed", "phase_at_failure": progress.state["phase"], "error_type": type(exc).__name__, "message": str(exc), "oom": isinstance(exc, torch.cuda.OutOfMemoryError), "micro_batch": 16, "accumulation": 2, "auto_micro_fallback": False, "optimizer_updates": progress.state["optimizer_updates"]})
        progress.update(status="failed", phase="failed", error_type=type(exc).__name__, error=str(exc), oom=isinstance(exc, torch.cuda.OutOfMemoryError))
        raise


if __name__ == "__main__":
    main()
