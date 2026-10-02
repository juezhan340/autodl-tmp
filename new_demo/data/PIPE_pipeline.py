"""编排：D0→D4 停闸；确认后再 D5→D6→复制。D5 模块不调 D6。"""

from __future__ import annotations

import json
import random
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from pathlib import Path
from typing import Any, Callable

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
from new_demo.data.D_copy_dataset import copy_success, write_dataset
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
    workers: int = 1,
) -> dict[str, Any]:
    """D1→D2→D3→D4。失败留表，过的发 bp_*，然后停闸。workers>1 时按条并发，编号仍按提交顺序。"""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    personas = load_personas()
    task_writer = DeepSeekTaskWriter(client)
    request_writer = DeepSeekRequestWriter(client)
    reviewer = DeepSeekInstructionReviewer(client)
    selected = tuple(categories) if categories else CATEGORIES
    unknown = [item for item in selected if item not in CATEGORIES]
    if unknown:
        raise ValueError(f"unknown categories: {unknown}")
    jobs = _plan_jobs(selected, count_per_category, seed, personas)
    results: list[dict[str, Any] | None] = [None] * len(jobs)

    def run_job(job: dict[str, Any]) -> dict[str, Any]:
        """线程里跑一条 D1→D4。"""
        print(f"start {job['category']}#{job['order'] + 1} seed={job['home_seed']}", flush=True)
        result = _generate_one_draft(job, task_writer, request_writer, reviewer)
        status = "pass" if result["passed"] else f"fail:{(result['failure'] or {}).get('stage')}"
        print(f"done  {job['category']}#{job['order'] + 1} {status}", flush=True)
        return result

    if workers == 1:
        for job in jobs:
            results[job["order"]] = run_job(job)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_job, job): job["order"] for job in jobs}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
    drafts = [item["draft"] for item in results if item]
    failures = [item["failure"] for item in results if item and item["failure"]]
    passed = [item["draft"] for item in results if item and item["passed"]]
    blueprints, _ = _number_blueprints(passed)
    root = Path(output_dir)
    _persist_d4(root, blueprints, failures, drafts)
    return {
        "blueprint_count": len(blueprints),
        "failure_count": len(failures),
        "attempt_count": len(drafts),
        "stopped_after": "D4",
        "workers": workers,
    }


