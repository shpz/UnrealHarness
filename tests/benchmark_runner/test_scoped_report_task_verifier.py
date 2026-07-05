from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFIER = Path("benchmarks/ue5-skillsbench/tasks/tps-autotest-run-scoped-report/verifier.py")


class ScopedReportTaskVerifierTests(unittest.TestCase):
    def test_verifier_accepts_input_and_error_report_without_performance_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            project.mkdir()
            _init_git(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                    "TPSample.Error.Accumulator.Add",
                    "TPSample.Error.Accumulator.Flush",
                    "TPSample.Error.Accumulator.Dedupe",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])
            self.assertEqual(verifier_result["automation"]["executed_tests"], 6)

    def test_verifier_accepts_skill_generated_markdown_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            project.mkdir()
            _init_git(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                    "TPSample.Error.Accumulator.Add",
                    "TPSample.Error.Accumulator.Flush",
                    "TPSample.Error.Accumulator.Dedupe",
                ],
            )
            (project / "Saved" / "Automation" / "Reports" / "2026-07-05-120000-autotest-report.md").write_text(
                "# UE5 Automation Test Report\n\n## Summary\n\n| Metric | Value |\n| Total Tests | 6 |\n| Passed | 6 |\n| Failed | 0 |\n\n> All tests passed.",
                encoding="utf-8",
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_verifier_rejects_performance_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            project.mkdir()
            _init_git(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Error.Accumulator.Add",
                    "TPSample.Performance.Memory.Budget",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertNotEqual(result.returncode, 0)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertEqual(verifier_result["failure_class"], "scope")


def _init_git(project: Path) -> None:
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "baseline"], cwd=project, check=True, capture_output=True)


def _write_report(project: Path, names: list[str]) -> None:
    report_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Scoped"
    report_dir.mkdir(parents=True)
    (report_dir / "index.json").write_text(
        json.dumps({"tests": [{"fullTestPath": name, "state": "Success"} for name in names]}),
        encoding="utf-8",
    )
    (project / "Saved" / "Automation" / "autotest_results.json").write_text("{}", encoding="utf-8")
    (project / "Saved" / "Automation" / "Reports" / "scoped-report.md").write_text(
        "# Report\n\nScope: TPSample.Input.* + TPSample.Error.*\n\nPassed: 6\n\nNo failures.",
        encoding="utf-8",
    )


def _run_verifier(project: Path, artifacts: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PROJECT_PATH": str(project),
        "ARTIFACTS_PATH": str(artifacts),
        "BENCHMARK_ROOT": str(Path("benchmarks/ue5-skillsbench").resolve()),
    }
    return subprocess.run(
        [sys.executable, str(VERIFIER.resolve())],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )


if __name__ == "__main__":
    unittest.main()
