"""调用 DeepSeek 对查询、拒绝和模糊意图轨迹做语义裁判。"""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from dataclasses import dataclass
from typing import Any

from homeflow_demo.agents.deepseek_client import DeepSeekAPIError, DeepSeekClient
from homeflow_demo.env.models import Scenario, copy_json


TRAJECTORY_JUDGE_SYSTEM = """你是 HomeFlow 候选轨迹的受约束语义裁判。
只返回 JSON，不要 markdown，不要解释，不要 emoji。
JSON 必须包含 semantic_ok、answer_grounded、intent_match、refusal_valid、unsupported_claim、reason_codes、short_reason。
你只能依据用户请求、公开工具返回、assistant 的结构化 finish 和 C 的确定性摘要判断。
查询任务检查回答是否覆盖问题且事实来自工具 observation；拒绝任务检查是否明确拒绝、说明原因且没有声称执行成功；模糊意图检查是否符合唯一任务目标。
不重新执行设备动作，不创造隐藏真值，不把 C 已确认的物理失败改成成功。
同一个结论只说一次，short_reason 保持简短。
"""


@dataclass(frozen=True)
class JudgeVote:
    """保存一次独立语义裁判的结果。"""

    request_id: str
    decision: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None

    @property
    def valid(self) -> bool:
        """返回本票是否获得了可解析的结构化结果。"""
        return self.error_code is None and isinstance(self.decision.get("semantic_ok"), bool)


@dataclass(frozen=True)
class SemanticJudgeResult:
    """保存多票语义裁判合并结果。"""

    status: str
    semantic_ok: bool | None
    votes: tuple[JudgeVote, ...]
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """转换为轨迹结果中的 semantic_result。"""
        return {
            "status": self.status,
            "semantic_ok": self.semantic_ok,
            "votes": [
                {
                    "request_id": vote.request_id,
                    "decision": dict(vote.decision),
                    "error_code": vote.error_code,
                    "error_message": vote.error_message,
                }
                for vote in self.votes
            ],
            "judge_votes": [vote.decision.get("semantic_ok") for vote in self.votes if vote.valid],
            "reason_codes": list(self.reason_codes),
        }


class DeepSeekTrajectoryJudge:
    """使用三次独立 DeepSeek 调用降低单次语义裁判波动。"""

    def __init__(self, client: DeepSeekClient, *, concurrency: int = 3) -> None:
        """注入 DeepSeek 客户端并设置投票并发。"""
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.client = client
        self.concurrency = concurrency

    def judge(
        self,
        scenario: Scenario,
        trajectory: dict[str, Any],
        deterministic_result: dict[str, Any],
        *,
        votes: int = 3,
    ) -> SemanticJudgeResult:
        """对一条轨迹进行多票语义审查并返回 pass/rejected/system_failure。"""
        if votes < 1:
            raise ValueError("votes must be positive")
        payload = _judge_payload(scenario, trajectory, deterministic_result)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.concurrency, votes)) as executor:
            futures = [executor.submit(self._judge_once, payload, scenario.scenario_id, index) for index in range(votes)]
            results = [future.result() for future in futures]
        valid_votes = [vote for vote in results if vote.valid]
        if not valid_votes:
            return SemanticJudgeResult("system_failure", None, tuple(results), ("NO_VALID_JUDGE_VOTE",))
        positive = sum(bool(vote.decision.get("semantic_ok")) for vote in valid_votes)
        negative = len(valid_votes) - positive
        if len(valid_votes) < (votes // 2 + 1):
            status = "system_failure"
            semantic_ok = None
            codes = ("INSUFFICIENT_JUDGE_VOTES",)
        else:
            semantic_ok = positive > negative
            status = "pass" if semantic_ok else "rejected"
            codes = () if semantic_ok else ("SEMANTIC_REJECTED",)
        return SemanticJudgeResult(status, semantic_ok, tuple(results), codes)

    def _judge_once(
        self,
        payload: dict[str, Any],
        scenario_id: str,
        index: int,
    ) -> JudgeVote:
        """执行一次独立裁判调用并保留失败类型。"""
        request_id = f"trajectory_judge_{scenario_id}_{index}_{uuid.uuid4().hex[:8]}"
        messages = [
            {"role": "system", "content": TRAJECTORY_JUDGE_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ]
        try:
            _, decision = self.client.complete_json(
                messages,
                role="trajectory_judge",
                request_id=request_id,
                temperature=0.0,
            )
            return JudgeVote(request_id, _normalize_decision(decision))
        except (DeepSeekAPIError, ValueError, TypeError) as exc:
            return JudgeVote(
                request_id,
                {},
                error_code=getattr(exc, "code", "JUDGE_ERROR"),
                error_message=str(exc),
            )


def _judge_payload(
    scenario: Scenario,
    trajectory: dict[str, Any],
    deterministic_result: dict[str, Any],
) -> dict[str, Any]:
    """构造不含 hidden final_state 的裁判输入。"""
    return {
        "category": scenario.task.category or scenario.metadata.get("category"),
        "user_request": scenario.task.user_request,
        "turns": copy_json(trajectory.get("turns", [])),
        "finish_payload": copy_json(trajectory.get("finish_payload")),
        "deterministic_result": copy_json(deterministic_result),
    }


def _normalize_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """校验语义裁判的最小布尔字段。"""
    required = ("semantic_ok", "answer_grounded", "intent_match", "refusal_valid", "unsupported_claim")
    if any(not isinstance(decision.get(key), bool) for key in required):
        raise ValueError("trajectory judge response has invalid boolean fields")
    return {
        "semantic_ok": decision["semantic_ok"],
        "answer_grounded": decision["answer_grounded"],
        "intent_match": decision["intent_match"],
        "refusal_valid": decision["refusal_valid"],
        "unsupported_claim": decision["unsupported_claim"],
        "reason_codes": decision.get("reason_codes", []),
        "short_reason": str(decision.get("short_reason", "")),
    }
