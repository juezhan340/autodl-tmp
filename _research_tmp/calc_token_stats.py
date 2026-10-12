"""统计 quota200_20261004_v2 数据集里单条轨迹的 token 长度。

规则与 training/10-5_sft/data.py 的 reconstruct_messages 一致：
system(A_policy+工具表) -> user(用户话) -> 每轮 assistant JSON -> user observation。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from new_demo.data.D0_template import build_a_prompt  # noqa: E402
from new_demo.env.B_tool_schema import available_tools  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

DATA = ROOT / "new_demo/runs/quota200_20261004_v2/data_processed/D_dataset.jsonl"
TOKENIZER_DIR = Path(r"D:\D_program\models\Qwen2.5-1.5B-Instruct")

# 与 training/10-5_sft/data.py 相同的损失边界模板（渲染文本与官方模板一致）。
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


def reconstruct_messages(row: dict) -> tuple[list[dict], bool]:
    """重建 A 的对话；返回 (messages, 工具表是否与当前 schema 一致)。"""
    turns = row["record"]["turns"]
    tools = turns[0]["observation_before"]["tools"]
    tools_match = tools == available_tools()
    messages = [
        {"role": "system", "content": build_a_prompt({"tools": tools})},
        {"role": "user", "content": row["scenario"]["user_request"]},
    ]
    for turn in turns:
        call = turn["tool_calls"][0]
        messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {"name": call["name"], "arguments": call["arguments"]},
                    ensure_ascii=False,
                ),
            }
        )
        if call["name"] == "finish":
            break
        payload = turn["observation_after"]["last_tool_result"]
        messages.append(
            {"role": "user", "content": "observation: " + json.dumps(payload, ensure_ascii=False)}
        )
    return messages, tools_match


def describe(values: list[int]) -> dict:
    """均值/中位/分位/极值。"""
    ordered = sorted(values)
    n = len(ordered)
    return {
        "count": n,
        "mean": round(sum(ordered) / n, 1),
        "median": ordered[n // 2],
        "p90": ordered[int(n * 0.90)],
        "p95": ordered[int(n * 0.95)],
        "min": ordered[0],
        "max": ordered[-1],
    }


def main() -> None:
    """逐条统计输入 token 与监督 token。"""
    tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER_DIR), local_files_only=True)
    original_template = tokenizer.chat_template
    tokenizer.chat_template = TRAIN_TEMPLATE
    input_lengths: list[int] = []
    supervised: list[int] = []
    raw_chars: list[int] = []
    per_category: dict[str, list[int]] = {}
    tools_mismatch = 0
    template_mismatch = 0
    with open(DATA, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            messages, tools_match = reconstruct_messages(row)
            tools_mismatch += 0 if tools_match else 1
            rendered_new = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            rendered_original = tokenizer.apply_chat_template(
                messages,
                chat_template=original_template,
                tokenize=False,
                add_generation_prompt=False,
            )
            template_mismatch += 0 if rendered_new == rendered_original else 1
            encoded = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                return_dict=True,
                return_assistant_tokens_mask=True,
                add_generation_prompt=False,
            )
            masks = encoded.get("assistant_masks")
            if masks is None:
                masks = encoded.get("assistant_tokens_mask")
            n_input = len(encoded["input_ids"])
            n_sup = sum(masks) if masks is not None else -1
            input_lengths.append(n_input)
            supervised.append(n_sup)
            raw_chars.append(len(line))
            per_category.setdefault(row["category"], []).append(n_input)
    report = {
        "rows": len(input_lengths),
        "tools_mismatch_rows": tools_mismatch,
        "template_mismatch_rows": template_mismatch,
        "input_tokens": describe(input_lengths),
        "supervised_tokens": describe(supervised),
        "raw_row_chars": describe(raw_chars),
        "per_category_input_mean": {
            key: round(sum(values) / len(values), 1) for key, values in sorted(per_category.items())
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
