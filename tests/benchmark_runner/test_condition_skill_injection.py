from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import unittest


config = importlib.import_module("benchmarks.ue5-skillsbench.runner.config")
runner_main = importlib.import_module("benchmarks.ue5-skillsbench.runner.__main__")


class ConditionSkillInjectionTests(unittest.TestCase):
    def test_no_skills_condition_records_empty_injection_and_missing_root(self) -> None:
        cfg = config.BenchmarkConfig(
            project=config.ProjectConfig("", "", "", "", "", ""),
            skills=[config.SkillConfig("ue-build", "skills/ue-build")],
            conditions=[],
            runner=config.RunnerConfig(".bench/runs", 1, [], []),
        )
        condition = config.ConditionConfig("no-skills", [])

        record = runner_main.describe_skill_injection(
            repo_root=Path("D:/repo"),
            workspace_root=Path("D:/repo/.bench/runs/run/workspace"),
            config=cfg,
            condition=condition,
            skills_root=None,
        )

        self.assertEqual(record["skills_injected"], [])
        self.assertFalse(record["skills_root_exists"])

    def test_skill_condition_records_source_and_destination_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            skills_root = workspace / "skills"
            (skills_root / "ue-build").mkdir(parents=True)
            cfg = config.BenchmarkConfig(
                project=config.ProjectConfig("", "", "", "", "", ""),
                skills=[config.SkillConfig("ue-build", "skills/ue-build")],
                conditions=[],
                runner=config.RunnerConfig(".bench/runs", 1, [], []),
            )
            condition = config.ConditionConfig("ue-build-only", ["ue-build"])

            record = runner_main.describe_skill_injection(
                repo_root=root,
                workspace_root=workspace,
                config=cfg,
                condition=condition,
                skills_root=skills_root,
            )

        self.assertTrue(record["skills_root_exists"])
        self.assertEqual(record["skills_injected"][0]["name"], "ue-build")
        self.assertTrue(record["skills_injected"][0]["source"].endswith("skills\\ue-build") or record["skills_injected"][0]["source"].endswith("skills/ue-build"))
        self.assertTrue(record["skills_injected"][0]["destination"].endswith("skills\\ue-build") or record["skills_injected"][0]["destination"].endswith("skills/ue-build"))


if __name__ == "__main__":
    unittest.main()
