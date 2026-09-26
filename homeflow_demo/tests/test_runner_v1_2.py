"""验证 V1.2 C 模块的解析、终止、评测和质量门禁。"""

from __future__ import annotations

import unittest
from typing import Any

from homeflow_demo.agents.oracle_policy import OraclePolicy
from homeflow_demo.data.scenario_generator import ScenarioGenerator
from homeflow_demo.env.demo_scenario import build_demo_scenario
from homeflow_demo.env.models import AssistantTurn, ToolCall
from homeflow_demo.env.tool_schema import classify_error
from homeflow_demo.eval.episode_runner import EpisodeRunner, parse_assistant_response


class FixedPolicy:
    """按预置响应顺序返回 assistant 输出。"""

    def __init__(self, responses: list[Any]) -> None:
        """复制响应序列并初始化游标。"""
        self.responses = list(responses)
        self.cursor = 0

    def respond(self, context: dict[str, Any]) -> Any:
        """返回下一条响应，耗尽后用纯文本结束。"""
        del context
        if self.cursor >= len(self.responses):
            return {"content": "结束。"}
        response = self.responses[self.cursor]
        self.cursor += 1
        return response


class EpisodeRunnerV12Test(unittest.TestCase):
    """覆盖 C 模块的统一轨迹和错误归因。"""

    def test_oracle_success_is_replayable_and_accepted(self) -> None:
        """确认可行任务的 Oracle 成功轨迹通过 SFT 门禁。"""
        scenario = build_demo_scenario()
        run = EpisodeRunner(OraclePolicy(scenario), model_id="oracle_test").run(scenario)
        self.assertTrue(run.evaluation.success)
        self.assertTrue(run.evaluation.trajectory_replayable)
        self.assertTrue(run.evaluation.accepted_for_sft)
        self.assertEqual(run.evaluation.rejection_reasons, [])

    def test_readonly_failure_is_strategy_error_and_replayable(self) -> None:
        """确认传感器写失败被稳定归因且失败轨迹仍可重放。"""
        scenario = ScenarioGenerator(20260924).generate(7, "train")[-1]
        run = EpisodeRunner(OraclePolicy(scenario)).run(scenario)
        self.assertFalse(run.evaluation.success)
        self.assertEqual(run.evaluation.failure_class, "strategy_error")
        self.assertEqual(run.evaluation.strategy_error_count, 1)
        self.assertTrue(run.evaluation.trajectory_replayable)
        self.assertFalse(run.evaluation.accepted_for_sft)

    def test_finish_followed_by_call_is_rejected(self) -> None:
        """确认同一 assistant turn 在 finish 后继续调用会被记录。"""
        scenario = ScenarioGenerator(20260929).generate(6, "train")[-1]
        policy = FixedPolicy(
            [
                {
                    "tool_calls": [
                        {"id": "finish_first", "name": "finish", "arguments": {"summary": "完成"}},
                        {"id": "late_call", "name": "observe_home", "arguments": {}},
                    ]
                }
            ]
        )
        run = EpisodeRunner(policy).run(scenario)
        self.assertEqual(run.evaluation.post_terminal_action_count, 1)
        self.assertFalse(run.evaluation.accepted_for_sft)
        self.assertIn("post_terminal_action", run.evaluation.rejection_reasons)

    def test_same_turn_discovery_dependency_is_rejected(self) -> None:
        """确认模型不能在一个输出中消费刚获得的房间目录。"""
        scenario = build_demo_scenario()
        policy = FixedPolicy(
            [
                {
                    "tool_calls": [
                        {"id": "observe", "name": "observe_home", "arguments": {}},
                        {
                            "id": "inspect_same_turn",
                            "name": "inspect_room",
                            "arguments": {"room_id": "room_bedroom"},
                        },
                    ]
                }
            ]
        )
        run = EpisodeRunner(policy).run(scenario)
        self.assertGreaterEqual(run.evaluation.strategy_error_count, 1)
        self.assertTrue(run.evaluation.trajectory_replayable)
        self.assertFalse(run.evaluation.accepted_for_sft)

    def test_openai_response_and_plain_text_are_normalized(self) -> None:
        """确认 OpenAI function call 和纯文本终答进入统一 ToolCall。"""
        parsed = parse_assistant_response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "observe_home", "arguments": "{}"},
                                }
                            ]
                        }
                    }
                ]
            },
            1,
        )
        self.assertEqual(parsed.tool_calls[0].name, "observe_home")
        final_turn = parse_assistant_response(AssistantTurn(text="任务结束。"), 2)
        self.assertEqual(final_turn.tool_calls[0].name, "finish")

    def test_missing_call_id_is_protocol_error(self) -> None:
        """确认缺少 call_id 的规范调用不能进入 B。"""
        scenario = build_demo_scenario()
        policy = FixedPolicy(
            [{"tool_calls": [{"name": "observe_home", "arguments": {}}]}]
        )
        run = EpisodeRunner(policy).run(scenario)
        self.assertGreaterEqual(run.evaluation.strategy_error_count, 1)
        self.assertFalse(run.evaluation.accepted_for_sft)

    def test_error_categories_separate_policy_system_and_unresolved(self) -> None:
        """确认三类错误不会在 reward 归因时混为一谈。"""
        self.assertEqual(classify_error("UNKNOWN_DEVICE"), "strategy_error")
        self.assertEqual(classify_error("DEVICE_UNAVAILABLE"), "environment_failure")
        self.assertEqual(classify_error("SERVICE_ERROR"), "unresolved")

    def test_unavailable_device_is_environment_failure(self) -> None:
        """确认设备离线会截断 episode，且不增加策略错误。"""
        scenario = ScenarioGenerator(20260924).generate(1, "train")[0]
        for device in scenario["home"]["devices"]:
            if device["device_id"] == "device_bedroom_light":
                device["available"] = False
        run = EpisodeRunner(OraclePolicy(scenario)).run(scenario)
        self.assertEqual(run.evaluation.failure_class, "environment_failure")
        self.assertEqual(run.evaluation.environment_failure_count, 1)
        self.assertEqual(run.evaluation.strategy_error_count, 0)
        self.assertTrue(run.evaluation.truncated)
        self.assertTrue(run.evaluation.trajectory_replayable)


if __name__ == "__main__":
    unittest.main()
