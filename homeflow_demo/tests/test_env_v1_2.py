"""验证 V1.2 HomeEnv 的执行器边界和状态隔离。"""

from __future__ import annotations

import math
import unittest

from homeflow_demo.env.demo_scenario import build_demo_scenario
from homeflow_demo.env.home_env import HomeEnv
from homeflow_demo.env.models import ToolCall
from homeflow_demo.env.schema import validate_scenario_dict


class HomeEnvV12Test(unittest.TestCase):
    """覆盖 B 模块最关键的环境执行契约。"""

    def setUp(self) -> None:
        """为每个测试创建相同初始场景。"""
        self.scenario = build_demo_scenario()
        self.env = HomeEnv()
        self.env.reset(self.scenario)

    def test_execute_does_not_require_discovery(self) -> None:
        """确认执行器不拦截未观察的真实 id，未知 id 才报错。"""
        observe = self.env.step(ToolCall("observe_home", {}, "call_observe"))
        self.assertTrue(observe.event.ok)
        self.assertNotIn("device_id", str(observe.event.result["data"]))

        room = self.env.step(
            ToolCall("inspect_room", {"room_id": "room_bedroom"}, "call_room")
        )
        self.assertTrue(room.event.ok)

        missing_room = self.env.step(
            ToolCall("inspect_room", {"room_id": "room_missing"}, "call_missing_room")
        )
        self.assertEqual(missing_room.event.error_code, "UNKNOWN_ROOM")

        missing_device = self.env.step(
            ToolCall(
                "inspect_device",
                {"device_id": "device_missing"},
                "call_missing_device",
            )
        )
        self.assertEqual(missing_device.event.error_code, "UNKNOWN_DEVICE")

        action = self.env.step(
            ToolCall(
                "execute_action",
                {
                    "device_id": "device_bedroom_light",
                    "action": "turn_off",
                    "params": {},
                },
                "call_direct_action",
            )
        )
        self.assertTrue(action.event.ok)
        self.assertFalse(self.env.runtime_state["device_bedroom_light"]["state"]["on"])

    def test_sensor_write_is_rejected_without_partial_state(self) -> None:
        """确认传感器写入返回 UNSUPPORTED_ACTION 且不改变状态。"""
        before = self.env.runtime_state
        result = self.env.step(
            ToolCall(
                "execute_action",
                {
                    "device_id": "sensor_bedroom_env",
                    "action": "set_temperature",
                    "params": {"value": 21.0},
                },
                "call_sensor_write",
            )
        )
        self.assertEqual(result.event.error_code, "UNSUPPORTED_ACTION")
        self.assertEqual(result.event.state_diff, {})
        self.assertEqual(self.env.runtime_state, before)

    def test_parameter_failure_is_atomic(self) -> None:
        """确认越界和非有限温度参数不会产生部分状态写入。"""
        before = self.env.runtime_state
        for index, value in enumerate((32.5, math.inf, math.nan)):
            result = self.env.step(
                ToolCall(
                    "execute_action",
                    {
                        "device_id": "device_bedroom_climate",
                        "action": "set_temperature",
                        "params": {"value": value},
                    },
                    f"call_bad_temperature_{index}",
                )
            )
            self.assertEqual(result.event.error_code, "BAD_REQUEST")
            self.assertEqual(result.event.state_diff, {})
            self.assertEqual(self.env.runtime_state, before)

    def test_snapshot_fork_isolates_runtime_state(self) -> None:
        """确认 fork 后子环境写入不影响父环境。"""
        child = self.env.fork()
        child_result = child.step(
            ToolCall(
                "execute_action",
                {
                    "device_id": "device_bedroom_light",
                    "action": "turn_off",
                    "params": {},
                },
                "call_child_light",
            )
        )
        self.assertTrue(child_result.event.ok)
        self.assertFalse(child.runtime_state["device_bedroom_light"]["state"]["on"])
        self.assertTrue(self.env.runtime_state["device_bedroom_light"]["state"]["on"])

    def test_observation_hides_truth_and_elapsed_time(self) -> None:
        """确认策略看不到隐藏目标和硬件相关耗时。"""
        observation, _ = self.env.reset(self.scenario)
        self.assertNotIn("conditions", str(observation))
        self.assertNotIn("keep", str(observation))
        next_observation = self.env.step(
            ToolCall("observe_home", {}, "call_observation")
        ).observation
        self.assertNotIn("elapsed_ms", str(next_observation))

    def test_schema_reports_malformed_values_without_crashing(self) -> None:
        """确认恶意非字符串引用会形成错误列表而不是触发 TypeError。"""
        malformed = build_demo_scenario()
        malformed["home"]["rooms"][0]["device_ids"] = [{"bad": "id"}]
        malformed["home"]["devices"][0]["device_type"] = ["environment_sensor"]
        malformed["home"]["devices"][1]["actions"][0]["action"] = {"bad": "action"}
        errors = validate_scenario_dict(malformed)
        self.assertGreaterEqual(len(errors), 3)

    def test_malformed_tool_call_returns_bad_request(self) -> None:
        """确认直接进入 B 的错误字段类型使用统一错误外壳。"""
        result = self.env.step({"name": 123, "arguments": ["bad"], "call_id": 456})
        self.assertEqual(result.event.error_code, "BAD_REQUEST")
        self.assertFalse(result.event.ok)

if __name__ == "__main__":
    unittest.main()
