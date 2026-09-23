"""验证 HomeEnv 的状态、奖励和 episode 边界。"""

import unittest

from homeflow_demo.env import Action, AssistantTurn, HomeEpisodeEnv
from homeflow_demo.env.demo_scenario import build_demo_scenario
from homeflow_demo.env.tool_schema import normalize_action


class HomeEpisodeEnvTest(unittest.TestCase):
    """覆盖 HomeEnv 第一版必须稳定的行为契约。"""

    def test_successful_episode(self) -> None:
        """合法控制动作后 finish 应得到成功终局。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        first = env.step(Action("control_device", {
            "device_id": "bedroom.light",
            "command": "set_power",
            "value": "off",
        }))
        second = env.step(Action("control_device", {
            "device_id": "bedroom.air_conditioner",
            "command": "set_temperature",
            "value": 26,
        }))
        final = env.step(Action("finish", {"summary": "任务已完成。"}))

        self.assertFalse(first.terminated)
        self.assertFalse(second.terminated)
        self.assertTrue(final.terminated)
        self.assertFalse(final.truncated)
        self.assertTrue(env.final_result().success)
        self.assertEqual(env.final_result().completion, 1.0)

    def test_invalid_action_does_not_mutate_state(self) -> None:
        """非法参数只能产生错误和惩罚，不能修改设备状态。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        before = env.devices
        result = env.step(Action("control_device", {
            "device_id": "bedroom.air_conditioner",
            "command": "set_temperature",
            "value": 99,
        }))

        self.assertFalse(result.info["ok"])
        self.assertEqual(result.info["error_code"], "VALUE_OUT_OF_RANGE")
        self.assertEqual(before, env.devices)
        self.assertEqual(env.final_result().completion, 0.0)

    def test_snapshot_restore(self) -> None:
        """恢复快照后应回到保存时的设备状态和轨迹位置。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        env.step(Action("control_device", {
            "device_id": "bedroom.light",
            "command": "set_power",
            "value": "off",
        }))
        snapshot = env.snapshot()
        env.step(Action("control_device", {
            "device_id": "bedroom.air_conditioner",
            "command": "set_temperature",
            "value": 26,
        }))
        env.restore(snapshot)

        self.assertEqual(env.devices["bedroom.light"]["state"]["power"], "off")
        self.assertEqual(env.devices["bedroom.air_conditioner"]["state"]["temperature"], 24)
        self.assertEqual(len(env.trajectory()), 1)

    def test_fork_is_independent(self) -> None:
        """同一 episode 的两个分支不能互相修改设备状态。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        left = env.fork()
        right = env.fork()
        left.step(Action("control_device", {
            "device_id": "bedroom.light",
            "command": "set_power",
            "value": "off",
        }))

        self.assertEqual(left.devices["bedroom.light"]["state"]["power"], "off")
        self.assertEqual(right.devices["bedroom.light"]["state"]["power"], "on")
        self.assertEqual(env.devices["bedroom.light"]["state"]["power"], "on")

    def test_max_steps_truncates_episode(self) -> None:
        """达到最大步数后应返回 truncated，而不是误报成功。"""
        scenario = build_demo_scenario()
        scenario["max_steps"] = 1
        env = HomeEpisodeEnv()
        env.reset(scenario)
        result = env.step(Action("query_device", {
            "device_id": "bedroom.light",
            "fields": ["power"],
        }))

        self.assertFalse(result.terminated)
        self.assertTrue(result.truncated)
        self.assertFalse(env.final_result().success)
        self.assertEqual(env.final_result().failure_reason, "MAX_STEPS")

    def test_single_target_can_finish_after_one_control(self) -> None:
        """单目标任务完成一次控制后即可正常 finish。"""
        scenario = build_demo_scenario()
        scenario["goal"]["predicates"] = [
            {"device_id": "bedroom.light", "field": "power", "equals": "off"}
        ]
        env = HomeEpisodeEnv()
        env.reset(scenario)
        env.step(Action("control_device", {
            "device_id": "bedroom.light",
            "command": "set_power",
            "value": "off",
        }))
        result = env.step(Action("finish", {"summary": "灯已关闭。"}))

        self.assertTrue(result.info["success"])
        self.assertTrue(env.final_result().success)

    def test_finish_before_goal_terminates_with_failure(self) -> None:
        """未完成目标时 finish 应结束 episode 并报告失败原因。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        result = env.step(Action("finish", {"summary": "提前结束。"}))

        self.assertTrue(result.terminated)
        self.assertFalse(result.truncated)
        self.assertFalse(result.info["success"])
        self.assertEqual(env.final_result().failure_reason, "FINISH_BEFORE_GOAL")

    def test_already_satisfied_goal_can_finish(self) -> None:
        """初始状态已经满足目标时，合法 finish 可以直接成功。"""
        scenario = build_demo_scenario()
        scenario["goal"]["predicates"] = [
            {"device_id": "bedroom.light", "field": "power", "equals": "on"}
        ]
        env = HomeEpisodeEnv()
        env.reset(scenario)
        result = env.step(Action("finish", {"summary": "目标已满足。"}))

        self.assertTrue(result.terminated)
        self.assertTrue(result.info["success"])
        self.assertTrue(env.final_result().success)

    def test_invalid_json_is_recorded_without_state_change(self) -> None:
        """非法 JSON 应被记录为解析错误且不修改设备状态。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        before = env.devices
        result = env.step("{bad json")

        self.assertFalse(result.info["ok"])
        self.assertEqual(result.info["error_code"], "INVALID_JSON")
        self.assertEqual(before, env.devices)

    def test_query_unknown_field_is_rejected(self) -> None:
        """查询不存在字段时应返回 UNKNOWN_FIELD。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        result = env.step(Action("query_device", {
            "device_id": "bedroom.light",
            "fields": ["temperature"],
        }))

        self.assertFalse(result.info["ok"])
        self.assertEqual(result.info["error_code"], "UNKNOWN_FIELD")

    def test_step_after_termination_requires_reset(self) -> None:
        """episode 终止后继续 step 应强制调用 reset。"""
        env = HomeEpisodeEnv()
        scenario = build_demo_scenario()
        scenario["goal"]["predicates"] = [
            {"device_id": "bedroom.light", "field": "power", "equals": "on"}
        ]
        env.reset(scenario)
        env.step(Action("finish", {"summary": "完成。"}))

        with self.assertRaises(RuntimeError):
            env.step(Action("query_device", {"device_id": "bedroom.light", "fields": []}))

    def test_normalize_action_accepts_json(self) -> None:
        """动作 JSON 字符串应转换成结构化 Action。"""
        action = normalize_action('{"name":"finish","arguments":{"summary":"完成"}}')

        self.assertEqual(action.name, "finish")
        self.assertEqual(action.arguments["summary"], "完成")

    def test_multi_tool_turn_creates_one_transition(self) -> None:
        """一个 assistant turn 的多个工具调用只能产生一条策略转移。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        result = env.step(AssistantTurn(tool_calls=[
            Action("control_device", {
                "device_id": "bedroom.light",
                "command": "set_power",
                "value": "off",
            }),
            Action("control_device", {
                "device_id": "bedroom.air_conditioner",
                "command": "set_temperature",
                "value": 26,
            }),
        ]))

        self.assertEqual(len(env.trajectory()), 1)
        self.assertEqual(result.info["turn_index"], 1)
        self.assertEqual(len(result.info["tool_events"]), 2)
        self.assertEqual(result.info["completion"], 1.0)
        self.assertEqual(env.devices["bedroom.light"]["state"]["power"], "off")
        self.assertEqual(env.devices["bedroom.air_conditioner"]["state"]["temperature"], 26)

    def test_new_max_turns_reports_turn_failure_reason(self) -> None:
        """新场景达到 max_turns 时应报告 MAX_TURNS。"""
        scenario = build_demo_scenario()
        scenario.pop("max_steps", None)
        scenario["max_turns"] = 1
        env = HomeEpisodeEnv()
        env.reset(scenario)
        result = env.step(AssistantTurn(tool_calls=[
            Action("query_device", {"device_id": "bedroom.light", "fields": ["power"]}),
        ]))

        self.assertTrue(result.truncated)
        self.assertEqual(env.final_result().failure_reason, "MAX_TURNS")

    def test_empty_turn_is_recorded_as_one_invalid_transition(self) -> None:
        """空 assistant turn 应消耗一个 turn 并记录结构错误。"""
        env = HomeEpisodeEnv()
        env.reset(build_demo_scenario())
        result = env.step(AssistantTurn())

        self.assertFalse(result.info["ok"])
        self.assertEqual(result.info["error_code"], "EMPTY_ASSISTANT_TURN")
        self.assertEqual(result.info["turn_index"], 1)
        self.assertEqual(len(env.trajectory()), 1)

    def test_tool_call_limit_rejects_whole_turn_without_state_change(self) -> None:
        """超过单回合工具调用上限时应拒绝整个 turn。"""
        scenario = build_demo_scenario()
        scenario["max_tool_calls_per_turn"] = 1
        env = HomeEpisodeEnv()
        env.reset(scenario)
        before = env.devices
        result = env.step(AssistantTurn(tool_calls=[
            Action("control_device", {
                "device_id": "bedroom.light",
                "command": "set_power",
                "value": "off",
            }),
            Action("control_device", {
                "device_id": "bedroom.air_conditioner",
                "command": "set_temperature",
                "value": 26,
            }),
        ]))

        self.assertFalse(result.info["ok"])
        self.assertEqual(result.info["error_code"], "TOO_MANY_TOOL_CALLS")
        self.assertEqual(before, env.devices)
        self.assertEqual(len(result.info["tool_events"]), 2)


if __name__ == "__main__":
    unittest.main()