def _plan_jobs(
    selected: tuple[str, ...],
    count_per_category: int,
    seed: int,
    personas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """主线程先排好类别、种子、画像，并发时配对不变。"""
    rng = random.Random(seed)
    serial_seed = seed
    jobs: list[dict[str, Any]] = []
    order = 0
    for category in selected:
        for _ in range(count_per_category):
            serial_seed += 1
            jobs.append(
                {
                    "order": order,
                    "category": category,
                    "home_seed": serial_seed,
                    "persona": copy_json(rng.choice(personas)),
                }
            )
            order += 1
    return jobs


def _generate_one_draft(
    job: dict[str, Any],
    task_writer: DeepSeekTaskWriter,
    request_writer: DeepSeekRequestWriter,
    reviewer: DeepSeekInstructionReviewer,
) -> dict[str, Any]:
    """一条样本：抽家、写 task、写用户话、D3、D4。"""
    category = job["category"]
    persona = job["persona"]
    s0 = make_home(job["home_seed"])
    draft: dict[str, Any] = {
        "category": category,
        "home": copy_json(s0),
        "persona_id": persona.get("persona_id"),
        "home_seed": job["home_seed"],
    }
    try:
        task_result = task_writer.write(s0=s0, persona=persona, category=category)
    except DeepSeekAPIError as exc:
        failure = {**draft, "stage": "D2_task", "error_code": exc.code, "message": str(exc)}
        return {"draft": draft, "passed": False, "failure": failure}
    if task_result.error_code or not task_result.task:
        failure = {
            **draft,
            "stage": "D2_task",
            "error_code": task_result.error_code,
            "message": task_result.error_message,
        }
        return {"draft": {**draft, "task_write": task_result.to_dict()}, "passed": False, "failure": failure}
    draft["task"] = task_result.task
    draft["probe"] = task_result.probe
    try:
        req_result = request_writer.write(category=category, task=task_result.task, home=s0)
    except DeepSeekAPIError as exc:
        failure = {**draft, "stage": "D2_request", "error_code": exc.code, "message": str(exc)}
        return {"draft": draft, "passed": False, "failure": failure}
    if req_result.error_code or not req_result.user_request:
        failure = {
            **draft,
            "stage": "D2_request",
            "error_code": req_result.error_code,
            "message": req_result.error_message,
        }
        return {"draft": draft, "passed": False, "failure": failure}
    draft["user_request"] = req_result.user_request
    try:
        review = reviewer.review(
            category=category,
            task=task_result.task,
            user_request=req_result.user_request,
            intent=task_result.task.get("intent"),
            home=s0,
        )
    except DeepSeekAPIError as exc:
        failure = {**draft, "stage": "D3", "error_code": exc.code, "message": str(exc)}
        return {"draft": draft, "passed": False, "failure": failure}
    draft["d3"] = review.to_dict()
    if not review.accept:
        failure = {
            **draft,
            "stage": "D3",
            "error_code": ",".join(review.codes) or "REJECTED",
            "message": "instruction review rejected",
        }
        return {"draft": draft, "passed": False, "failure": failure}
    oracle = check_blueprint(s0, task_result.task, task_result.probe)
    if not oracle.ok:
        failure = {
            **draft,
            "stage": "D4",
            "error_code": oracle.error_code,
            "message": oracle.message,
        }
        return {"draft": draft, "passed": False, "failure": failure}
    return {"draft": draft, "passed": True, "failure": None}


def run_full_pipeline(
    *,
    count_per_category: int,
    seed: int,
    output_dir: str | Path,
    client: DeepSeekClient,
    categories: tuple[str, ...] | list[str] | None = None,
    workers: int = 1,
    policy: Any | None = None,
) -> dict[str, Any]:
    """D1→D6 一次跑完，D4 之后不等人。两段都按 workers 并发。"""
    d4 = generate_until_d4(
        count_per_category=count_per_category,
        seed=seed,
        output_dir=output_dir,
        client=client,
        categories=categories,
        workers=workers,
    )
    if d4["blueprint_count"] == 0:
        return {**d4, "trajectories": 0, "copied": 0, "stopped_after": "dataset"}
    d5 = continue_from_d5(output_dir, client, policy=policy, workers=workers)
    return {**d4, **d5, "stopped_after": "dataset"}


def continue_from_d5(
    output_dir: str | Path,
    client: DeepSeekClient,
    policy: Any | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    """读已编号蓝图，D5 跑轨迹、D6 打票、复制数据集。workers>1 时按蓝图并发。"""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    root = Path(output_dir)
    processed = root / "data_processed"
    blueprints = _read_jsonl(processed / "D4_blueprints.jsonl")
    if not blueprints:
        raise RuntimeError("no D4_blueprints.jsonl to run")
    policy = policy or DeepSeekPolicy(client)
    judged: list[dict[str, Any] | None] = [None] * len(blueprints)

    def run_one_trajectory(index: int, blueprint: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """一条蓝图：C.run 然后 D6。"""
        scenario_id = f"sc_{index:03d}"
        # 每条轨迹单独一份 A 会话，并发时不能共用 messages
        used_policy = DeepSeekPolicy(client) if isinstance(policy, DeepSeekPolicy) else policy
        row = run_one(blueprint, used_policy, scenario_id)
        print(
            f"D5 {scenario_id} {blueprint.get('category')} labels={row['labels']}",
            flush=True,
        )
        judged_row = judge_one(row, client)
        print(
            f"D6 {scenario_id} {judged_row.get('category')} d6={judged_row.get('d6')}",
            flush=True,
        )
        return index, judged_row

    if workers == 1:
        for index, blueprint in enumerate(blueprints, start=1):
            _, row = run_one_trajectory(index, blueprint)
            judged[index - 1] = row
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(run_one_trajectory, index, blueprint)
                for index, blueprint in enumerate(blueprints, start=1)
            ]
            for future in as_completed(futures):
                index, row = future.result()
                judged[index - 1] = row
    rows = [item for item in judged if item is not None]
    _write_jsonl(processed / "D5_trajectories.jsonl", rows)
    stats = write_dataset(rows, root)
    stats["trajectories"] = len(rows)
    stats["stopped_after"] = "dataset"
    stats["workers"] = workers
    return stats


def run_quota_pipeline(
    *,
    target_success: int,
    max_attempts: int,
    seed: int,
    output_dir: str | Path,
    client: Any,
    categories: tuple[str, ...] | list[str] | None = None,
    workers_per_category: int = 10,
    sample_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """每类最多 max_attempts 次，凑满 target_success 条进集轨迹。五类并行，每类 workers_per_category 路。"""
    if target_success < 1:
        raise ValueError("target_success must be >= 1")
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if workers_per_category < 1:
        raise ValueError("workers_per_category must be >= 1")
    selected = tuple(categories) if categories else CATEGORIES
    unknown = [item for item in selected if item not in CATEGORIES]
    if unknown:
        raise ValueError(f"unknown categories: {unknown}")
    root = Path(output_dir)
    processed = root / "data_processed"
    if (processed / "D4_blueprints.jsonl").exists():
        raise RuntimeError(f"output dir already has data: {root}")
    personas = load_personas()
    jobs = _plan_jobs(selected, max_attempts, seed, personas)
    jobs_by_cat: dict[str, list[dict[str, Any]]] = {cat: [] for cat in selected}
    for job in jobs:
        jobs_by_cat[str(job["category"])].append(job)
    if sample_fn is None:
        task_writer = DeepSeekTaskWriter(client)
        request_writer = DeepSeekRequestWriter(client)
        reviewer = DeepSeekInstructionReviewer(client)

        def runner(job: dict[str, Any]) -> dict[str, Any]:
            """正式路径：一条从 D1 跑到 D6。"""
            return _run_one_full_sample(job, task_writer, request_writer, reviewer, client)
    else:
        runner = sample_fn
    sink = _QuotaSink(root, selected, target_success, max_attempts, workers_per_category)
    print(
        f"quota start cats={','.join(selected)} target={target_success} "
        f"max_attempts={max_attempts} workers_per_category={workers_per_category}",
        flush=True,
    )

    def fill(category: str) -> dict[str, Any]:
        """一类：10 路以内并发，成功满额或次数用尽就停。"""
        return _fill_category(
            category=category,
            jobs=jobs_by_cat[category],
            target_success=target_success,
            max_attempts=max_attempts,
            workers_per_category=workers_per_category,
            sample_fn=runner,
            sink=sink,
        )

    summaries: dict[str, Any] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(selected)) as outer:
        futures = {outer.submit(fill, cat): cat for cat in selected}
        for future in as_completed(futures):
            cat = futures[future]
            try:
                summaries[cat] = future.result()
            except Exception as exc:
                errors[cat] = f"{type(exc).__name__}: {exc}"
                print(f"quota {cat} crashed: {errors[cat]}", flush=True)
    stats = sink.finalize()
    stats["category_summaries"] = summaries
    stats["errors"] = errors
    stats["stopped_after"] = "dataset"
    stats["workers_per_category"] = workers_per_category
    stats["workers"] = workers_per_category * len(selected)
    stats["target_success"] = target_success
    stats["max_attempts"] = max_attempts
    if errors:
        stats["error_categories"] = errors
    print(f"quota done copied={stats.get('copied')} attempts={stats.get('attempt_count')}", flush=True)
    return stats


def _fill_category(
    *,
    category: str,
    jobs: list[dict[str, Any]],
    target_success: int,
    max_attempts: int,
    workers_per_category: int,
    sample_fn: Callable[[dict[str, Any]], dict[str, Any]],
    sink: "_QuotaSink",
) -> dict[str, Any]:
    """提交量不超过剩余名额；在飞任务失败后再补。"""
    budget = min(max_attempts, len(jobs))
    submitted = 0
    n_success = 0
    in_flight: dict[Any, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers_per_category) as pool:
        while True:
            # 在飞的也占名额，失败后再补，避免成功时多派
            needed = target_success - n_success - len(in_flight)
            capacity = workers_per_category - len(in_flight)
            remaining = budget - submitted
            to_submit = min(capacity, remaining, max(0, needed))
            for _ in range(max(0, to_submit)):
                job = copy_json(jobs[submitted])
                job["attempt"] = submitted + 1
                job["blueprint_id"] = f"bp_{category}_{job['attempt']:03d}"
                job["scenario_id"] = f"sc_{category}_{job['attempt']:03d}"
                submitted += 1
                print(
                    f"start {category}#{job['attempt']} seed={job['home_seed']} "
                    f"success={n_success}/{target_success} inflight={len(in_flight)+1}",
                    flush=True,
                )
                in_flight[pool.submit(sample_fn, job)] = job
            if not in_flight:
                break
            done, _ = wait(tuple(in_flight.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                job = in_flight.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "draft": {
                            "category": category,
                            "persona_id": job.get("persona", {}).get("persona_id")
                            if isinstance(job.get("persona"), dict)
                            else job.get("persona_id"),
                            "home_seed": job.get("home_seed"),
                            "attempt": job.get("attempt"),
                        },
                        "passed": False,
                        "failure": {
                            "category": category,
                            "stage": "RUN",
                            "error_code": "RUN_ERROR",
                            "message": f"{type(exc).__name__}: {exc}",
                            "attempt": job.get("attempt"),
                        },
                        "blueprint": None,
                        "trajectory": None,
                        "success": False,
                    }
                sink.record(category, result)
                status = "success" if result.get("success") else f"fail:{(result.get('failure') or {}).get('stage') or 'C/D6'}"
                print(
                    f"done  {category}#{job.get('attempt')} {status} "
                    f"success={sink.success_count(category)}/{target_success}",
                    flush=True,
                )
                if result.get("success"):
                    n_success += 1
    return {
        "category": category,
        "attempts": submitted,
        "success": n_success,
        "target": target_success,
        "met": n_success >= target_success,
    }


def _run_one_full_sample(
    job: dict[str, Any],
    task_writer: DeepSeekTaskWriter,
    request_writer: DeepSeekRequestWriter,
    reviewer: DeepSeekInstructionReviewer,
    client: Any,
) -> dict[str, Any]:
    """一条样本从抽家跑到 D6，成功与否看是否能进数据集。"""
    category = str(job["category"])
    result = _generate_one_draft(job, task_writer, request_writer, reviewer)
    draft = result["draft"]
    draft["attempt"] = job.get("attempt")
    if not result["passed"]:
        failure = result["failure"] or {}
        failure["attempt"] = job.get("attempt")
        return {
            "draft": draft,
            "passed": False,
            "failure": failure,
            "blueprint": None,
            "trajectory": None,
            "success": False,
        }
    blueprint = {
        "blueprint_id": job["blueprint_id"],
        "category": category,
        "home": copy_json(draft["home"]),
        "task": copy_json(draft["task"]),
        "user_request": draft["user_request"],
    }
    policy = DeepSeekPolicy(client)
    row = run_one(blueprint, policy, job["scenario_id"])
    print(
        f"D5 {job['scenario_id']} {category} labels={row['labels']}",
        flush=True,
    )
    judged = judge_one(row, client)
    print(
        f"D6 {job['scenario_id']} {category} d6={judged.get('d6')}",
        flush=True,
    )
    kept, _ = copy_success([judged])
    success = bool(kept)
    failure = None
    if not success:
        labels = judged.get("labels") or {}
        bad = [key for key in ("C-1", "C-2", "C-3", "C-4") if labels.get(key) is not True]
        failure = {
            "category": category,
            "stage": "D5" if bad else "D6",
            "error_code": ",".join(bad) if bad else str(judged.get("d6")),
            "message": "trajectory not copied",
            "attempt": job.get("attempt"),
            "scenario_id": job.get("scenario_id"),
            "user_request": blueprint.get("user_request"),
        }
    return {
        "draft": draft,
        "passed": True,
        "failure": failure,
        "blueprint": blueprint,
        "trajectory": judged,
        "success": success,
    }


class _QuotaSink:
    """配额跑次的落盘。追加草稿/失败/蓝图/轨迹，成功满额后进数据集。"""

    def __init__(
        self,
        root: Path,
        selected: tuple[str, ...],
        target_success: int,
        max_attempts: int,
        workers_per_category: int,
    ) -> None:
        """建目录和空 jsonl。"""
        self.root = root
        self.selected = selected
        self.target_success = target_success
        self.max_attempts = max_attempts
        self.workers_per_category = workers_per_category
        self.lock = threading.Lock()
        self.started = time.time()
        self.drafts: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.blueprints: list[dict[str, Any]] = []
        self.trajectories: list[dict[str, Any]] = []
        self.successes: dict[str, list[dict[str, Any]]] = {cat: [] for cat in selected}
        self.attempts: dict[str, int] = {cat: 0 for cat in selected}
        processed = root / "data_processed"
        raw = root / "data_raw"
        reports = root / "reports"
        processed.mkdir(parents=True, exist_ok=True)
        raw.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        for path in (
            processed / "D4_blueprints.jsonl",
            processed / "D5_trajectories.jsonl",
            processed / "D_dataset.jsonl",
            raw / "D34_failures.jsonl",
            raw / "D2_drafts.jsonl",
        ):
            path.write_text("", encoding="utf-8")
        self.processed = processed
        self.raw = raw
        self.reports = reports

    def success_count(self, category: str) -> int:
        """该类已进集条数。"""
        with self.lock:
            return len(self.successes[category])

    def record(self, category: str, result: dict[str, Any]) -> None:
        """一条结束就落盘，方便中途看进度。"""
        with self.lock:
            self.attempts[category] += 1
            draft = result.get("draft") or {"category": category}
            self.drafts.append(draft)
            _append_jsonl(self.raw / "D2_drafts.jsonl", draft)
            failure = result.get("failure")
            # D2–D4 / RUN 进失败表；轨迹没进集只留在 D5_trajectories
            if failure and result.get("blueprint") is None:
                self.failures.append(failure)
                _append_jsonl(self.raw / "D34_failures.jsonl", failure)
            blueprint = result.get("blueprint")
            if blueprint:
                self.blueprints.append(blueprint)
                _append_jsonl(self.processed / "D4_blueprints.jsonl", blueprint)
            trajectory = result.get("trajectory")
            if trajectory:
                self.trajectories.append(trajectory)
                _append_jsonl(self.processed / "D5_trajectories.jsonl", trajectory)
            if result.get("success") and trajectory is not None:
                if len(self.successes[category]) < self.target_success:
                    self.successes[category].append(trajectory)
            self._rewrite_outputs()

    def finalize(self) -> dict[str, Any]:
        """收尾写摘要。"""
        with self.lock:
            return self._rewrite_outputs(final=True)

    def _rewrite_outputs(self, final: bool = False) -> dict[str, Any]:
        """重写数据集、进度和 manifest。调用方必须持锁。"""
        kept: list[dict[str, Any]] = []
        per_category: dict[str, dict[str, int]] = {}
        for cat in self.selected:
            rows = self.successes[cat][: self.target_success]
            kept.extend(rows)
            per_category[cat] = {
                "attempts": self.attempts[cat],
                "blueprints": sum(1 for item in self.blueprints if item.get("category") == cat),
                "trajectories": sum(1 for item in self.trajectories if item.get("category") == cat),
                "success": len(rows),
                "target": self.target_success,
                "max_attempts": self.max_attempts,
            }
        stats = write_dataset(kept, self.root)
        stats["attempt_count"] = len(self.drafts)
        stats["blueprint_count"] = len(self.blueprints)
        stats["trajectories"] = len(self.trajectories)
        stats["failure_count"] = len(self.failures)
        stats["per_category"] = per_category
        stats["elapsed_sec"] = round(time.time() - self.started, 1)
        (self.processed / "D_manifest.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._write_progress(stats, final=final)
        _write_preview(self.reports / "D4_preview.md", self.blueprints, self.failures)
        return stats

    def _write_progress(self, stats: dict[str, Any], final: bool = False) -> None:
        """给人看的配额进度。"""
        title = "# 配额进度（完成）" if final else "# 配额进度"
        lines = [
            title,
            "",
            f"目标每类 {self.target_success} 条成功，最多尝试 {self.max_attempts}，每类并发 {self.workers_per_category}。",
            f"已用时 {stats.get('elapsed_sec')} 秒。",
            "",
            "```text",
        ]
        for cat in self.selected:
            item = stats["per_category"][cat]
            flag = "满" if item["success"] >= self.target_success else "…"
            lines.append(
                f"{cat}  {flag}  success {item['success']:>3}/{self.target_success}  "
                f"attempts {item['attempts']:>3}/{self.max_attempts}  "
                f"bp {item['blueprints']:>3}  traj {item['trajectories']:>3}"
            )
        lines.append("```")
        lines.append("")
        lines.append(
            f"合计 attempt {stats.get('attempt_count')}  blueprint {stats.get('blueprint_count')}  "
            f"traj {stats.get('trajectories')}  copied {stats.get('copied')}"
        )
        lines.append("")
        (self.reports / "progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if final:
            (self.reports / "quota.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    """追加一行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
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
