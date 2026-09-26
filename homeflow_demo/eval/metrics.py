"""汇总 V1.2 EpisodeEvaluation 的小批量稳定指标。"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


def summarize_episode_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """从轨迹或直接评测记录汇总成功、错误、SFT 接收和奖励指标。"""
    evaluations = [_evaluation_from_record(record) for record in records]
    count = len(evaluations)
    failures = Counter(str(item.get("failure_class", "unknown")) for item in evaluations)
    return {
        "episode_count": count,
        "success_count": sum(bool(item.get("success")) for item in evaluations),
        "success_rate": _rate(sum(bool(item.get("success")) for item in evaluations), count),
        "accepted_for_sft_count": sum(
            bool(item.get("accepted_for_sft")) for item in evaluations
        ),
        "accepted_for_sft_rate": _rate(
            sum(bool(item.get("accepted_for_sft")) for item in evaluations), count
        ),
        "strategy_error_count": sum(int(item.get("strategy_error_count", 0)) for item in evaluations),
        "environment_failure_count": sum(
            int(item.get("environment_failure_count", 0)) for item in evaluations
        ),
        "unresolved_error_count": sum(
            int(item.get("unresolved_error_count", 0)) for item in evaluations
        ),
        "mean_reward": round(
            sum(float(item.get("reward", 0.0)) for item in evaluations) / count, 6
        ) if count else 0.0,
        "failure_class_counts": dict(sorted(failures.items())),
    }


def _evaluation_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """兼容完整轨迹字典和直接 EpisodeEvaluation 字典。"""
    evaluation = record.get("evaluation", record)
    if not isinstance(evaluation, dict):
        raise ValueError("record evaluation must be an object")
    return evaluation


def _rate(numerator: int, denominator: int) -> float:
    """安全计算六位小数比例。"""
    return round(numerator / denominator, 6) if denominator else 0.0
