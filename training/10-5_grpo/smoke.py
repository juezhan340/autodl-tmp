"""执行4任务乘4轨迹、四路生成及一次GRPO参数更新，禁止隐式启动完整训练。"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from runtime import REPO_ROOT, annotate_json_tree, digest, file_sha256, load_config, read_jsonl, write_json, write_jsonl
from trajectory import preprocess
from reward import assign_advantages, judge_rows, score
from rollout import BatchService, HFBackend, generate_group, pack_calls
from model_math import activate, adapter_digest, load_model, make_batch, surrogate_loss, token_logps


def select_tasks(config, tokenizer):
    """从训练集合按已知教师长度选各类最长一项；教师消息只选样、不喂给actor。"""
    root = Path(config["sft_data"])
    tasks = read_jsonl(root / "train_scenarios.jsonl")
    messages = {row["sample_id"]: row for row in read_jsonl(root / "train.jsonl")}
    lengths = {key: len(tokenizer.apply_chat_template(row["messages"], tokenize=True)) for key, row in messages.items()}
    selected = [max((row for row in tasks if row["category"] == category), key=lambda row: lengths[row["sample_id"]]) for category in config["smoke_categories"]]
    forbidden = {row["group_id"] for split in ("validation", "test") for row in read_jsonl(root / f"{split}_scenarios.jsonl")}
    if any(row["group_id"] in forbidden for row in selected):
        raise ValueError("smoke task overlaps validation/test group")
    return selected, {row["sample_id"]: lengths[row["sample_id"]] for row in selected}


def check_archives(config, output):
    """不加载模型和调用API，在800条已有轨迹上核对预处理支持范围。"""
    source = Path(config["sft_data"]).parent / "comparison_test_20261005"
    report = {}
    fingerprints = {}
    for model in ("baseline", "epoch1", "epoch2", "epoch3"):
        path = source / model / "trajectories.jsonl"
        fingerprints[str(path)] = file_sha256(path)
        ledgers = [preprocess(row) for row in read_jsonl(path)]
        report[model] = {"rows": len(ledgers), "ordinary_error_events": sum(row["error_count"] for row in ledgers), "false_finish_rows": sum(row["false_finish"] for row in ledgers), "unsafe_rows": sum(bool(row["unsafe_events"]) for row in ledgers), "evidence_status": dict(Counter(row["evidence_status"] for row in ledgers)), "semantic_judge": "not_called"}
        write_jsonl(output / model / "evidence.jsonl", ledgers, "已有轨迹的规则重放证据；无模型更新、无外部评审，未知结尾不记0分。")
    unchanged = all(file_sha256(Path(path)) == value for path, value in fingerprints.items())
    result = {"mode": "cpu_check", "models": report, "source_files_unchanged": unchanged, "reward_version": config["reward_version"], "config_sha256": digest(config)}
    if not unchanged:
        raise ValueError("archive source changed during check")
    write_json(output / "check_report.json", result)
    return result


def memory_snapshot():
    """记录本阶段分配和预留峰值，两者包含关系不相加。"""
    import torch
    torch.cuda.synchronize()
    return {"allocated_peak_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 2), "reserved_peak_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 2)}


def reset_memory():
    """阶段之间释放空闲缓存后重置峰值，避免旧缓存冒充本阶段开销。"""
    import torch
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()


def precompute_logps(model, packed, tokenizer, config, require_initial_equal=True):
    """采样policy未更新时分小批算旧概率与固定SFT参考概率，缓存到CPU。"""
    import torch
    old = [torch.zeros(len(row["input_ids"]) - 1) for row in packed]
    reference = [torch.zeros_like(row) for row in old]
    max_delta = 0.0
    for start in range(0, len(packed), config["micro_batch"]):
        batch = make_batch(packed[start:start + config["micro_batch"]], tokenizer.pad_token_id, "cuda")
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
            activate(model, "policy")
            sampled = token_logps(model, batch, config["temperature"]).float()
            activate(model, "sft_reference")
            fixed = token_logps(model, batch, config["temperature"]).float()
        max_delta = max(max_delta, float(((sampled - fixed).abs() * batch["mask"]).max()))
        for index in range(sampled.shape[0]):
            active = batch["mask"][index].bool()
            positions = batch["positions"][active].cpu()
            old[start + index][positions] = sampled[index][active].cpu()
            reference[start + index][positions] = fixed[index][active].cpu()
        del sampled, fixed, batch
    activate(model, "policy")
    if require_initial_equal and max_delta > 1e-4:
        raise ValueError("initial policy and fixed SFT probabilities differ")
    return old, reference, max_delta


def train_once(model, packed, old, reference, advantages, tokenizer, config, output, optimizer=None, save_checkpoint=True):
    """16轨迹分8个micro反向累计，只执行一次优化器step且不保留16套计算图。"""
    import torch
    activate(model, "policy")
    model.train()
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    if optimizer is None:
        optimizer = torch.optim.AdamW(parameters, lr=config["learning_rate"], weight_decay=0.0)
    optimizer.zero_grad(set_to_none=True)
    denominator = sum(row["sampled_tokens"] for row in packed)
    records = []
    for start in range(0, len(packed), config["micro_batch"]):
        subset = packed[start:start + config["micro_batch"]]
        batch = make_batch(subset, tokenizer.pad_token_id, "cuda")
        width = batch["input_ids"].shape[1] - 1
        previous = torch.zeros((len(subset), width), device="cuda")
        fixed = torch.zeros_like(previous)
        for index, row in enumerate(subset):
            length = len(row["input_ids"]) - 1
            previous[index, :length] = old[start + index].to("cuda")
            fixed[index, :length] = reference[start + index].to("cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            current = token_logps(model, batch, config["temperature"]).float()
            advantage = torch.tensor(advantages[start:start + len(subset)], device="cuda")
            loss, metrics = surrogate_loss(current, previous[:, batch["positions"]], fixed[:, batch["positions"]], advantage, batch["mask"], denominator, config["beta"], config["epsilon"])
        if not torch.isfinite(loss):
            raise ValueError("GRPO loss is not finite")
        loss.backward()
        records.append({"micro": len(records) + 1, "trajectories": len(subset), "loss": float(loss.detach()), **metrics})
        print({"phase": "backward", "micro": len(records), "total_micros": config["accumulation"], "loss": records[-1]["loss"]}, flush=True)
        del current, previous, fixed, loss, batch, advantage
    norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0)
    if not torch.isfinite(norm):
        raise ValueError("gradient norm is not finite")
    informative = float(norm) > 1e-12
    if informative:
        optimizer.step()
    if informative and save_checkpoint:
        destination = output / "smoke_adapter"
        model.save_pretrained(destination, selected_adapters=["policy"])
        tokenizer.save_pretrained(destination / "policy")
        torch.save(optimizer.state_dict(), destination / "optimizer.pt")
        annotate_json_tree(destination)
    optimizer.zero_grad(set_to_none=True)
    model.eval()
    write_jsonl(output / "update_metrics.jsonl", records, "一次更新中的micro损失及KL统计；无额外手工再除累计次数。")
    return {"optimizer_updates": int(informative), "gradient_norm_before_clip": float(norm), "sampled_policy_tokens": denominator, "micro_batches": len(records), "loss_sum": sum(row["loss"] for row in records), "mean_kl": sum(row["kl_sum"] for row in records) / denominator, "clip_fraction": sum(row["clip_tokens"] for row in records) / denominator, "initial_logprob_delta_max": max(row["initial_logprob_delta"] for row in records), "all_groups_tied": not any(abs(value) > 1e-10 for value in advantages)}


def run_smoke(config, output, api_confirmed):
    """按用户要求直接4路顶起；出错保留证据，不自动降并发伪装通过。"""
    import torch
    from transformers import set_seed
    if not torch.cuda.is_available():
        raise ValueError("GPU unavailable: no GPU smoke was executed")
    if not api_confirmed:
        raise ValueError("finish review requires --confirm-api-review")
    set_seed(config["seed"])
    started = time.perf_counter()
    source_adapter = Path(config["sft_adapter"]) / "adapter_model.safetensors"
    source_hash = file_sha256(source_adapter)
    phase_memory = {}
    reset_memory()
    model, tokenizer = load_model(config)
    phase_memory["load"] = memory_snapshot()
    initial_policy = adapter_digest(model, "policy")
    initial_reference = adapter_digest(model, "sft_reference")
    if initial_policy != initial_reference:
        raise ValueError("policy/reference tensor hashes differ")
    tasks, lengths = select_tasks(config, tokenizer)
    write_json(output / "selected_tasks.json", {"tasks": tasks, "teacher_lengths_for_selection_only": lengths})
    rows = []
    backend = HFBackend(model, tokenizer, config)
    service = BatchService(backend, config["rollout_parallel"])
    reset_memory()
    try:
        for task in tasks:
            rows.extend(generate_group(task, service, tokenizer, config))
            write_jsonl(output / "rollouts.jsonl", rows, "16条当前policy新轨迹及真实token；隐藏Scenario仅用于评判，不作为policy输入。")
            print({"phase": "rollout", "completed_groups": len(rows) // config["num_generations"], "trajectories": len(rows)}, flush=True)
    finally:
        service.close()
    phase_memory["rollout"] = memory_snapshot()
    write_json(output / "generation_batches.json", backend.batches)
    if any(row["infrastructure_errors"] for row in rows):
        raise ValueError("rollout infrastructure errors; no rewards or update applied")
    if max(batch["size"] for batch in backend.batches) != config["rollout_parallel"]:
        raise ValueError("requested four-way batch was not exercised")
    packed = [pack_calls(row["calls"], config["max_length"]) for row in rows]
    write_jsonl(output / "packed_trajectories.jsonl", packed, "完整上下文可见，policy_mask只标真实采样token；前缀逐token一致已验证。")
    evidence = [preprocess(row) for row in rows]
    write_jsonl(output / "evidence.jsonl", evidence, "状态重放、目标进度、必要取证、真实错误回执与安全门控。")
    semantics = judge_rows(rows, output / "finish_review", REPO_ROOT / ".env.deepseek", config["judge_workers"])
    scores = [score(item, semantic, config) for item, semantic in zip(evidence, semantics)]
    write_jsonl(output / "rewards.jsonl", scores, "r2奖励，无无效调用、编造事实或调用成本项；pending禁止进入更新。")
    advantages = assign_advantages(rows, scores, config["num_generations"])
    write_json(output / "advantages.json", {row["rollout_id"]: advantage for row, advantage in zip(rows, advantages)})
    reset_memory()
    old, reference, initial_delta = precompute_logps(model, packed, tokenizer, config)
    phase_memory["old_reference_logps"] = memory_snapshot()
    reset_memory()
    update = train_once(model, packed, old, reference, advantages, tokenizer, config, output)
    phase_memory["train_forward_backward_step"] = memory_snapshot()
    if adapter_digest(model, "sft_reference") != initial_reference or file_sha256(source_adapter) != source_hash:
        raise ValueError("frozen reference or source SFT adapter changed")
    policy_changed = adapter_digest(model, "policy") != initial_policy
    if bool(update["optimizer_updates"]) != policy_changed:
        raise ValueError("optimizer update does not match policy weight change")
    result = {"status": "completed", "mode": "smoke", "full_training_started": False, "trajectories": len(rows), "task_groups": len(tasks), "rollout_parallel_observed": max(batch["size"] for batch in backend.batches), "maximum_packed_length": max(len(row["input_ids"]) for row in packed), "phase_memory": phase_memory, "reward_values": [item["total_reward"] for item in scores], "initial_reference_logprob_delta": initial_delta, "reference_unchanged": True, "source_sft_adapter_unchanged": True, "policy_changed": policy_changed, "elapsed_seconds": round(time.perf_counter() - started, 3), **update}
    write_json(output / "smoke_report.json", result)
    del model
    torch.cuda.empty_cache()
    return result


def main():
    """默认只CPU核对；GPU和收费评审都需显式确认，唯一GPU入口是冒烟。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--mode", choices=("check", "smoke"), default="check")
    parser.add_argument("--confirm-smoke", action="store_true")
    parser.add_argument("--confirm-api-review", action="store_true")
    args = parser.parse_args()
    if args.mode == "smoke" and not args.confirm_smoke:
        raise ValueError("GPU smoke requires --confirm-smoke")
    config = load_config(args.config)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(config["output_root"]) / (args.mode + "-" + stamp)
    write_json(output / "run_config.json", {"config": config, "mode": args.mode, "started_at_utc": datetime.now(timezone.utc).isoformat()})
    print({"mode": args.mode, "output": str(output), "config_sha256": digest(config)}, flush=True)
    try:
        result = check_archives(config, output) if args.mode == "check" else run_smoke(config, output, args.confirm_api_review)
    except Exception as exc:
        write_json(output / "failure.json", {"status": "failed", "error_type": type(exc).__name__, "message": str(exc), "full_training_started": False})
        raise
    print(result, flush=True)


if __name__ == "__main__":
    main()
