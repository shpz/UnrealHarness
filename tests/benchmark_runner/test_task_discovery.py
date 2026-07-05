from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import textwrap
import unittest


config = importlib.import_module("benchmarks.ue5-skillsbench.runner.config")


class TaskDiscoveryTests(unittest.TestCase):
    def test_task_toml_parses_role_oracle_verifier_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "task-a"
            task_dir.mkdir()
            (task_dir / "task.toml").write_text(
                textwrap.dedent(
                    """
                    id = "task-a"
                    project = "TPSample"
                    timeout_minutes = 12
                    benchmark_role = "formal"
                    primary_skills = ["ue-autotest"]
                    secondary_skills = ["ue-build"]

                    [metadata]
                    subcategory = "automation-test-authoring"
                    tags = ["unreal-engine", "automation"]

                    [oracle]
                    type = "patch"
                    path = "oracle.patch"
                    repeat = 3

                    [verifier]
                    type = "python"
                    path = "verifier.py"
                    timeout_minutes = 9

                    [artifacts]
                    required = ["verifier_result.json", "automation/report.md"]
                    """
                ).strip(),
                encoding="utf-8",
            )

            task = config.load_task_toml(task_dir / "task.toml")

        self.assertEqual(task.benchmark_role, "formal")
        self.assertEqual(task.oracle.type, "patch")
        self.assertEqual(task.oracle.path, "oracle.patch")
        self.assertEqual(task.oracle.repeat, 3)
        self.assertEqual(task.verifier.path, "verifier.py")
        self.assertEqual(task.verifier.timeout_minutes, 9)
        self.assertEqual(task.artifacts.required, ["verifier_result.json", "automation/report.md"])

    def test_discover_tasks_only_returns_directories_with_task_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["task-b", "task-a"]:
                task_dir = root / name
                task_dir.mkdir()
                (task_dir / "task.toml").write_text(
                    f'id = "{name}"\nproject = "TPSample"\nbenchmark_role = "smoke"\n\n[oracle]\ntype = "none"\n',
                    encoding="utf-8",
                )
            (root / "not-a-task").mkdir()

            tasks = config.discover_tasks(root)

        self.assertEqual([task.id for task in tasks], ["task-a", "task-b"])
        self.assertTrue(all(task.benchmark_role == "smoke" for task in tasks))
        self.assertTrue(all(task.oracle.type == "none" for task in tasks))


if __name__ == "__main__":
    unittest.main()
