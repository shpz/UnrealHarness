from __future__ import annotations

import json
import importlib
from pathlib import Path
import tempfile
import unittest


report = importlib.import_module("benchmarks.ue5-skillsbench.runner.report")


class ReportGenerationTests(unittest.TestCase):
    def test_report_writes_summary_results_and_failure_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs"
            output = root / "reports"

            _write_result(
                run_root,
                "phase-d-sample-t1-no-skills-1",
                task_id="tps-build-fix-module-dependency",
                condition="no-skills",
                trial=1,
                passed=False,
                failure_class="build",
                wall_clock=10.0,
                build_duration=None,
                files_changed=0,
                lines_added=0,
                lines_deleted=0,
                skills=[],
                failed_check="ubt_build",
            )
            _write_result(
                run_root,
                "phase-d-sample-t1-ue-build-1",
                task_id="tps-build-fix-module-dependency",
                condition="ue-build-only",
                trial=1,
                passed=True,
                failure_class=None,
                wall_clock=8.0,
                build_duration=4.0,
                files_changed=1,
                lines_added=1,
                lines_deleted=0,
                skills=["ue-build"],
            )
            _write_result(
                run_root,
                "phase-d-sample-t1-ue-build-2",
                task_id="tps-build-fix-module-dependency",
                condition="ue-build-only",
                trial=2,
                passed=True,
                failure_class=None,
                wall_clock=6.0,
                build_duration=3.0,
                files_changed=1,
                lines_added=1,
                lines_deleted=0,
                skills=["ue-build"],
            )

            result = report.make_report(run_root, "phase-d-sample", output)

            self.assertTrue(Path(result["json_path"]).exists())
            self.assertTrue(Path(result["md_path"]).exists())
            self.assertTrue(Path(result["failures_path"]).exists())

            payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
            rows = {(row["task_id"], row["condition"]): row for row in payload["summary"]}
            build_row = rows[("tps-build-fix-module-dependency", "ue-build-only")]
            self.assertEqual(build_row["median_wall_clock_seconds"], 7.0)
            self.assertEqual(build_row["mean_files_changed"], 1.0)
            self.assertEqual(build_row["mean_lines_changed"], 1.0)
            self.assertEqual(build_row["delta_pp"], 100.0)
            self.assertEqual(build_row["normalized_gain"], 1.0)

            skill_impact = payload["skill_impact"]["ue-build"]
            self.assertEqual(skill_impact["task_count"], 1)
            self.assertEqual(skill_impact["mean_delta_pp"], 100.0)

            failures_md = Path(result["failures_path"]).read_text(encoding="utf-8")
            self.assertIn("tps-build-fix-module-dependency", failures_md)
            self.assertIn("ubt_build", failures_md)
            self.assertIn("build", failures_md)

            summary_md = Path(result["md_path"]).read_text(encoding="utf-8")
            self.assertIn("Skill Impact", summary_md)
            self.assertIn("Median Wall", summary_md)


def _write_result(
    run_root: Path,
    run_id: str,
    *,
    task_id: str,
    condition: str,
    trial: int,
    passed: bool,
    failure_class: str | None,
    wall_clock: float,
    build_duration: float | None,
    files_changed: int,
    lines_added: int,
    lines_deleted: int,
    skills: list[str],
    failed_check: str | None = None,
) -> None:
    run_dir = run_root / run_id
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    verifier_result = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": [{"name": failed_check or "ok", "passed": passed, "details": "detail"}],
    }
    verifier_path = artifacts / "verifier_result.json"
    verifier_path.write_text(json.dumps(verifier_result), encoding="utf-8")
    (artifacts / "git.diff").write_text("diff", encoding="utf-8")
    result = {
        "run_id": run_id,
        "task_id": task_id,
        "condition": condition,
        "trial": trial,
        "skills_injected": [{"name": skill} for skill in skills],
        "agent": {"name": "oracle", "duration_seconds": 1.0, "failure_class": None},
        "verifier": {"passed": passed, "failure_class": failure_class},
        "overall_passed": passed,
        "failure_class": failure_class,
        "metrics": {
            "wall_clock_seconds": wall_clock,
            "build_duration_seconds": build_duration,
            "files_changed": files_changed,
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
        },
        "artifacts": {
            "verifier_result": str(verifier_path),
            "diff": str(artifacts / "git.diff"),
        },
    }
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
