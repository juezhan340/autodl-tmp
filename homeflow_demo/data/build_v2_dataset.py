"""组织 V2 任务生成、DeepSeek rollout、审查和 smoke 数据路由。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

from homeflow_demo.agents.deepseek_client import DeepSeekAPIError, DeepSeekClient
from homeflow_demo.agents.deepseek_policy import DeepSeekPolicy
from homeflow_demo.data.deepseek_task_reviewer import DeepSeekTaskReviewer
from homeflow_demo.data.deepseek_task_writer import DeepSeekTaskWriter
from homeflow_demo.data.static_task_validator import register_candidate, validate_task_candidate
from homeflow_demo.data.task_blueprints import TASK_CATEGORIES, TaskBlueprint, generate_task_blueprints
from homeflow_demo.data.trajectory_format import write_jsonl
from homeflow_demo.env.demo_scenario import build_demo_scenario
from homeflow_demo.env.models import ToolCall
from homeflow_demo.eval.deepseek_trajectory_judge import DeepSeekTrajectoryJudge
from homeflow_demo.eval.deterministic_audit import audit_episode
from homeflow_demo.eval.episode_runner import EpisodeRunner


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "smoke_runs" / "v2"


def build_v2_smoke(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    seed: int = 20260924,
    count_per_category: int = 1,
    concurrency: int = 5,
    judge_votes: int = 3,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    """执行每类指定数量任务的 V2 smoke，并保存完整中间结果。"""
    if count_per_category < 1:
        raise ValueError("count_per_category must be positive")
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    root = Path(output_dir)
    raw_root = root / "data_raw" / "v2"
    processed_root = root / "data_processed" / "v2"
    raw_root.mkdir(parents=True, exist_ok=True)
    processed_root.mkdir(parents=True, exist_ok=True)
    api_client = client or DeepSeekClient(raw_dir=raw_root)
    blueprints = generate_task_blueprints(
        count_per_category,
        split="smoke",
        seed=seed,
    )
    write_jsonl(raw_root / "blueprints.jsonl", [item.to_dict() for item in blueprints])

    writer = DeepSeekTaskWriter(api_client, concurrency=concurrency)
    writer_results = writer.generate(blueprints)
    write_jsonl(raw_root / "task_writer" / "results.jsonl", [item.to_dict() for item in writer_results])

    validations: list[dict[str, Any]] = []
    review_inputs: list[tuple[TaskBlueprint, dict[str, Any]]] = []
    registry: dict[str, str] = {}
    writer_by_id = {item.blueprint_id: item for item in writer_results}
    for blueprint in blueprints:
        writer_result = writer_by_id[blueprint.blueprint_id]
        for candidate_index, candidate in enumerate(writer_result.candidates):
            validation = validate_task_candidate(
                blueprint,
                candidate,
                seen_texts=registry,
            )
            validation_record = {
                "blueprint_id": blueprint.blueprint_id,
                "candidate_index": candidate_index,
                "candidate": candidate,
                **validation.to_dict(),
            }
            validations.append(validation_record)
            if validation.accepted:
                register_candidate(registry, validation, scenario_id=blueprint.blueprint_id)
                review_inputs.append((blueprint, candidate))
    write_jsonl(raw_root / "task_review" / "static_validations.jsonl", validations)

    reviewer = DeepSeekTaskReviewer(api_client, concurrency=concurrency)
    review_results = reviewer.review(review_inputs)
    write_jsonl(raw_root / "task_review" / "decisions.jsonl", [item.to_dict() for item in review_results])
    accepted_requests = _select_accepted_requests(review_results)
    scenarios = [
        blueprint.compile_scenario(accepted_requests[blueprint.blueprint_id])
        for blueprint in blueprints
        if blueprint.blueprint_id in accepted_requests
    ]
    write_jsonl(processed_root / "scenarios_smoke.jsonl", scenarios)

    rollout_records = _run_rollouts(scenarios, api_client, concurrency)
    write_jsonl(raw_root / "rollouts" / "episode_records.jsonl", rollout_records)
    judge = DeepSeekTrajectoryJudge(api_client, concurrency=min(3, concurrency))
    completed_records = _judge_and_route(
        scenarios,
        rollout_records,
        judge,
        judge_votes=judge_votes,
    )
    write_jsonl(raw_root / "trajectory_judge" / "records.jsonl", [
        {"scenario_id": item["scenario_id"], "semantic_result": item.get("semantic_result")}
        for item in completed_records
    ])
    route_counts = _write_routes(processed_root, completed_records)
    protocol_probe = run_protocol_feedback_probe()
    result = {
        "dataset_version": "v2-smoke",
        "count_per_category": count_per_category,
        "blueprint_count": len(blueprints),
        "writer_result_count": len(writer_results),
        "static_validation_count": len(validations),
        "review_input_count": len(review_inputs),
        "scenario_count": len(scenarios),
        "rollout_count": len(rollout_records),
        "route_counts": route_counts,
        "categories": list(TASK_CATEGORIES),
        "requested_concurrency": concurrency,
        "max_active_api_requests": api_client.max_active_requests,
        "protocol_feedback_probe": protocol_probe,
        "generated_at": time.time(),
    }
    (root / "smoke_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _select_accepted_requests(results: list[Any]) -> dict[str, str]:
    """为每个 Blueprint 选择第一个通过审查的候选。"""
    selected: dict[str, str] = {}
    for result in results:
        if result.accepted and result.blueprint_id not in selected:
            text = result.candidate.get("text")
            if isinstance(text, str) and text.strip():
                selected[result.blueprint_id] = text.strip()
    return selected


def _run_rollouts(
    scenarios: list[dict[str, Any]],
    client: DeepSeekClient,
    concurrency: int,
) -> list[dict[str, Any]]:
    """并发运行候选轨迹，验证 A/B/C 环境端并发。"""
    def run_one(scenario: dict[str, Any]) -> dict[str, Any]:
        """让一个 Scenario 使用独立 C/B 状态完成 rollout。"""
        try:
            policy = DeepSeekPolicy(client)
            run = EpisodeRunner(policy, model_id=policy.model_id).run(scenario)
            return run.to_dict()
        except DeepSeekAPIError as exc:
            return {
                "scenario_id": scenario["scenario_id"],
                "model_id": client.model,
                "route": "system_failure",
                "system_failure": {"code": exc.code, "message": str(exc)},
                "metadata": scenario.get("metadata", {}),
            }
        except Exception as exc:  # pragma: no cover - smoke 运行时保留异常上下文
            return {
                "scenario_id": scenario["scenario_id"],
                "model_id": client.model,
                "route": "system_failure",
                "system_failure": {"code": "RUNNER_ERROR", "message": str(exc)},
                "metadata": scenario.get("metadata", {}),
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(run_one, scenario) for scenario in scenarios]
        return [future.result() for future in futures]


def _judge_and_route(
    scenarios: list[dict[str, Any]],
    records: list[dict[str, Any]],
    judge: DeepSeekTrajectoryJudge,
    *,
    judge_votes: int,
) -> list[dict[str, Any]]:
    """对需要语义审查的类别调用 Judge 并确定最终 route。"""
    scenario_map = {item["scenario_id"]: item for item in scenarios}
    output: list[dict[str, Any]] = []
    for record in records:
        scenario_data = scenario_map.get(record["scenario_id"])
        if scenario_data is None:
            record["route"] = "system_failure"
            record["system_failure"] = {"code": "UNKNOWN_SCENARIO", "message": "scenario missing"}
            output.append(record)
            continue
        if record.get("route") == "system_failure":
            output.append(record)
            continue
        from homeflow_demo.env.schema import ensure_valid_scenario

        scenario = ensure_valid_scenario(scenario_data)
        deterministic = audit_episode(scenario, _episode_run_from_record(record))
        record["deterministic_result"] = deterministic
        category = scenario.task.category
        semantic_result = None
        if category in {"vague_intent", "dangerous_refusal", "environment_query"}:
            semantic_result = judge.judge(
                scenario,
                record,
                deterministic,
                votes=judge_votes,
            ).to_dict()
        record["semantic_result"] = semantic_result
        record["route"] = _route_record(record, category)
        output.append(record)
    return output


def _episode_run_from_record(record: dict[str, Any]) -> Any:
    """为确定性审查适配已序列化的 EpisodeRun 结构。"""
    from homeflow_demo.eval.episode_evaluator import EpisodeEvaluation
    from homeflow_demo.eval.episode_runner import EpisodeRun

    evaluation_data = record.get("evaluation", {})
    evaluation = EpisodeEvaluation(**evaluation_data)
    return EpisodeRun(trajectory=record, evaluation=evaluation)


def _route_record(record: dict[str, Any], category: str | None) -> str:
    """合并确定性和语义结果，禁止裁判挽救物理失败。"""
    evaluation = record.get("evaluation", {})
    if not evaluation.get("success"):
        return "failed"
    semantic = record.get("semantic_result")
    if category in {"vague_intent", "dangerous_refusal", "environment_query"}:
        if not isinstance(semantic, dict) or semantic.get("status") == "system_failure":
            return "system_failure"
        if semantic.get("status") == "rejected":
            return "semantic_rejected"
    if evaluation.get("strategy_error_count", 0) or evaluation.get("parse_error_count", 0):
        return "recovered_success"
    return "clean_success"


def _write_routes(root: Path, records: list[dict[str, Any]]) -> dict[str, int]:
    """按最终 route 写入可供后续 SFT/RL 使用的 JSONL 文件。"""
    groups: dict[str, list[dict[str, Any]]] = {
        "clean_success": [],
        "recovered_success": [],
        "semantic_rejected": [],
        "failed": [],
        "system_failure": [],
    }
    for record in records:
        groups.setdefault(str(record.get("route", "system_failure")), []).append(record)
    for name, items in groups.items():
        write_jsonl(root / f"trajectories_{name}.jsonl", items)
    return {name: len(items) for name, items in groups.items()}


def run_protocol_feedback_probe() -> dict[str, Any]:
    """用本地固定策略验证非法 JSON 消耗 turn 并收到 C 错误反馈。"""
    from homeflow_demo.data.scenario_generator import ScenarioGenerator

    scenario = ScenarioGenerator(20260924).generate(1, "train")[0]

    class ProbePolicy:
        """第一回合故意格式错误，后续按最小发现链继续。"""

        def __init__(self) -> None:
            """初始化探针响应和记录。"""
            self.responses = [
                "{invalid-json",
                {"tool_calls": [{"id": "probe_observe", "name": "observe_home", "arguments": {}}]},
                {"tool_calls": [{"id": "probe_room", "name": "inspect_room", "arguments": {"room_id": "room_bedroom"}}]},
                {"tool_calls": [{"id": "probe_device", "name": "inspect_device", "arguments": {"device_id": "device_bedroom_light"}}]},
                {"tool_calls": [{"id": "probe_finish", "name": "finish", "arguments": {"summary": "探针结束", "outcome": "completed"}}]},
            ]
            self.contexts: list[dict[str, Any]] = []
            self.cursor = 0

        def respond(self, context: dict[str, Any]) -> Any:
            """记录 C context 并返回下一条固定响应。"""
            self.contexts.append(context)
            response = self.responses[min(self.cursor, len(self.responses) - 1)]
            self.cursor += 1
            return response

    policy = ProbePolicy()
    run = EpisodeRunner(policy, model_id="protocol_probe").run(scenario)
    feedback_codes = [
        context.get("protocol_feedback", {}).get("code")
        for context in policy.contexts[1:]
        if isinstance(context.get("protocol_feedback"), dict)
    ]
    return {
        "turn_count": len(run.trajectory.get("turns", [])),
        "parse_error_count": run.evaluation.parse_error_count,
        "feedback_codes_seen": feedback_codes,
        "invalid_response_consumed_turn": run.evaluation.parse_error_count == 1
        and len(run.trajectory.get("turns", [])) >= 2,
    }


def main() -> None:
    """解析命令行参数并执行 V2 smoke 数据流水线。"""
    parser = argparse.ArgumentParser(description="Build HomeFlow V2 smoke dataset")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="smoke 输出目录")
    parser.add_argument("--seed", type=int, default=20260924, help="Blueprint seed")
    parser.add_argument("--count-per-category", type=int, default=1, help="每类任务尝试次数")
    parser.add_argument("--concurrency", type=int, default=5, help="API 和 rollout 并发上限")
    parser.add_argument("--judge-votes", type=int, default=3, help="每条语义轨迹的裁判票数")
    args = parser.parse_args()
    result = build_v2_smoke(
        args.output_dir,
        seed=args.seed,
        count_per_category=args.count_per_category,
        concurrency=args.concurrency,
        judge_votes=args.judge_votes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
