"""读已经按 T 装配好的提示词文件，只把本轮材料填进 {{占位符}}。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "data_static" / "D0_templates"
PERSONAS_PATH = Path(__file__).resolve().parents[1] / "data_static" / "D0_personas.jsonl"

CATEGORY_TO_T = {
    "T1": "T1",
    "single_control": "T1",
    "T2": "T2",
    "multi_control": "T2",
    "T3": "T3",
    "vague_intent": "T3",
    "T4": "T4",
    "dangerous_refusal": "T4",
    "T5": "T5",
    "environment_query": "T5",
}

TASK_FILES = {
    "T1": "T1_single_control.md",
    "T2": "T2_multi_control.md",
    "T3": "T3_vague_intent.md",
    "T4": "T4_dangerous_refusal.md",
    "T5": "T5_environment_query.md",
}
REQUEST_FILES = {
    "T1": "D0_request_T1.md",
    "T2": "D0_request_T2.md",
    "T3": "D0_request_T3.md",
    "T4": "D0_request_T4.md",
    "T5": "D0_request_T5.md",
}
REVIEW_FILES = {
    "T1": "D3_review_T1.md",
    "T2": "D3_review_T2.md",
    "T3": "D3_review_T3.md",
    "T4": "D3_review_T4.md",
    "T5": "D3_review_T5.md",
}
D6_FILES = {"T3": "D6_T3.md", "T4": "D6_T4.md", "T5": "D6_T5.md"}
A_POLICY_FILE = "A_policy.md"

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def normalize_category(category: str) -> str:
    """把 single_control / T1 收成 T1。"""
    if category not in CATEGORY_TO_T:
        raise ValueError(f"unknown category: {category}")
    return CATEGORY_TO_T[category]


def load_template(kind: str, category: str) -> str:
    """task / request / review / D6 都按 T 分文件。"""
    code = normalize_category(category)
    if kind == "task":
        path = TEMPLATES_DIR / TASK_FILES[code]
    elif kind == "request":
        path = TEMPLATES_DIR / REQUEST_FILES[code]
    elif kind == "review":
        path = TEMPLATES_DIR / REVIEW_FILES[code]
    elif kind == "d6":
        if code not in D6_FILES:
            raise ValueError(f"D6 has no template for {code}")
        path = TEMPLATES_DIR / D6_FILES[code]
    else:
        raise ValueError(f"unknown template kind: {kind}")
    return path.read_text(encoding="utf-8")


def build_a_prompt(values: dict[str, Any]) -> str:
    """A 的提示词全任务共用一份，只填本轮 context。"""
    text = (TEMPLATES_DIR / A_POLICY_FILE).read_text(encoding="utf-8")
    return render_template(text, values)


def render_template(text: str, values: dict[str, Any]) -> str:
    """只替换 {{name}}。dict/list 写成 JSON；缺键或填完还有占位符就报错。"""

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError("template missing value for {{" + key + "}}")
        value = values[key]
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    filled = _PLACEHOLDER.sub(replacer, text)
    leftover = _PLACEHOLDER.findall(filled)
    if leftover:
        raise ValueError(f"unfilled placeholders: {leftover}")
    return filled


def build_prompt(kind: str, category: str, values: dict[str, Any]) -> str:
    """固定文件 + 本轮材料。T 规则已经写死在文件里。"""
    return render_template(load_template(kind, category), values)


def load_personas(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读二十五条画像。"""
    target = Path(path) if path else PERSONAS_PATH
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("persona must be an object")
        rows.append(item)
    return rows


def display_names_from_home(home: dict[str, Any]) -> str:
    """把 s0 里的 display_name 收成顿号分隔的一句，给 D2 第二次用。"""
    names: list[str] = []
    for device in home.get("devices", []):
        name = device.get("display_name")
        if isinstance(name, str) and name:
            names.append(name)
    return "、".join(names)


def rooms_from_home(home: dict[str, Any]) -> str:
    """把 s0 里的房间显示名收成顿号分隔的一句，给 D3 用。"""
    names: list[str] = []
    for room in home.get("rooms", []):
        name = room.get("display_name")
        if isinstance(name, str) and name:
            names.append(name)
    return "、".join(names)

