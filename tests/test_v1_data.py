"""验证 V1 schema、生成器、规划器和 Gym 风格接口。"""

import unittest

from homeflow_demo.data.planner import plan_scenario, run_oracle_episode
from homeflow_demo.data.scenario_generator import ScenarioGenerator
from homeflow_demo.data.trajectory_format import read_jsonl, write_jsonl
from homeflow_demo.data.validate_v1_dataset import validate_v1_dataset
from homeflow_demo.env import Action, HomeEpisodeEnv
from homeflow_demo.env.demo_scenario import build_demo_scenario
from homeflow_demo.env.gym_adapter import GymHomeEnvAdapter
from homeflow_demo.env.schema import SchemaValidationError, ensure_valid_scenario, validate_scenario_dict
from homeflow_demo.env.tool_schema import validate_action


class V1DataTest(unittest.TestCase):
    """覆盖 V1 进入批量数据生成前的关键契约。"""

    def test_scenario_generator_is_reproducible(self) -> None:
        """相同 seed 和参数应生成完全相同的场景。"""
        first = ScenarioGenerator(seed=7).generate(8, "train")
        second = ScenarioGenerator(seed=7).generate(8, "train")
        self.assertEqual(first, second)

    def test_scenario_ids_are_unique_across_splits(self) -> None:
        """同一个生成器连续生成 split 时，场景 ID 不能重复。"""
        generator = ScenarioGenerator(seed=7)
        records = generator.generate(8, "train") + generator.generate(4, "val")
        ids = [record["scenario_id"] for record in records]
        self.assertEqual(len(ids), len(set(ids)))

    def test_schema_rejects_duplicate_device_ids(self) -> None:
        """重复设备 ID 必须在状态机之前被拒绝。"""
        scenario = build_demo_scenario()
        scenario["devices"].append(dict(scenario["devices"][0]))
        with self.assertRaises(SchemaValidationError):
            ensure_valid_scenario(scenario)

    def test_planner_solves_demo_scenario(self) -> None:
        """规则规划器应为可行双目标场景生成成功动作序列。"""
        scenario = build_demo_scenario()
        plan = plan_scenario(scenario)
        record = run_oracle_episode(scenario)
        self.assertTrue(plan.feasible)
        self.assertTrue(record["success"])
        self.assertEqual(record["final_result"]["completion"], 1.0)

    def test_planner_rejects_out_of_range_goal(self) -> None:
        """超出设备值域的温度目标应被标记为不可行。"""
        scenario = build_demo_scenario()
        scenario["goal"]["predicates"] = [
            {"device_id": "bedroom.air_conditioner", "field": "temperature", "equals": 31}
        ]
        plan = plan_scenario(scenario)
        self.assertFalse(plan.feasible)
        self.assertIn("unrepresentable", plan.reason or "")

    def test_gym_adapter_contract(self) -> None:
        """Gym 风格适配器应返回 reset 二元组和 step 五元组。"""
        adapter = GymHomeEnvAdapter()
        observation, info = adapter.reset(options={"scenario": build_demo_scenario()})
        result = adapter.step({
            "name": "query_device",
            "arguments": {"device_id": "bedroom.light", "fields": ["power"]},
        })
        self.assertIn("user_request", observation)
        self.assertIn("tools", info)
        self.assertEqual(len(result), 5)
        self.assertIsInstance(result[1], float)

    def test_all_generated_scenarios_pass_schema(self) -> None:
        """V1 三个 split 的全部生成场景都应通过 schema。"""
        generator = ScenarioGenerator(seed=11)
        for split, count in (("train", 80), ("val", 20), ("eval", 40)):
            for scenario in generator.generate(count, split):
                self.assertEqual(validate_scenario_dict(scenario), [])

    def test_all_feasible_generated_scenarios_have_successful_oracle(self) -> None:
        """每个可行场景都必须存在成功的规则轨迹。"""
        generator = ScenarioGenerator(seed=11)
        for split, count in (("train", 80), ("val", 20), ("eval", 40)):
            for scenario in generator.generate(count, split):
                record = run_oracle_episode(scenario)
                if scenario["metadata"]["feasible"]:
                    self.assertTrue(record["success"], scenario["scenario_id"])
                    self.assertEqual(record["final_result"]["completion"], 1.0)

    def test_infeasible_generated_scenarios_are_not_marked_successful(self) -> None:
        """不可行任务必须保留失败结果，不能伪造成功轨迹。"""
        scenarios = ScenarioGenerator(seed=11).generate(18, "eval")
        for scenario in scenarios:
            record = run_oracle_episode(scenario)
            if not scenario["metadata"]["feasible"]:
                self.assertFalse(record["success"])
                self.assertFalse(record["feasible"])

    def test_query_then_control_plan_contains_query(self) -> None:
        """requires_query 场景的规则计划必须先查询再控制。"""
        scenarios = ScenarioGenerator(seed=11).generate(3, "train")
        query_scenario = next(item for item in scenarios if item["metadata"]["requires_query"])
        plan = plan_scenario(query_scenario)

        self.assertTrue(plan.feasible)
        self.assertEqual(plan.actions[0].name, "query_device")
        self.assertEqual(plan.actions[-1].name, "finish")

    def test_each_device_type_has_valid_control_command(self) -> None:
        """四类设备的边界控制命令都应通过工具校验。"""
        devices = {
            "l": {"id": "l", "type": "light", "state": {"power": "on", "brightness": 1, "color_temp": 1500}},
            "t": {"id": "t", "type": "thermostat", "state": {"power": "on", "temperature": 16, "mode": "cool"}},
            "s": {"id": "s", "type": "switch", "state": {"power": "off"}},
            "k": {"id": "k", "type": "lock", "state": {"locked": False}},
        }
        actions = [
            ("l", "set_power", "off"),
            ("l", "set_brightness", 100),
            ("l", "set_color_temp", 9000),
            ("t", "set_power", "off"),
            ("t", "set_temperature", 30),
            ("t", "set_mode", "auto"),
            ("s", "set_power", "on"),
            ("k", "set_locked", True),
        ]
        for device_id, command, value in actions:
            with self.subTest(command=command):
                result = validate_action(
                    Action("control_device", {"device_id": device_id, "command": command, "value": value}),
                    devices,
                )
                self.assertTrue(result.valid)

    def test_control_value_boundaries_are_rejected(self) -> None:
        """越过 V1 工具边界的数值必须被拒绝。"""
        devices = {
            "light": {"id": "light", "type": "light", "state": {"power": "on", "brightness": 50, "color_temp": 4000}},
            "ac": {"id": "ac", "type": "thermostat", "state": {"power": "on", "temperature": 24, "mode": "cool"}},
        }
        invalid_actions = [
            ("light", "set_brightness", -1),
            ("light", "set_brightness", 101),
            ("light", "set_color_temp", 1499),
            ("ac", "set_temperature", 15),
            ("ac", "set_temperature", 31),
        ]
        for device_id, command, value in invalid_actions:
            with self.subTest(command=command, value=value):
                result = validate_action(
                    Action("control_device", {"device_id": device_id, "command": command, "value": value}),
                    devices,
                )
                self.assertFalse(result.valid)
                self.assertEqual(result.error_code, "VALUE_OUT_OF_RANGE")

    def test_schema_rejects_unsupported_initial_state_field(self) -> None:
        """设备初始状态不能携带该设备类型不支持的字段。"""
        scenario = build_demo_scenario()
        scenario["devices"][0]["state"]["temperature"] = 24

        errors = validate_scenario_dict(scenario)

        self.assertTrue(any("unsupported fields" in error for error in errors))

    def test_schema_rejects_invalid_initial_state_value(self) -> None:
        """设备初始状态值必须落在 V1 值域内。"""
        scenario = build_demo_scenario()
        scenario["devices"][1]["state"]["temperature"] = 31

        errors = validate_scenario_dict(scenario)

        self.assertTrue(any("invalid value" in error for error in errors))

    def test_dataset_validator_accepts_checked_in_v1_data(self) -> None:
        """已生成的 V1 数据应通过文件、划分和轨迹重放验收。"""
        report = validate_v1_dataset("homeflow_demo/data_processed/v1")

        self.assertTrue(report["valid"])
        self.assertEqual(report["scenario_id_count"], 140)
        self.assertEqual(report["splits"]["train"]["scenario_count"], 80)
        self.assertEqual(report["splits"]["val"]["scenario_count"], 20)
        self.assertEqual(report["splits"]["eval"]["scenario_count"], 40)

    def test_trajectory_jsonl_round_trip(self) -> None:
        """轨迹 JSONL 写入后应能无损读回。"""
        import tempfile
        from pathlib import Path

        record = run_oracle_episode(build_demo_scenario())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trajectory.jsonl"
            self.assertEqual(write_jsonl(path, [record]), 1)
            self.assertEqual(read_jsonl(path), [record])

    def test_oracle_record_uses_turn_format(self) -> None:
        """新 Oracle 记录必须包含 turn-level 主字段。"""
        record = run_oracle_episode(build_demo_scenario())

        self.assertEqual(record["format_version"], "v1.1-turn")
        self.assertEqual(len(record["turns"]), record["final_result"]["turns"])
        self.assertTrue(record["turns"][0]["tool_events"])
        self.assertIn("assistant_output", record["turns"][0])


if __name__ == "__main__":
    unittest.main()
