"""验证 V1.2 数据生成、构建清单和全量验证入口。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from homeflow_demo.data.build_v1_2_dataset import build_v1_2_dataset
from homeflow_demo.data.scenario_generator import TASK_KINDS, ScenarioGenerator
from homeflow_demo.data.validate_v1_2_dataset import validate_v1_2_dataset


class DataV12Test(unittest.TestCase):
    """覆盖 D 模块本地数据的任务覆盖、隔离和确定性。"""

    def test_generator_covers_all_task_kinds(self) -> None:
        """确认连续八条场景恰好覆盖八类任务。"""
        scenarios = ScenarioGenerator(20260924).generate(8, "train")
        kinds = {item["metadata"]["task_kind"] for item in scenarios}
        self.assertEqual(kinds, set(TASK_KINDS))
        self.assertEqual(len({item["scenario_id"] for item in scenarios}), 8)

    def test_threshold_tasks_cover_control_and_no_op_branches(self) -> None:
        """确认阈值任务同时包含执行控制和正确不动作分支。"""
        scenarios = ScenarioGenerator(20260924).generate(48, "train")
        branches: dict[str, set[str]] = {
            "temperature_threshold": set(),
            "humidity_threshold": set(),
        }
        for scenario in scenarios:
            task_kind = scenario["metadata"]["task_kind"]
            if task_kind in branches:
                branches[task_kind].add(scenario["metadata"]["threshold_branch"])
        self.assertEqual(branches["temperature_threshold"], {"control", "no_op"})
        self.assertEqual(branches["humidity_threshold"], {"control", "no_op"})

    def test_full_build_is_deterministic_and_valid(self) -> None:
        """确认两次完整构建得到相同指纹且都通过全量重放。"""
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            first = build_v1_2_dataset(root / "first", seed=20260924)
            second = build_v1_2_dataset(root / "second", seed=20260924)
            self.assertEqual(first["dataset_fingerprint"], second["dataset_fingerprint"])
            report = validate_v1_2_dataset(root / "first")
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["scenario_id_count"], 140)
            self.assertEqual(report["splits"]["train"]["replay_count"], 80)
            self.assertEqual(report["splits"]["val"]["replay_count"], 20)
            self.assertEqual(report["splits"]["eval"]["replay_count"], 40)


if __name__ == "__main__":
    unittest.main()
