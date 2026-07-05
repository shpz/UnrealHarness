from __future__ import annotations

import importlib
from pathlib import Path
import unittest


config = importlib.import_module("benchmarks.ue5-skillsbench.runner.config")
runner_main = importlib.import_module("benchmarks.ue5-skillsbench.runner.__main__")


class TaskCatalogContractTests(unittest.TestCase):
    def test_real_task_catalog_has_valid_role_and_oracle_contracts(self) -> None:
        tasks_root = Path("benchmarks/ue5-skillsbench/tasks")
        tasks = config.discover_tasks(tasks_root)
        self.assertGreaterEqual(len(tasks), 1)

        errors_by_task: dict[str, list[str]] = {}
        for task in tasks:
            errors = runner_main.validate_task_oracle_contract(task, tasks_root / task.id)
            if errors:
                errors_by_task[task.id] = errors

        self.assertEqual(errors_by_task, {})

    def test_phase_b_scoped_report_task_is_registered(self) -> None:
        tasks = {
            task.id: task
            for task in config.discover_tasks(Path("benchmarks/ue5-skillsbench/tasks"))
        }

        task = tasks["tps-autotest-run-scoped-report"]
        self.assertEqual(task.benchmark_role, "formal")
        self.assertEqual(task.oracle.type, "action")
        self.assertEqual(task.oracle.path, "oracle.py")
        self.assertEqual(task.metadata.subcategory, "automation-execution-reporting")
        self.assertIn("ue-autotest", task.primary_skills)

    def test_phase_c_add_input_math_task_is_registered(self) -> None:
        tasks = {
            task.id: task
            for task in config.discover_tasks(Path("benchmarks/ue5-skillsbench/tasks"))
        }

        task = tasks["tps-autotest-add-input-math-tests"]
        self.assertEqual(task.benchmark_role, "formal")
        self.assertEqual(task.oracle.type, "action")
        self.assertEqual(task.oracle.path, "oracle.py")
        self.assertEqual(task.metadata.subcategory, "automation-test-authoring")
        self.assertIn("ue-autotest", task.primary_skills)
        self.assertIn("ue-build", task.secondary_skills)

    def test_phase_c_fix_failing_error_tests_task_is_registered(self) -> None:
        tasks = {
            task.id: task
            for task in config.discover_tasks(Path("benchmarks/ue5-skillsbench/tasks"))
        }

        task = tasks["tps-autotest-fix-failing-error-tests"]
        self.assertEqual(task.benchmark_role, "formal")
        self.assertEqual(task.oracle.type, "action")
        self.assertEqual(task.oracle.path, "oracle.py")
        self.assertEqual(task.metadata.subcategory, "automation-failure-repair")
        self.assertIn("ue-autotest", task.primary_skills)
        self.assertIn("ue-build", task.secondary_skills)

    def test_phase_c_build_fix_module_dependency_task_is_registered(self) -> None:
        tasks = {
            task.id: task
            for task in config.discover_tasks(Path("benchmarks/ue5-skillsbench/tasks"))
        }

        task = tasks["tps-build-fix-module-dependency"]
        self.assertEqual(task.benchmark_role, "formal")
        self.assertEqual(task.oracle.type, "action")
        self.assertEqual(task.oracle.path, "oracle.py")
        self.assertEqual(task.metadata.subcategory, "module-dependency-repair")
        self.assertIn("ue-build", task.primary_skills)

    def test_build_fix_enhanced_input_dependency_task_is_registered(self) -> None:
        tasks = {
            task.id: task
            for task in config.discover_tasks(Path("benchmarks/ue5-skillsbench/tasks"))
        }

        task = tasks["tps-build-fix-enhanced-input-dependency"]
        self.assertEqual(task.benchmark_role, "formal")
        self.assertEqual(task.oracle.type, "action")
        self.assertEqual(task.oracle.path, "oracle.py")
        self.assertEqual(task.metadata.subcategory, "module-dependency-repair")
        self.assertIn("ue-build", task.primary_skills)

    def test_catalog_has_three_formal_build_tasks(self) -> None:
        tasks = config.discover_tasks(Path("benchmarks/ue5-skillsbench/tasks"))

        formal_build_tasks = [
            task for task in tasks
            if task.benchmark_role == "formal" and "ue-build" in task.primary_skills
        ]

        self.assertGreaterEqual(len(formal_build_tasks), 3)


if __name__ == "__main__":
    unittest.main()
