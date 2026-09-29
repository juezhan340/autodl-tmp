"""编排：D0→D4 停闸；确认后再 D5→D6→复制。D5 模块不调 D6。"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from new_demo.agents.A_policy import DeepSeekPolicy
from new_demo.agents.DeepSeek_client import DeepSeekAPIError, DeepSeekClient
from new_demo.data.D0_template import load_personas
from new_demo.data.D1_home_maker import make_home
from new_demo.data.D2_request_writer import DeepSeekRequestWriter
from new_demo.data.D2_task_writer import DeepSeekTaskWriter
from new_demo.data.D3_reviewer import DeepSeekInstructionReviewer
from new_demo.data.D4_oracle import check_blueprint
from new_demo.data.D5_run import run_one
from new_demo.data.D6_judge import judge_one
from new_demo.data.D_copy_dataset import write_dataset
from new_demo.env.B_models import copy_json


CATEGORIES = ("T1", "T2", "T3", "T4", "T5")


def run_until_d4(
    drafts: list[dict[str, Any]],
    output_dir: str | Path,
) -> dict[str, Any]:
    """已有草稿时只跑 D4。写出蓝图和失败表后停。"""
    root = Path(output_dir)
    blueprints, failures = _number_blueprints(drafts)
    _persist_d4(root, blueprints, failures, drafts)
    return {
        "blueprint_count": len(blueprints),
        "failure_count": len(failures),
        "stopped_after": "D4",
    }


def generate_until_d4(
    *,
    count_per_category: int,
    seed: int,
    output_dir: str | Path,
    client: DeepSeekClient,
    categories: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """D1→D2→D3→D4。失败留表，过的发 bp_*，然后停闸。"""
    rng = random.Random(seed)
    personas = load_personas()
    task_writer = DeepSeekTaskWriter(client)
    request_writer = DeepSeekRequestWriter(client)
    reviewer = DeepSeekInstructionReviewer(client)
    drafts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    serial_seed = seed
    selected = tuple(categories) if categories else CATEGORIES
    unknown = [item for item in selected if item not in CATEGORIES]
    if unknown:
        raise ValueError(f"unknown categories: {unknown}")
    for category in selected:
        for _ in range(count_per_category):
            serial_seed += 1
            s0 = make_home(serial_seed)
            persona = rng.choice(personas)
            draft: dict[str, Any] = {
                "category": category,
                "home": copy_json(s0),
                "persona_id": persona.get("persona_id"),
            }
            try:
                task_result = task_writer.write(s0=s0, persona=persona, category=category)
            except DeepSeekAPIError as exc:
                failures.append({**draft, "stage": "D2_task", "error_code": exc.code, "message": str(exc)})
                drafts.append(draft)
                continue
            if task_result.error_code or not task_result.task:
                failures.append(
                    {
                        **draft,
                        "stage": "D2_task",
                        "error_code": task_result.error_code,
                        "message": task_result.error_message,
                    }
                )
                drafts.append({**draft, "task_write": task_result.to_dict()})
                continue
            draft["task"] = task_result.task
            draft["probe"] = task_result.probe
            try:
                req_result = request_writer.write(category=category, task=task_result.task, home=s0)
            except DeepSeekAPIError as exc:
                failures.append({**draft, "stage": "D2_request", "error_code": exc.code, "message": str(exc)})
                drafts.append(draft)
                continue
            if req_result.error_code or not req_result.user_request:
                failures.append(
                    {
                        **draft,
                        "stage": "D2_request",
                        "error_code": req_result.error_code,
                        "message": req_result.error_message,
                    }
                )
                drafts.append(draft)
                continue
            draft["user_request"] = req_result.user_request
            try:
                review = reviewer.review(
                    category=category,
                    task=task_result.task,
                    user_request=req_result.user_request,
                    intent=task_result.task.get("intent"),
                )
            except DeepSeekAPIError as exc:
                failures.append({**draft, "stage": "D3", "error_code": exc.code, "message": str(exc)})
                drafts.append(draft)
                continue
            draft["d3"] = review.to_dict()
            if not review.accept:
                failures.append(
                    {
                        **draft,
                        "stage": "D3",
                        "error_code": ",".join(review.codes) or "REJECTED",
                        "message": "instruction review rejected",
                    }
                )
                drafts.append(draft)
                continue
            oracle = check_blueprint(s0, task_result.task, task_result.probe)
            if not oracle.ok:
                failures.append(
                    {
                        **draft,
                        "stage": "D4",
                        "error_code": oracle.error_code,
                        "message": oracle.message,
                    }
                )
                drafts.append(draft)
                continue
            passed.append(draft)
            drafts.append(draft)
    blueprints, _ = _number_blueprints(passed)
    root = Path(output_dir)
    _persist_d4(root, blueprints, failures, drafts)
    return {
        "blueprint_count": len(blueprints),
        "failure_count": len(failures),
        "attempt_count": len(drafts),
        "stopped_after": "D4",
    }


def continue_from_d5(
    output_dir: str | Path,
    client: DeepSeekClient,
    policy: Any | None = None,
) -> dict[str, Any]:
    """停闸确认之后才调用。依次 D5、D6、复制。"""
    root = Path(output_dir)
    processed = root / "data_processed"
    blueprints = _read_jsonl(processed / "D4_blueprints.jsonl")
    if not blueprints:
        raise RuntimeError("no D4_blueprints.jsonl to run")
    policy = policy or DeepSeekPolicy(client)
    rows: list[dict[str, Any]] = []
    for index, blueprint in enumerate(blueprints, start=1):
        scenario_id = f"sc_{index:03d}"
        row = run_one(blueprint, policy, scenario_id)
        print(
            f"D5 {scenario_id} {blueprint.get('category')} labels={row['labels']}",
            flush=True,
        )
        rows.append(row)
    judged = []
    for row in rows:
        judged_row = judge_one(row, client)
        print(
            f"D6 {judged_row['record']['scenario_id']} {judged_row.get('category')} d6={judged_row.get('d6')}",
            flush=True,
        )
        judged.append(judged_row)
    _write_jsonl(processed / "D5_trajectories.jsonl", judged)
    stats = write_dataset(judged, root)
    stats["trajectories"] = len(judged)
    stats["stopped_after"] = "dataset"
    return stats


def _number_blueprints(drafts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """过 D4 的发 bp_*；probe 不进蓝图。"""
    blueprints: list[dict[str, Any]] = []
    leftovers: list[dict[str, Any]] = []
    serial = 1
    for draft in drafts:
        if "task" not in draft or "user_request" not in draft or "home" not in draft:
            leftovers.append(draft)
            continue
        result = check_blueprint(draft["home"], draft["task"], draft.get("probe"))
        if not result.ok:
            leftovers.append(
                {
                    "category": draft.get("category"),
                    "user_request": draft.get("user_request"),
                    "task": copy_json(draft["task"]),
                    "error_code": result.error_code,
                    "message": result.message,
                    "stage": "D4",
                }
            )
            continue
        blueprints.append(
            {
                "blueprint_id": f"bp_{serial:03d}",
                "category": draft.get("category"),
                "home": copy_json(draft["home"]),
                "task": copy_json(draft["task"]),
                "user_request": draft["user_request"],
            }
        )
        serial += 1
    return blueprints, leftovers


def _persist_d4(
    root: Path,
    blueprints: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
) -> None:
    """落蓝图、失败表、草稿，删掉未确认的轨迹文件，写给人看的摘要。"""
    processed = root / "data_processed"
    raw = root / "data_raw"
    processed.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    _write_jsonl(processed / "D4_blueprints.jsonl", blueprints)
    _write_jsonl(raw / "D34_failures.jsonl", failures)
    _write_jsonl(raw / "D2_drafts.jsonl", drafts)
    trajectories = processed / "D5_trajectories.jsonl"
    if trajectories.exists():
        trajectories.unlink()
    _write_preview(root / "reports" / "D4_preview.md", blueprints, failures)


def _write_preview(path: Path, blueprints: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    """停闸给人看：每条蓝图的类别、用户话、设备和失败原因。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# D4 停闸预览", "", f"蓝图 {len(blueprints)} 条，失败 {len(failures)} 条。确认前不要跑 D5。", ""]
    for item in blueprints:
        names = "、".join(dev.get("display_name", "") for dev in item["home"].get("devices", []))
        lines.append(f"## {item['blueprint_id']}  {item.get('category')}")
        lines.append(f"用户话：{item.get('user_request')}")
        lines.append(f"设备：{names}")
        intent = (item.get("task") or {}).get("intent")
        lines.append(f"intent：{intent}")
        lines.append("")
    if failures:
        lines.append("## 失败草稿")
        for item in failures:
            lines.append(
                f"- {item.get('category')} stage={item.get('stage')} code={item.get('error_code')} {item.get('message')}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """覆盖写入 jsonl。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读一行一个对象。"""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
