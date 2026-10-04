"""加载基础模型或任一 LoRA 检查点，通过现有 C/B 进行多轮环境评测。"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from common import CATEGORIES, data_dir, load_config, read_jsonl, write_json, write_jsonl
from data import load_tokenizer, verify_manifest
from new_demo.agents.A_policy import DeepSeekPolicy
from new_demo.agents.DeepSeek_client import DeepSeekClient, DeepSeekResponse
from new_demo.data.D6_judge import judge_one
from new_demo.eval.C_episode_runner import EpisodeRunner


def load_inference_model(config: dict, adapter: str | None = None):
    """离线加载已有基础权重，按需重载一个 LoRA 检查点。"""
    import torch
    from transformers import AutoModelForCausalLM
    model = AutoModelForCausalLM.from_pretrained(config["base_model"], local_files_only=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa")
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, local_files_only=True)
    model.to("cuda")
    model.eval()
    model.config.use_cache = True
    return model, load_tokenizer(config)


class LocalGenerationClient:
    """把本地 generate 包装成现有 A_policy 的客户端接口，不发外部请求。"""

    def __init__(self, model, tokenizer, config: dict) -> None:
        """保存共享模型与 tokenizer，各 episode 的 messages 仍由 A 独立维护。"""
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.attempted_generations = 0
        self.successful_generations = 0

    def complete(self, messages, *, role, request_id=None, temperature=None):
        """每次只生成当前助手输出，长度超限时报错而不删除历史。"""
        import torch
        self.attempted_generations += 1
        if role != "A":
            raise ValueError("local generation client only handles A")
        started = time.perf_counter()
        encoded = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
        length = encoded["input_ids"].shape[-1]
        if length > self.config["max_length"]:
            raise ValueError("generation history exceeds configured input capacity")
        encoded = {key: value.to(self.model.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model.generate(**encoded, do_sample=False, max_new_tokens=self.config["max_new_tokens"], eos_token_id=self.tokenizer.eos_token_id, pad_token_id=self.tokenizer.pad_token_id)
        generated = output[0, length:]
        content = self.tokenizer.decode(generated, skip_special_tokens=True)
        self.successful_generations += 1
        return DeepSeekResponse(request_id=request_id or "local", role="A", content=content, raw_response={}, usage={"prompt_tokens": length, "completion_tokens": len(generated)}, elapsed_ms=(time.perf_counter() - started) * 1000, model="local-Qwen2.5-1.5B-Instruct")


def final_success(row: dict, semantic_mode: str) -> bool | None:
    """未做语义复核的合格 T3/T4/T5 不能被计成完整成功。"""
    if not all(row["labels"].get(k) is True for k in ("C-1", "C-2", "C-3", "C-4")):
        return False
    if row["category"] in ("T1", "T2"):
        return True
    if semantic_mode == "off":
        return None
    if row.get("d6") == "system_failure":
        return None
    return row.get("d6") == "对"


def evaluation_subset(rows: list[dict], per_category: int | None) -> list[dict]:
    """小型接口测试按类取少量样本，正式评测可使用整个固定集合。"""
    if per_category is None:
        return rows
    if per_category < 1:
        raise ValueError("per-category must be positive")
    selected = []
    for category in CATEGORIES:
        matches = [row for row in rows if row["category"] == category]
        selected.extend(matches[:per_category])
    return selected


def run_evaluation(config: dict, split: str, output: str | Path, adapter: str | None = None, per_category: int | None = None, semantic_mode: str = "off", confirm_test: bool = False) -> dict:
    """评测选定集合；测试集与收费 D6 调用均需明确选择。"""
    if split == "test" and not confirm_test:
        raise ValueError("final test evaluation requires --confirm-final-test")
    if split not in ("train", "validation", "test"):
        raise ValueError("invalid evaluation split")
    verify_manifest(config)
    output = Path(output)
    if (output / "trajectories.jsonl").exists():
        raise ValueError("evaluation output already exists; choose a new directory")
    scenarios = evaluation_subset(read_jsonl(data_dir(config) / f"{split}_scenarios.jsonl"), per_category)
    external = DeepSeekClient(raw_dir=output / "api") if semantic_mode == "deepseek" else None
    if external is not None and not external.api_key:
        raise ValueError("D6 requested but API key is not configured")
    model, tokenizer = load_inference_model(config, adapter)
    client = LocalGenerationClient(model, tokenizer, config)
    rows = []
    for task in scenarios:
        started = time.perf_counter()
        result = EpisodeRunner(DeepSeekPolicy(client)).run(task["scenario"])
        row = {"sample_id": task["sample_id"], "group_id": task["group_id"], "category": task["category"], "scenario": task["scenario"], "record": result.record, "labels": result.labels.to_dict(), "d6": "跳过" if task["category"] in ("T1", "T2") else "待审", "d6_votes": []}
        if external is not None:
            row = judge_one(row, external)
        row["final_success"] = final_success(row, semantic_mode)
        row["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        rows.append(row)
        write_jsonl(output / "trajectories.jsonl", rows, "环境交互与标签审计。隐藏 Scenario 仅供评测；final_success=null 表示尚无完整语义结论。")
    per_class = {}
    for category in CATEGORIES:
        subset = [r for r in rows if r["category"] == category]
        per_class[category] = {"total": len(subset), "program_success": sum(all(r["labels"].values()) for r in subset), "final_success": sum(r["final_success"] is True for r in subset), "pending_semantic": sum(r["final_success"] is None for r in subset), "c_failures": dict(Counter(k for r in subset for k, passed in r["labels"].items() if not passed))}
    summary = {"split": split, "model": config["base_model"], "adapter": adapter, "few_shot": False, "semantic_judge": semantic_mode, "total": len(rows), "per_category": per_class, "generation_attempts": client.attempted_generations, "successful_generations": client.successful_generations, "generation_errors": client.attempted_generations - client.successful_generations, "scope": "environment_evaluation_not_teacher_forced_accuracy"}
    write_json(output / "summary.json", summary)
    import torch
    del client, model
    torch.cuda.empty_cache()
    return summary


def main() -> None:
    """默认只评验证集，最终测试与 D6 均由显式参数控制。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    parser.add_argument("--adapter")
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-category", type=int)
    parser.add_argument("--semantic-judge", choices=("off", "deepseek"), default="off")
    parser.add_argument("--confirm-final-test", action="store_true")
    args = parser.parse_args()
    print(run_evaluation(load_config(args.config), args.split, args.output, args.adapter, args.per_category, args.semantic_judge, args.confirm_final_test))


if __name__ == "__main__":
    main()
