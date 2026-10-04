"""提供本轮训练的配置、可追溯文件读写和离线运行约束。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT))
CATEGORIES = ("T1", "T2", "T3", "T4", "T5")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def read_json(path: str | Path) -> Any:
    """读取完整 JSON，由调用方校验业务形状。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict]:
    """读取非空 JSONL 行，不静默跳过损坏记录。"""
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical(value: Any) -> str:
    """以固定键顺序序列化，用于指纹而不是助手正文。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    """计算结构化数据的确定性 SHA-256。"""
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    """分块计算文件指纹，避免把模型权重一次读入内存。"""
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def atomic_text(path: str | Path, text: str) -> None:
    """同目录临时写入再替换，不留下半份报告。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def describe_json(path: str | Path) -> None:
    """为生成的 JSON 配同名中文说明；长数据只展示形状和计数。"""
    path = Path(path)
    value = read_json(path)
    pretty = json.dumps(value, ensure_ascii=False, indent=2)
    if len(pretty) <= 24000:
        body = "```json\n" + pretty + "\n```\n"
    else:
        shape = {"类型": type(value).__name__, "数量或顶层键": len(value) if isinstance(value, list) else list(value)}
        body = "数据较长，内容形状如下；完整内容见同名 JSON。\n\n```json\n" + json.dumps(shape, ensure_ascii=False, indent=2) + "\n```\n"
    atomic_text(path.with_suffix(".md"), f"# {path.name} 中文说明\n\n本文件记录运行配置、统计或检查点元数据，不含密钥。\n\n{body}")


def write_json(path: str | Path, value: Any) -> None:
    """写 JSON 并同步生成同名中文说明。"""
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    describe_json(path)


def write_jsonl(path: str | Path, rows: list[dict], description: str) -> None:
    """写多条记录及其中文用途说明，正文不复制整批数据。"""
    path = Path(path)
    atomic_text(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    keys = list(rows[0]) if rows else []
    atomic_text(path.with_suffix(".md"), f"# {path.name} 中文说明\n\n{description}\n\n共 {len(rows)} 行。顶层字段：{', '.join(keys)}。\n")


def annotate_json_tree(root: str | Path) -> None:
    """补齐 Trainer 和 PEFT 自动生成的 JSON 中文说明。"""
    for path in Path(root).rglob("*.json"):
        describe_json(path)


def load_config(path: str | Path | None = None) -> dict:
    """读取本轮配置，并把相对数据路径固定到仓库根。"""
    config = read_json(path or HERE / "config.json")
    required = set(read_json(HERE / "config.json"))
    if set(config) != required:
        raise ValueError("config keys must match config.json")
    for key in ("base_model", "dataset_source", "output_root"):
        value = Path(config[key]).expanduser()
        config[key] = str(value if value.is_absolute() else REPO_ROOT / value)
    for key in ("train_per_category", "validation_per_category", "test_per_category", "max_length", "epochs", "micro_batch_size", "gradient_accumulation_steps", "lora_r", "lora_alpha", "max_new_tokens"):
        if not isinstance(config[key], int) or isinstance(config[key], bool) or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if not 0 < config["learning_rate"] < 1 or not 0 <= config["lora_dropout"] < 1:
        raise ValueError("invalid learning rate or LoRA dropout")
    return config


def data_dir(config: dict) -> Path:
    """返回默认仓库外的数据产物目录。"""
    return Path(config["output_root"]) / "data"
