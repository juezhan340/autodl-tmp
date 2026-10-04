"""运行数据、教师重放、最小 GPU 更新与检查点重载的预测试闭环。"""

from __future__ import annotations

import argparse
import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path

from common import CATEGORIES, data_dir, file_sha256, load_config, read_json, read_jsonl, write_json
from data import prepare_data, verify_manifest
from evaluate import load_inference_model, run_evaluation
from train import run_training
from new_demo.agents.A_policy import ScriptPolicy
from new_demo.eval.C_episode_runner import EpisodeRunner


def replay_training_examples(config: dict) -> list[dict]:
    """每类重放一条训练教师轨迹，验证 C/B 契约，不查询测试集成绩。"""
    source = {row["scenario"]["scenario_id"]: row for row in read_jsonl(config["dataset_source"])}
    training = read_jsonl(data_dir(config) / "train.jsonl")
    results = []
    for category in CATEGORIES:
        sample = next(row for row in training if row["category"] == category)
        row = source[sample["sample_id"]]
        calls = [turn["tool_calls"][0] for turn in row["record"]["turns"]]
        result = EpisodeRunner(ScriptPolicy(calls)).run(row["scenario"])
        if not result.labels.all_true:
            raise ValueError(f"teacher replay failed: {sample['sample_id']}")
        results.append({"sample_id": sample["sample_id"], "category": category, "labels": result.labels.to_dict()})
    return results


def verify_adapter_reload(config: dict, run_dir: Path) -> list[str]:
    """重载每个 epoch 和选定 adapter，逐张量核对保存后的参数。"""
    import torch
    from peft import get_peft_model_state_dict
    from safetensors import safe_open
    index = read_json(run_dir / "checkpoint_index.json")
    paths = [Path(item["path"]) for item in index] + [run_dir / "selected_adapter"]
    verified = []
    for path in paths:
        # 与正式评测一致，每个检查点独立加载，避免追加adapter时先被转成BF16。
        model, tokenizer = load_inference_model(config, str(path))
        actual = get_peft_model_state_dict(model)
        with safe_open(str(path / "adapter_model.safetensors"), framework="pt", device="cpu") as saved:
            if set(actual) != set(saved.keys()):
                raise ValueError("reloaded adapter tensor names differ")
            for name in saved.keys():
                torch.testing.assert_close(actual[name].detach().cpu(), saved.get_tensor(name), rtol=0, atol=0)
        verified.append(str(path))
        del model, tokenizer, actual
        torch.cuda.empty_cache()
    return verified


def run_preflight(config: dict, gpu_smoke: bool = False, report_dir: str | Path | None = None, reuse_smoke: str | None = None) -> dict:
    """只准备数据与预测试，绝不调用完整训练模式或200条测试评测。"""
    manifest = prepare_data(config)
    verify_manifest(config)
    report = {"full_training_started": False, "test_set_model_evaluated": False, "external_judge_called": False, "data_counts": {name: info["count"] for name, info in manifest["splits"].items()}, "max_tokens": {name: info["max_tokens"] for name, info in manifest["splits"].items()}, "target_tokens": {name: info["target_tokens"] for name, info in manifest["splits"].items()}, "data_manifest_sha256": file_sha256(data_dir(config) / "manifest.json"), "teacher_replay": replay_training_examples(config), "versions": {name: importlib.metadata.version(name) for name in ("torch", "transformers", "trl", "peft", "accelerate", "datasets", "tokenizers", "safetensors")}, "gpu_smoke": None}
    if gpu_smoke:
        base_weights = Path(config["base_model"]) / "model.safetensors"
        before = file_sha256(base_weights)
        if reuse_smoke:
            previous = Path(reuse_smoke).resolve()
            if previous.parent != Path(config["output_root"]).resolve() or not previous.name.startswith("smoke-"):
                raise ValueError("reuse path must be a smoke run under output_root")
            saved = read_json(previous / "run_config.json")
            if saved["config"] != config:
                raise ValueError("reused smoke configuration differs")
            if saved["data_manifest_sha256"] != report["data_manifest_sha256"]:
                raise ValueError("reused smoke dataset version differs")
            summary = read_json(previous / "training_summary.json")
            if summary["mode"] != "smoke" or summary["updates"] != 2:
                raise ValueError("only a completed two-update smoke may be reused")
        else:
            summary = run_training(config, "smoke")
        run_dir = Path(summary["run_dir"])
        reloaded = verify_adapter_reload(config, run_dir)
        evaluation_dir = run_dir / "evaluation_smoke"
        if evaluation_dir.exists():
            suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            evaluation_dir = run_dir / ("evaluation_smoke-" + suffix)
        evaluation = run_evaluation(config, "train", evaluation_dir, summary["selected_adapter"], per_category=1, semantic_mode="off")
        if evaluation["generation_errors"] or evaluation["successful_generations"] < 5:
            raise ValueError("local generation interface test failed")
        if file_sha256(base_weights) != before:
            raise ValueError("original base weights were modified")
        report["gpu_smoke"] = {key: value for key, value in summary.items() if key != "log_history"}
        report["gpu_smoke"]["verified_adapter_paths"] = reloaded
        report["gpu_smoke"]["base_weights_unchanged"] = True
        report["gpu_smoke"]["environment_interface_test"] = evaluation
    output = Path(report_dir) if report_dir else Path(config["output_root"]) / "preflight"
    write_json(output / "preflight_report.json", report)
    return report


def main() -> None:
    """默认只做 CPU 数据检查；两次 GPU 更新需要明确指定开关。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--gpu-smoke", action="store_true")
    parser.add_argument("--report-dir")
    parser.add_argument("--reuse-smoke")
    args = parser.parse_args()
    if args.reuse_smoke and not args.gpu_smoke:
        parser.error("--reuse-smoke requires --gpu-smoke")
    report = run_preflight(load_config(args.config), args.gpu_smoke, args.report_dir, args.reuse_smoke)
    print({"data": report["data_counts"], "gpu_smoke": report["gpu_smoke"], "full_training_started": False})


if __name__ == "__main__":
    main()
