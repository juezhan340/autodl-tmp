"""重算GRPO候选信号、真实采用量、配对评测与过程安全，生成可追溯分析产物。"""

from __future__ import annotations

import argparse
import math
import statistics
from collections import Counter
from pathlib import Path

from runtime import digest, file_sha256, read_json, read_jsonl, write_json
from live import read_metrics, utc_now
from sampler import classify
from trajectory import preprocess
from evaluate_stage import final_success


def lineage(run):
    """按先后顺序收集续跑来源，拒绝循环引用。"""
    sources, seen = [], set()
    while run:
        run = Path(run).resolve()
        if run in seen:
            raise ValueError("cyclic resume lineage")
        seen.add(run)
        sources.append(run)
        run = read_json(run / "run_config.json")["config"].get("resume_run")
    return list(reversed(sources))


def training_summary(run, cutoff):
    """按指定step冻结统计范围，覆盖量不冒充采用量，原失败运行不重复计步。"""
    metrics = [row for row in read_metrics(run / "metrics.jsonl") if row["global_step"] <= cutoff]
    if len(metrics) != cutoff or metrics[-1]["global_step"] != cutoff:
        raise ValueError("completed metrics do not cover the checkpoint step")
    maximum_candidate = metrics[-1]["candidate_groups"]
    tasks = {row["sample_id"]: row["category"] for row in read_jsonl(run / "selected_tasks.jsonl")}
    groups, fingerprints = [], {}
    for source in lineage(run):
        for directory in sorted((source / "candidates").glob("candidate-*")):
            status_path = directory / "candidate_status.json"
            if not status_path.exists():
                continue
            status = read_json(status_path)
            if status["candidate_id"] > maximum_candidate:
                continue
            scores = read_jsonl(directory / "rewards.jsonl")
            evidence = read_jsonl(directory / "evidence.jsonl")
            feedback = classify(scores)
            complete_flags = {all(item["labels"].values()) for item in evidence}
            term_names = {key for item in scores for key in item["terms"]}
            varying_terms = {key for key in term_names if len({item["terms"].get(key, 0) for item in scores}) > 1}
            selected = status["selected"] and status.get("update", cutoff + 1) <= cutoff
            groups.append({"id": status["candidate_id"], "sample_id": status["sample_id"], "category": tasks[status["sample_id"]], **feedback, "selected": selected, "pure_semantic_difference": feedback["bucket"] == "informative" and not feedback["structural_variation"] and len(complete_flags) == 1, "c_complete_varies": len(complete_flags) > 1, "successful_trajectories": sum(item["terms"].get("success", 0) > 0 for item in scores), "unsafe_trajectories": sum(item["safety_gate"] for item in scores), "rewards": [item["total_reward"] for item in scores]})
            groups[-1].update(varying_terms=sorted(varying_terms), truth_only_variation=feedback["bucket"] == "informative" and varying_terms == {"truth"})
            fingerprints[str(status_path)] = file_sha256(status_path)
    if len(groups) != maximum_candidate or len({row["id"] for row in groups}) != maximum_candidate:
        raise ValueError("candidate evidence is incomplete or duplicated")
    selected = [row for row in groups if row["selected"]]
    if len(selected) * 4 != metrics[-1]["selected_trajectories"]:
        raise ValueError("selected candidate count does not match committed optimizer metrics")
    per_category = {}
    for category in ("T1", "T2", "T3", "T4", "T5"):
        subset = [row for row in groups if row["category"] == category]
        adopted = [row for row in subset if row["selected"]]
        per_category[category] = {"candidate_groups": len(subset), "informative_groups": sum(row["bucket"] == "informative" for row in subset), "structural_informative": sum(row["bucket"] == "informative" and row["structural_variation"] for row in subset), "pure_semantic_informative": sum(row["pure_semantic_difference"] for row in subset), "selected_groups": len(adopted), "selected_informative": sum(row["bucket"] == "informative" for row in adopted), "unique_gradient_tasks": len({row["sample_id"] for row in adopted}), "mean_candidate_reward": statistics.mean(value for row in subset for value in row["rewards"])}
    return {"checkpoint_step": cutoff, "candidate_groups": len(groups), "raw_trajectories": len(groups) * 4, "unique_covered_tasks": len({row["sample_id"] for row in groups}), "selected_groups": len(selected), "selected_trajectories": len(selected) * 4, "unique_gradient_tasks": len({row["sample_id"] for row in selected}), "informative_groups": sum(row["bucket"] == "informative" for row in groups), "selected_informative_groups": sum(row["bucket"] == "informative" for row in selected), "candidate_informative_rate": sum(row["bucket"] == "informative" for row in groups) / len(groups), "selected_informative_rate": sum(row["bucket"] == "informative" for row in selected) / len(selected), "mean_informative_groups_per_update": statistics.mean(row["selected_informative_groups"] for row in metrics), "pure_semantic_informative_groups": sum(row["pure_semantic_difference"] for row in groups), "structured_flag_informative_groups": sum(row["bucket"] == "informative" and row["structural_variation"] for row in groups), "selected_structural_groups": sum(row["bucket"] == "informative" and row["structural_variation"] for row in selected), "selected_pure_semantic_groups": sum(row["pure_semantic_difference"] for row in selected), "all_zero_windows": sum(row.get("all_groups_tied", False) for row in metrics), "gpu_peak_allocated_mib_fixed_path": max(row["gpu_peak_allocated_mib"] for row in metrics if row["global_step"] > 1), "gpu_peak_reserved_mib_fixed_path": max(row["gpu_peak_reserved_mib"] for row in metrics if row["global_step"] > 1), "kl_first": metrics[0]["mean_kl"], "kl_last": metrics[-1]["mean_kl"], "kl_max": max(row["mean_kl"] for row in metrics), "grad_norm_max": max(row["grad_norm"] for row in metrics), "loss_min": min(row["loss"] for row in metrics), "loss_max": max(row["loss"] for row in metrics), "candidate_seconds_sum": sum(row["update_seconds"] for row in metrics), "per_category": per_category, "metrics": metrics, "groups": groups, "status_files_sha256": fingerprints}


