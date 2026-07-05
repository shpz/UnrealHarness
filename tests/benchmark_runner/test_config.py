from __future__ import annotations

import importlib
from pathlib import Path
import unittest


config = importlib.import_module("benchmarks.ue5-skillsbench.runner.config")


class BenchmarkConfigTests(unittest.TestCase):
    def test_benchmark_yaml_declares_autotest_skill_and_condition_matrix(self) -> None:
        cfg = config.load_benchmark_yaml(Path("benchmarks/ue5-skillsbench/benchmark.yaml"))

        skills = {skill.name: skill.path for skill in cfg.skills}
        self.assertEqual(skills["ue-build"], "skills/ue-build")
        self.assertEqual(skills["ue-autotest"], "skills/ue-autotest")

        conditions = {condition.id: condition.skills for condition in cfg.conditions}
        self.assertEqual(conditions["no-skills"], [])
        self.assertEqual(conditions["ue-build-only"], ["ue-build"])
        self.assertEqual(conditions["ue-autotest-only"], ["ue-autotest"])
        self.assertEqual(conditions["ue-autotest-with-build"], ["ue-build", "ue-autotest"])
        self.assertNotIn("all-ue-skills", conditions)
        self.assertEqual(cfg.runner.run_root, ".bench/runs")


if __name__ == "__main__":
    unittest.main()
