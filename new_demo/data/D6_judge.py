"""D6：只审 C 四步全过且待审的 T3/T4/T5，三票对错。"""

from __future__ import annotations

import uuid
from typing import Any

from new_demo.agents.DeepSeek_client import DeepSeekAPIError, DeepSeekClient
from new_demo.data.D0_template import build_prompt, normalize_category
from new_demo.env.B_models import copy_json


def judge_one(row: dict[str, Any], client: DeepSeekClient) -> dict[str, Any]:
    """写回同一条 sc_*。解析失败不记成错。"""
    labels = row.get("labels") or {}
    if not all(labels.get(key) is True for key in ("C-1", "C-2", "C-3", "C-4")):
        return row
    code = normalize_category(str(row.get("category", "")))
    if code in {"T1", "T2"}:
        row["d6"] = "跳过"
        return row
    if row.get("d6") != "待审":
        return row
    record = row.get("record") or {}
    user_request = (row.get("scenario") or {}).get("user_request", "")
    votes: list[dict[str, Any]] = []
    valid: list[str] = []
    for index in range(1, 4):
        request_id = f"d6_{record.get('scenario_id', 'sc')}_{index}_{uuid.uuid4().hex[:6]}"
        try:
            prompt = build_prompt(
                "d6",
                code,
                {
                    "category": code,
                    "user_request": user_request,
                    "finish": record.get("finish"),
                    "turns": record.get("turns"),
                },
            )
            _, parsed = client.complete_json(
                [{"role": "user", "content": prompt}],
                role="external",
                request_id=request_id,
            )
            verdict = parsed.get("verdict")
            if verdict in {"对", "错"}:
                votes.append({"verdict": verdict, "request_id": request_id})
                valid.append(verdict)
            else:
                votes.append({"verdict": None, "request_id": request_id, "error": "bad_verdict"})
        except (DeepSeekAPIError, ValueError, KeyError) as exc:
            votes.append({"verdict": None, "request_id": request_id, "error": str(exc)})
    row["d6_votes"] = copy_json(votes)
    if len(valid) < 3:
        row["d6"] = "system_failure"
    elif valid.count("对") >= 2:
        row["d6"] = "对"
    else:
        row["d6"] = "错"
    return row
