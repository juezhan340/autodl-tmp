"""验证 V1.2 HomeEnv 的发现链、只读边界和状态隔离。"""

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

    def test_room_and_device_must_be_discovered(self) -> None:
        """确认真实 ID 也不能绕过 observe_home 和 inspect_room。"""
        room_result = self.env.step(
            ToolCall("inspect_room", {"room_id": "room_bedroom"}, "call_room_early")
        )
        self.assertEqual(room_result.event.error_code, "UNKNOWN_ROOM")

        guessed = self.env.step(
            ToolCall(
                "inspect_device",
                {"device_id": "device_bedroom_light"},
                "call_device_early",
            )
        )
        self.assertEqual(guessed.event.error_code, "UNKNOWN_DEVICE")

        self.assertTrue(self.env.step(ToolCall("observe_home", {}, "call_observe")).event.ok)
        room = self.env.step(
            ToolCall("inspect_room", {"room_id": "room_bedroom"}, "call_room")
        )
        returned_ids = {
            item["device_id"] for item in room.event.result["data"]["room"]["devices"]
        }
        self.assertIn("device_bedroom_light", returned_ids)
        premature_action = self.env.step(
            ToolCall(
                "execute_action",
                {
                    "device_id": "device_bedroom_light",
                    "action": "turn_off",
                    "params": {},
                },
                "call_action_before_device_inspection",
            )
        )
        self.assertEqual(premature_action.event.error_code, "BAD_REQUEST")
        device = self.env.step(
            ToolCall(
                "inspect_device",
                {"device_id": "device_bedroom_light"},
                "call_device",
            )
        )
        self.assertTrue(device.event.ok)

    def test_sensor_write_is_rejected_without_partial_state(self) -> None:
        """确认传感器写入返回 UNSUPPORTED_ACTION 且不改变状态。"""
        self._discover_room("room_bedroom")
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
        self._discover_room("room_bedroom")
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

    def test_snapshot_fork_preserves_discovery_and_isolation(self) -> None:
        """确认 fork 继承发现状态，但子环境写入不影响父环境。"""
        self._discover_room("room_bedroom")
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

    def _discover_room(self, room_id: str) -> None:
        """按正式发现链让一个房间及其设备变为可执行。"""
        self.env.step(ToolCall("observe_home", {}, f"observe_{room_id}"))
        self.env.step(ToolCall("inspect_room", {"room_id": room_id}, f"inspect_{room_id}"))
        room_devices = [
            item
            for item in self.scenario["home"]["devices"]
            if item["room_id"] == room_id
        ]
        for device in room_devices:
            self.env.step(
                ToolCall(
                    "inspect_device",
                    {"device_id": device["device_id"]},
                    f"inspect_{device['device_id']}",
                )
            )


if __name__ == "__main__":
    unittest.main()
