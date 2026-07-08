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

        requires = {skill.name: skill.requires for skill in cfg.skills}
        self.assertEqual(requires["ue-autotest"], ["ue-build"])

        conditions = {condition.id: condition.skills for condition in cfg.conditions}
        self.assertEqual(conditions["no-skills"], [])
        self.assertEqual(conditions["ue-build-only"], ["ue-build"])
        self.assertEqual(conditions["ue-autotest-with-build"], ["ue-build", "ue-autotest"])
        # ue-autotest hard-depends on ue-build; a standalone autotest condition
        # benchmarks a broken harness, not the skill.
        self.assertNotIn("ue-autotest-only", conditions)
        self.assertNotIn("all-ue-skills", conditions)
        self.assertEqual(cfg.runner.run_root, ".bench/runs")

    def test_validate_skill_dependencies_rejects_condition_missing_dependency(self) -> None:
        cfg = config.BenchmarkConfig(
            project=config.ProjectConfig("", "", "", "", "", ""),
            skills=[
                config.SkillConfig("ue-build", "skills/ue-build"),
                config.SkillConfig("ue-autotest", "skills/ue-autotest", requires=["ue-build"]),
            ],
            conditions=[
                config.ConditionConfig("ue-autotest-only", ["ue-autotest"]),
                config.ConditionConfig("ue-autotest-with-build", ["ue-build", "ue-autotest"]),
            ],
            runner=config.RunnerConfig(".bench/runs", 1, [], []),
        )

        errors = config.validate_skill_dependencies(cfg)

        self.assertEqual(len(errors), 1)
        self.assertIn("ue-autotest-only", errors[0])
        self.assertIn("ue-build", errors[0])


if __name__ == "__main__":
    unittest.main()