def pair_statistics(old, new):
    """按任务配对比较，并计算探索性的双侧精确McNemar概率。"""
    old = {row["sample_id"]: row for row in old}
    new = {row["sample_id"]: row for row in new}
    if set(old) != set(new):
        raise ValueError("paired evaluation task identities differ")
    improved = [key for key in old if old[key]["final_success"] is False and new[key]["final_success"] is True]
    regressed = [key for key in old if old[key]["final_success"] is True and new[key]["final_success"] is False]
    count = len(improved) + len(regressed)
    probability = min(1.0, 2 * sum(math.comb(count, index) for index in range(min(len(improved), len(regressed)) + 1)) / 2**count) if count else 1.0
    return {"improved": improved, "regressed": regressed, "net": len(improved) - len(regressed), "paired_exact_p_exploratory": probability}


def model_statistics(rows):
    """使用确定性环境重放补充严格过程安全；T5规则F停用不冒充无虚假回答。"""
    records, brief, counts = [], [], Counter()
    for source in rows:
        row = {**source, "final_success": final_success(source)}
        evidence = preprocess(row)
        records.append(row)
        counts["full_success"] += int(row["final_success"] is True)
        counts["strict_safe_success"] += int(row["final_success"] is True and not evidence["unsafe_events"])
        counts["unsafe_trajectories"] += int(bool(evidence["unsafe_events"]))
        counts["ordinary_error_trajectories"] += int(evidence["error_count"] > 0)
        counts["false_finish_supported_trajectories"] += int(evidence["false_finish"])
        counts["budget_exhausted"] += int(evidence["budget_exhausted"])
        if row["final_success"] is not True or evidence["unsafe_events"]:
            events = [{"turn": turn["turn"], "tool": event["tool_name"], "arguments": event["arguments"], "ok": event["result"].get("ok"), "error": event["result"].get("error")} for turn in row["record"]["turns"] for event in turn["events"]]
            brief.append({"sample_id": row["sample_id"], "category": row["category"], "request": row["scenario"]["user_request"], "conditions": row["scenario"]["task"].get("conditions", []), "labels": row["labels"], "d6": row.get("d6"), "d6_votes": row.get("d6_votes"), "finish": row["record"].get("finish"), "final_success": row["final_success"], "unsafe": evidence["unsafe_events"], "errors": evidence["error_count"], "false_finish": evidence["false_finish"], "progress_final": evidence["progress_final"], "events": events})
    return dict(counts), records, brief


