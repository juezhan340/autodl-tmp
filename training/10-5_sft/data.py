"""筛选、分组划分轨迹并恢复可见消息，使用官方模板构建助手标签。"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from common import CATEGORIES, HERE, REPO_ROOT, canonical, data_dir, digest, file_sha256, load_config, read_json, read_jsonl, write_json, write_jsonl
from new_demo.data.D0_template import build_a_prompt
from new_demo.env.B_tool_schema import available_tools

# generation 标记只划定损失范围，渲染后的角色边界与原始 Qwen 模板保持一致。
TRAIN_TEMPLATE = """{%- for message in messages %}
{{- '<|im_start|>' + message['role'] + '\n' }}
{%- if message['role'] == 'assistant' %}
{% generation %}{{- message['content'] + '<|im_end|>' }}{% endgeneration %}
{%- else %}
{{- message['content'] + '<|im_end|>' }}
{%- endif %}
{{- '\n' }}
{%- endfor %}
{%- if add_generation_prompt %}{{- '<|im_start|>assistant\n' }}{%- endif %}"""


def clean_success(row: dict) -> bool:
    """只接收四标签全过、D6 合格、过程无错误的完整成功轨迹。"""
    if row.get("category") not in CATEGORIES or not all(row.get("labels", {}).get(k) is True for k in ("C-1", "C-2", "C-3", "C-4")):
        return False
    expected = "跳过" if row["category"] in ("T1", "T2") else "对"
    if row.get("d6") != expected:
        return False
    turns = row.get("record", {}).get("turns", [])
    if not turns or row["record"].get("protocol", {}).get("truncated"):
        return False
    for number, turn in enumerate(turns, 1):
        if turn.get("turn") != number or len(turn.get("tool_calls", [])) != 1:
            return False
        if len(turn.get("events", [])) != 1 or turn["events"][0].get("result", {}).get("ok") is not True:
            return False
        if turn["tool_calls"][0]["name"] == "finish" and number != len(turns):
            return False
    last = turns[-1]["tool_calls"][0]
    return last["name"] == "finish" and last["arguments"] == row["record"].get("finish")


def group_id(row: dict) -> str:
    """家庭和任务语义相同的改写题归同组，忽略运行 id 与隐藏 intent 的措辞。"""
    scenario = row["scenario"]
    home = json.loads(canonical(scenario["home"]))
    for room in home["rooms"]:
        room["device_ids"] = sorted(room["device_ids"])
    home["rooms"] = sorted(home["rooms"], key=room_key)
    home["devices"] = sorted(home["devices"], key=device_key)
    task = {key: value for key, value in scenario["task"].items() if key != "intent"}
    for key in ("conditions", "keep", "required_observations"):
        task[key] = sorted(task.get(key, []), key=canonical)
    return digest({"home": home, "task": task})


def room_key(room: dict) -> str:
    """按房间 id 排序，避免数组顺序改变分组。"""
    return room["room_id"]


def device_key(device: dict) -> str:
    """按设备 id 排序，保持分组指纹确定。"""
    return device["device_id"]


def sample_key(row: dict) -> str:
    """以场景内容排序，使输入 JSONL 行顺序不影响划分。"""
    return digest({"group": group_id(row), "request": row["scenario"]["user_request"]})


def features(row: dict) -> set[str]:
    """提取设备、动作、算子和保持条件覆盖，用于选择训练代表样本。"""
    result = set()
    devices = {d["device_id"]: d for d in row["scenario"]["home"]["devices"]}
    for turn in row["record"]["turns"]:
        call = turn["tool_calls"][0]
        arguments = call["arguments"]
        if arguments.get("device_id") in devices:
            result.add("device:" + devices[arguments["device_id"]]["device_type"])
        if call["name"] == "execute_action":
            result.add("action:" + arguments["action"])
    for condition in row["scenario"]["task"]["conditions"]:
        result.add("operator:" + condition.get("operator", "eq"))
    result.add("keep:" + str(bool(row["scenario"]["task"]["keep"])))
    finish = row["record"]["finish"]
    if finish.get("reason_code"):
        result.add("reason:" + finish["reason_code"])
    return result


def split_rows(rows: list[dict], config: dict) -> tuple[dict[str, list[dict]], dict]:
    """按组隔离和类别配额划分，训练集先覆盖可用特征再随机补齐。"""
    splits = {name: [] for name in ("train", "validation", "test", "reserve")}
    excluded = [r["scenario"]["scenario_id"] for r in rows if not clean_success(r)]
    groups = {}
    for row in sorted(rows, key=sample_key):
        if clean_success(row):
            key = group_id(row)
            if key in groups and groups[key]["category"] != row["category"]:
                raise ValueError("same task group has conflicting categories")
            groups.setdefault(key, row)
    coverage = {}
    for index, category in enumerate(CATEGORIES):
        candidates = [r for r in groups.values() if r["category"] == category]
        rng = random.Random(config["seed"] + index)
        rng.shuffle(candidates)
        n_train = config["train_per_category"]
        n_validation = config["validation_per_category"]
        n_test = config["test_per_category"]
        if len(candidates) < n_train + n_validation + n_test:
            raise ValueError(f"not enough independent {category} groups")
        selected, covered = [], set()
        # 优先保留能补充稀有动作或设备的示范，再按固定种子补齐训练配额。
        while len(selected) < n_train:
            gains = [len(features(row) - covered) for row in candidates]
            best = gains.index(max(gains))
            row = candidates.pop(best)
            selected.append(row)
            covered.update(features(row))
        rng.shuffle(selected)
        splits["train"].extend(selected)
        splits["validation"].extend(candidates[:n_validation])
        splits["test"].extend(candidates[n_validation:n_validation + n_test])
        splits["reserve"].extend(candidates[n_validation + n_test:])
        coverage[category] = sorted(covered)
    return splits, {"source_rows": len(rows), "eligible_groups": len(groups), "excluded_ids": excluded, "training_coverage": coverage}


def reconstruct_messages(row: dict) -> list[dict]:
    """恢复 A 实际使用的 JSON 文本对话，隐藏 task 与整屋状态不进入消息。"""
    turns = row["record"]["turns"]
    tools = turns[0]["observation_before"]["tools"]
    if tools != available_tools():
        raise ValueError("recorded public tool schema differs from current schema")
    messages = [{"role": "system", "content": build_a_prompt({"tools": tools})}, {"role": "user", "content": row["scenario"]["user_request"]}]
    for turn in turns:
        call = turn["tool_calls"][0]
        content = json.dumps({"name": call["name"], "arguments": call["arguments"]}, ensure_ascii=False)
        messages.append({"role": "assistant", "content": content})
        if call["name"] == "finish":
            break
        payload = turn["observation_after"]["last_tool_result"]
        messages.append({"role": "user", "content": "observation: " + json.dumps(payload, ensure_ascii=False)})
    return messages


def load_tokenizer(config: dict):
    """只从本地加载官方 tokenizer，并加入不改变文本的助手区域标记。"""
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(config["base_model"], local_files_only=True)
    tokenizer._sft_original_template = tokenizer.chat_template
    tokenizer.chat_template = TRAIN_TEMPLATE
    tokenizer.padding_side = "right"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def encode_record(record: dict, tokenizer, max_length: int) -> tuple[dict, dict]:
    """使用官方助手 mask 构造标签，检查每段 JSON 与结束 token 都被监督。"""
    messages = record["messages"]
    original = tokenizer.apply_chat_template(messages, chat_template=tokenizer._sft_original_template, tokenize=False, add_generation_prompt=False)
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    if original != rendered:
        raise ValueError("training template changed the original conversation text")
    encoded = tokenizer.apply_chat_template(messages, tokenize=True, return_dict=True, return_assistant_tokens_mask=True, add_generation_prompt=False)
    ids, mask = encoded["input_ids"], encoded["assistant_masks"]
    if len(ids) > max_length:
        raise ValueError(f"{record['sample_id']} is too long: {len(ids)} > {max_length}; truncation forbidden")
    spans, current = [], []
    for token, supervised in zip(ids, mask):
        if supervised:
            current.append(token)
        elif current:
            spans.append(current)
            current = []
    if current:
        spans.append(current)
    targets = [m["content"] for m in messages if m["role"] == "assistant"]
    if len(spans) != len(targets) or not spans:
        raise ValueError("assistant mask omitted or merged decision spans")
    for span, target in zip(spans, targets):
        if span[-1] != tokenizer.eos_token_id:
            raise ValueError("assistant end token is not supervised")
        if tokenizer.decode(span[:-1], skip_special_tokens=False) != target:
            raise ValueError("assistant mask includes a header/observation or misses JSON tokens")
    labels = [token if supervised else -100 for token, supervised in zip(ids, mask)]
    return {"input_ids": ids, "attention_mask": encoded["attention_mask"], "labels": labels}, {"tokens": len(ids), "target_tokens": sum(mask), "assistant_spans": len(spans)}


def provenance(config: dict) -> dict:
    """冻结输入、配置、提示词、schema 与 tokenizer 指纹。"""
    paths = [Path(config["dataset_source"]), REPO_ROOT / "new_demo/data_static/D0_templates/A_policy.md", REPO_ROOT / "new_demo/env/B_tool_schema.py", REPO_ROOT / "new_demo/eval/C_episode_evaluator.py", Path(config["base_model"]) / "tokenizer.json", Path(config["base_model"]) / "tokenizer_config.json", HERE / "data.py"]
    return {"config_sha256": digest(config), "files": {str(p): file_sha256(p) for p in paths}}


def prepare_data(config: dict, overwrite: bool = False) -> dict:
    """导出500/100/200及全部 mask 审计，已有不同版本产物时拒绝覆盖。"""
    root = data_dir(config)
    inputs = provenance(config)
    manifest_path = root / "manifest.json"
    if manifest_path.exists() and not overwrite:
        manifest = read_json(manifest_path)
        if manifest["provenance"] != inputs:
            raise ValueError("data provenance changed; choose a new output root or explicit overwrite")
        verify_manifest(config)
        return manifest
    rows = read_jsonl(config["dataset_source"])
    splits, audit = split_rows(rows, config)
    tokenizer = load_tokenizer(config)
    split_stats, output_hashes = {}, {}
    for name, selected in splits.items():
        records, scenarios, lengths, targets = [], [], [], []
        for row in selected:
            sample_id = row["scenario"]["scenario_id"]
            record = {"sample_id": sample_id, "group_id": group_id(row), "category": row["category"], "messages": reconstruct_messages(row)}
            _, checked = encode_record(record, tokenizer, config["max_length"])
            records.append(record)
            scenarios.append({"sample_id": sample_id, "group_id": record["group_id"], "category": row["category"], "scenario": row["scenario"]})
            lengths.append(checked["tokens"])
            targets.append(checked["target_tokens"])
        write_jsonl(root / f"{name}.jsonl", records, "可见消息供 SFT；只有 messages 送入 tokenizer，追溯字段不作为模型输入。")
        write_jsonl(root / f"{name}_scenarios.jsonl", scenarios, "隐藏 Scenario 只供环境评测和审计，不能作为 SFT 输入。")
        split_stats[name] = {"count": len(records), "categories": dict(Counter(r["category"] for r in records)), "max_tokens": max(lengths, default=0), "total_tokens": sum(lengths), "target_tokens": sum(targets), "group_ids": [r["group_id"] for r in records]}
        for suffix in ("", "_scenarios"):
            path = root / f"{name}{suffix}.jsonl"
            output_hashes[path.name] = file_sha256(path)
    manifest = {"provenance": inputs, "audit": audit, "splits": split_stats, "output_sha256": output_hashes, "scope": "preparation_only_no_full_training"}
    write_json(manifest_path, manifest)
    verify_manifest(config)
    return manifest


def verify_manifest(config: dict) -> dict:
    """加载时检查所有文件未被改动且四个场景集合完全隔离。"""
    root = data_dir(config)
    manifest = read_json(root / "manifest.json")
    if manifest["provenance"] != provenance(config):
        raise ValueError("source/config/template provenance mismatch")
    seen = set()
    for name, info in manifest["splits"].items():
        groups = set(info["group_ids"])
        if seen & groups or len(groups) != info["count"]:
            raise ValueError("scenario group leakage or duplicate groups")
        seen.update(groups)
    for filename, expected in manifest["output_sha256"].items():
        if file_sha256(root / filename) != expected:
            raise ValueError(f"prepared data was modified: {filename}")
    return manifest


def tokenized_split(config: dict, split: str, tokenizer) -> list[dict]:
    """只编码消息文件，不把配套隐藏 Scenario 或追溯字段交给模型。"""
    verify_manifest(config)
    return [encode_record(row, tokenizer, config["max_length"])[0] for row in read_jsonl(data_dir(config) / f"{split}.jsonl")]


def main() -> None:
    """命令行只准备数据；覆盖现有版本必须显式指定。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    report = prepare_data(load_config(args.config), args.overwrite)
    print({name: value["count"] for name, value in report["splits"].items()})


if __name__ == "__main__":
    main()
