# -*- coding: utf-8 -*-
"""用 shields.io 徽章接口查 star 数（GitHub API 匿名配额已耗尽时可用）。

shields 返回的是取整到 k 的近似值（如 75k），够用于"高星项目"标注；
数值带有 shields 自己的缓存，通常几小时内更新一次。
"""
import json
import time
import urllib.request
from pathlib import Path

DATA = Path(r"C:\Users\洛涧北府\AppData\Local\Temp\hf_analyze")

REPOS = [
    "hiyouga/LLaMA-Factory",
    "unslothai/unsloth",
    "huggingface/trl",
    "axolotl-ai-cloud/axolotl",
    "modelscope/ms-swift",
    "huggingface/peft",
    "microsoft/DeepSpeed",
    "Lightning-AI/litgpt",
    "volcengine/verl",
    "OpenRLHF/OpenRLHF",
    "THUDM/slime",
    "allenai/open-instruct",
    "hkust-nlp/simpleRL-reason",
    "Jiayi-Pan/TinyZero",
    "huggingface/open-r1",
    "Open-Reasoner-Zero/Open-Reasoner-Zero",
    "deepseek-ai/DeepSeek-R1",
    "vllm-project/vllm",
    "EleutherAI/lm-evaluation-harness",
    "QwenLM/Qwen2.5",
    "meta-llama/llama-cookbook",
    "tloen/alpaca-lora",
    "NVIDIA/NeMo-Aligner",
    "Taskar-LLM/Agent-FLAN",
    "zjunlp/KnowLM",
    "MediaBrain-SJTU/SLM-Distillation",
]

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
out = {}
for r in REPOS:
    try:
        req = urllib.request.Request(f"https://img.shields.io/github/stars/{r}.json",
                                     headers={"User-Agent": "research-helper"})
        d = json.loads(op.open(req, timeout=40).read().decode("utf-8", "replace"))
        out[r] = {"stars_text": d.get("value")}
        print(f"{str(d.get('value')):>7} | {r}")
    except Exception as e:  # noqa: BLE001
        out[r] = {"error": str(e)[:120]}
        print(f"   FAIL | {r} | {str(e)[:100]}")
    time.sleep(0.3)

(DATA / "gh_stars_shields.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved gh_stars_shields.json")
