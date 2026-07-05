from __future__ import annotations

import importlib
import unittest


config = importlib.import_module("benchmarks.ue5-skillsbench.runner.config")
runner_main = importlib.import_module("benchmarks.ue5-skillsbench.runner.__main__")


def task(task_id: str, role: str, subcategory: str, tags: list[str]) -> object:
    return config.TaskConfig(
        id=task_id,
        project="TPSample",
        benchmark_role=role,
        metadata=config.TaskMetadata(subcategory=subcategory, tags=tags),
    )


class RunMatrixSelectionTests(unittest.TestCase):
    def test_default_matrix_selects_only_formal_tasks(self) -> None:
        tasks = [
            task("formal-build", "formal", "engine-resolution", ["ue5"]),
            task("smoke-build", "smoke", "basic-build", ["smoke"]),
        ]

        selected = runner_main.select_matrix_tasks(tasks, task_ids=[], task_filters=[])

        self.assertEqual([task.id for task in selected], ["formal-build"])

    def test_explicit_task_id_can_select_smoke_task(self) -> None:
        tasks = [
            task("formal-build", "formal", "engine-resolution", ["ue5"]),
            task("smoke-build", "smoke", "basic-build", ["smoke"]),
        ]

        selected = runner_main.select_matrix_tasks(tasks, task_ids=["smoke-build"], task_filters=[])

        self.assertEqual([task.id for task in selected], ["smoke-build"])

    def test_task_filters_match_subcategory_or_tags_with_or_semantics(self) -> None:
        tasks = [
            task("build", "formal", "engine-resolution", ["ue5"]),
            task("autotest", "formal", "automation-reporting", ["automation"]),
            task("repair", "formal", "build-repair", ["module-dependency"]),
        ]

        selected = runner_main.select_matrix_tasks(
            tasks,
            task_ids=[],
            task_filters=["automation-reporting", "module-dependency"],
        )

        self.assertEqual([task.id for task in selected], ["autotest", "repair"])

    def test_condition_filter_preserves_requested_order(self) -> None:
        conditions = [
            config.ConditionConfig("no-skills", []),
            config.ConditionConfig("ue-build-only", ["ue-build"]),
            config.ConditionConfig("ue-autotest-with-build", ["ue-build", "ue-autotest"]),
        ]

        selected = runner_main.select_matrix_conditions(
            conditions,
            condition_ids=["ue-autotest-with-build", "no-skills"],
        )

        self.assertEqual([condition.id for condition in selected], ["ue-autotest-with-build", "no-skills"])

    def test_matrix_trial_run_id_stays_short_for_ue_intermediate_paths(self) -> None:
        run_id = runner_main.matrix_trial_run_id(
            "phase-d-codex-smoke-2x2x2",
            sequence=7,
        )

        self.assertEqual(run_id, "phase-d-codex-smoke-2x2x2-r007")
        self.assertLess(len(run_id), 40)
        self.assertNotIn("tps-build-fix-module-dependency", run_id)
        self.assertNotIn("ue-autotest-with-build", run_id)

    def test_validation_trial_run_id_stays_short_with_long_audit_prefix(self) -> None:
        run_id = runner_main.validation_trial_run_id(
            "final-audit-tps-build-fix-module-dependency",
            phase="oracle",
            trial=1,
        )

        self.assertLessEqual(len(run_id), 40)
        self.assertTrue(run_id.endswith("-vo001"))
        self.assertNotIn("validate-oracle", run_id)


if __name__ == "__main__":
    unittest.main()