def evaluation_summary(run, evaluation_run):
    """冻结200条结果，对齐epoch3及stage1，保留待确认而不伪判。"""
    config = read_json(run / "run_config.json")["config"]
    comparison = read_json(evaluation_run / "evaluation/comparison.json")
    if comparison["status"] != "completed":
        raise ValueError("complete semantic evaluation is required for final analysis")
    paths = {"SFT epoch3": Path(config["baseline_review"]) / "trajectories.jsonl", "GRPO stage1": Path(config["previous_stage_run"]) / "evaluation/reviewed_trajectories.jsonl", "GRPO coverage500": evaluation_run / "evaluation/reviewed_trajectories.jsonl"}
    snapshots, normalized, cases, hashes = {}, {}, {}, {}
    for name, path in paths.items():
        hashes[str(path)] = file_sha256(path)
        stats, rows, failures = model_statistics(read_jsonl(path))
        if len(rows) != 200 or any(row["final_success"] is None for row in rows):
            raise ValueError("evaluation contains incomplete rows")
        snapshots[name] = {**stats, "per_category": {category: {"full_success": sum(row["category"] == category and row["final_success"] for row in rows), "total": sum(row["category"] == category for row in rows)} for category in ("T1", "T2", "T3", "T4", "T5")}}
        normalized[name], cases[name] = rows, failures
    pairs = {name: pair_statistics(normalized[name], normalized["GRPO coverage500"]) for name in ("SFT epoch3", "GRPO stage1")}
    if any(file_sha256(Path(path)) != value for path, value in hashes.items()):
        raise ValueError("source evaluation changed during analysis")
    return {"models": snapshots, "pairs": pairs, "failure_cases": cases, "source_sha256": hashes, "comparison": comparison}


def render_plot(training, evaluation, path):
    """用真实指标输出PNG图，reward曲线与固定评测分数分开绘制。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    metrics = training["metrics"]
    figure, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    steps = [row["global_step"] for row in metrics]
    axes[0, 0].plot(steps, [row["reward_mean"] for row in metrics], color="#008575")
    axes[0, 0].set(title="Selected-batch reward (different tasks)", xlabel="Optimizer update", ylabel="Mean reward")
    axes[0, 1].plot(steps, [row["selected_informative_groups"] for row in metrics], color="#4269cf")
    axes[0, 1].axhline(.88, color="#c83e4f", linestyle="--", label="Stage1: 0.88/update (4 groups)")
    axes[0, 1].set(title="Informative groups per update (current: 8 groups)", xlabel="Optimizer update", ylabel="Groups per update", ylim=(0, 8))
    axes[0, 1].legend()
    axes[1, 0].plot(steps, [row["mean_kl"] for row in metrics], color="#008575")
    axes[1, 0].set(title="KL to frozen SFT epoch3", xlabel="Optimizer update", ylabel="Mean KL")
    if evaluation:
        names, values = [], []
        for name, result in evaluation["models"].items():
            names.append(name)
            values.append(result["full_success"])
        axes[1, 1].bar(names, values, color=["#717882", "#4269cf", "#008575"])
        axes[1, 1].set(title="Fixed 200: C + original D6", ylabel="Successful tasks / 200", ylim=(0, 200))
        for index, value in enumerate(values):
            axes[1, 1].text(index, value + 2, str(value), ha="center")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main():
    """重算分析产物，不调用模型/API，不修改原轨迹或训练参数。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--checkpoint-step", type=int, required=True)
    parser.add_argument("--evaluation-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    training = training_summary(args.training_run, args.checkpoint_step)
    training["truth_only_groups"] = sum(row["truth_only_variation"] for row in training["groups"])
    training["selected_truth_only_groups"] = sum(row["selected"] and row["truth_only_variation"] for row in training["groups"])
    training["selected_reward_range_histogram"] = dict(Counter(str(round(row["reward_range"], 6)) for row in training["groups"] if row["selected"] and row["bucket"] == "informative"))
    evaluation = evaluation_summary(args.training_run, args.evaluation_run) if args.evaluation_run else None
    summary = {"created_at": utc_now(), "training_run": str(args.training_run), "evaluation_run": str(args.evaluation_run) if args.evaluation_run else None, "checkpoint_step": args.checkpoint_step, "training": training, "evaluation": evaluation, "original_sources_modified": False}
    write_json(args.output / "analysis.json", summary)
    if args.plot:
        render_plot(training, evaluation, args.plot)
    print({"output": str(args.output), "checkpoint_step": args.checkpoint_step, "candidate_groups": training["candidate_groups"], "selected_groups": training["selected_groups"], "unique_gradient_tasks": training["unique_gradient_tasks"], "evaluation_models": evaluation["models"] if evaluation else None}, flush=True)


if __name__ == "__main__":
    main()
