"""复用SFT的可追溯读写工具，隔离GRPO产物和原始检查点。"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load_helpers():
    """以独立模块名载入现有工具，避免两个目录的common同名冲突。"""
    spec = importlib.util.spec_from_file_location("sft_artifact_helpers", HERE.parent / "10-5_sft/common.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helpers = _load_helpers()
read_json = helpers.read_json
read_jsonl = helpers.read_jsonl
write_json = helpers.write_json
write_jsonl = helpers.write_jsonl
digest = helpers.digest
file_sha256 = helpers.file_sha256
annotate_json_tree = helpers.annotate_json_tree


def annotate_jsonl_tree(root):
    """为外部客户端追加的JSONL补说明，不重写原始响应与错误日志。"""
    for path in Path(root).rglob("*.jsonl"):
        rows = read_jsonl(path)
        keys = list(rows[0]) if rows else []
        helpers.atomic_text(path.with_suffix(".md"), f"# {path.name} 中文说明\n\n原始运行日志，共 {len(rows)} 行；不包含请求鉴权头。\n\n顶层字段：{', '.join(keys)}。\n")


def load_config(path=None):
    """读取候选配置并验证单次更新的组、轨迹和累计批次关系。"""
    config = read_json(path or HERE / "config.json")
    for key in ("groups_per_update", "num_generations", "rollout_parallel", "micro_batch", "accumulation", "max_length", "max_new_tokens"):
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f"invalid positive integer: {key}")
    if config["groups_per_update"] * config["num_generations"] != config["micro_batch"] * config["accumulation"]:
        raise ValueError("trajectory count does not equal micro_batch * accumulation")
    if config["rollout_parallel"] > config["num_generations"] or config["num_generations"] % config["rollout_parallel"]:
        raise ValueError("rollout_parallel must divide num_generations")
    if config["groups_per_update"] != len(config["smoke_categories"]):
        raise ValueError("one smoke task is required per configured category")
    for key in ("temperature", "learning_rate", "beta", "epsilon"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"invalid finite numeric parameter: {key}")
    if config["temperature"] <= 0 or not 0 < config["learning_rate"] < 1 or config["beta"] < 0 or not 0 < config["epsilon"] < 1:
        raise ValueError("invalid temperature, learning rate, beta or epsilon")
    return config
