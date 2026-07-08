from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import textwrap
import unittest


authoritative_rerun = importlib.import_module("benchmarks.ue5-skillsbench.runner.authoritative_rerun")
automation_report = importlib.import_module("benchmarks.ue5-skillsbench.runner.automation_report")
runner_main = importlib.import_module("benchmarks.ue5-skillsbench.runner.__main__")
source_checks = importlib.import_module("benchmarks.ue5-skillsbench.runner.source_checks")


class AuthoritativeRerunTests(unittest.TestCase):
    def test_rerun_disabled_returns_none(self) -> None:
        import os

        old = os.environ.pop(authoritative_rerun.RERUN_ENV, None)
        try:
            result = authoritative_rerun.run_authoritative_automation(
                Path("."), "TPSample.Input.Math"
            )
        finally:
            if old is not None:
                os.environ[authoritative_rerun.RERUN_ENV] = old
        self.assertIsNone(result)

    def test_rerun_flag_parsing(self) -> None:
        import os

        old = os.environ.get(authoritative_rerun.RERUN_ENV)
        try:
            for value, expected in [("1", True), ("true", True), ("0", False), ("", False)]:
                os.environ[authoritative_rerun.RERUN_ENV] = value
                self.assertEqual(authoritative_rerun.rerun_enabled(), expected, value)
        finally:
            if old is None:
                os.environ.pop(authoritative_rerun.RERUN_ENV, None)
            else:
                os.environ[authoritative_rerun.RERUN_ENV] = old


class ParseAutomationReportDirTests(unittest.TestCase):
    def test_parses_only_the_given_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fresh = root / "fresh"
            fresh.mkdir()
            (fresh / "index.json").write_text(
                json.dumps({"tests": [{"fullTestPath": "TPSample.Input.Math.Normalize", "state": "Success"}]}),
                encoding="utf-8",
            )
            stale = root / "stale"
            stale.mkdir()
            (stale / "index.json").write_text(
                json.dumps({"tests": [{"fullTestPath": "TPSample.Fake.Test", "state": "Success"}]}),
                encoding="utf-8",
            )

            result = automation_report.parse_automation_report_dir(fresh)

        self.assertEqual(result.executed_tests, 1)
        self.assertEqual(result.tests[0].name, "TPSample.Input.Math.Normalize")

    def test_missing_directory_yields_no_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = automation_report.parse_automation_report_dir(Path(tmp) / "missing")

        self.assertEqual(result.parser, "none")
        self.assertFalse(result.can_confirm_results)


class ParseEditorLogEvidenceTests(unittest.TestCase):
    def test_ignores_json_reports_and_reads_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            # JSON report exists but must not count as execution evidence.
            report_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "S"
            report_dir.mkdir(parents=True)
            (report_dir / "index.json").write_text(
                json.dumps({"tests": [{"fullTestPath": "TPSample.Fake", "state": "Success"}]}),
                encoding="utf-8",
            )

            evidence = automation_report.parse_editor_log_evidence(project)
            self.assertFalse(evidence.can_confirm_results)

            logs = project / "Saved" / "Logs"
            logs.mkdir(parents=True)
            (logs / "UnrealEditor-Cmd.log").write_text(
                textwrap.dedent(
                    """
                    LogAutomationController: TPSample.Input.Math.Normalize passed (0.01s)
                    LogAutomationController: TPSample.Error.Accumulator.Add passed (0.01s)
                    """
                ).strip(),
                encoding="utf-8",
            )

            evidence = automation_report.parse_editor_log_evidence(project)

        self.assertTrue(evidence.can_confirm_results)
        self.assertEqual(
            sorted(test.name for test in evidence.tests),
            ["TPSample.Error.Accumulator.Add", "TPSample.Input.Math.Normalize"],
        )

    def test_aggregates_across_multiple_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            logs = project / "Saved" / "Logs"
            logs.mkdir(parents=True)
            (logs / "UnrealEditor-Cmd.log").write_text(
                "LogAutomationController: TPSample.Input.Math.Normalize passed (0.01s)",
                encoding="utf-8",
            )
            report_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "S"
            report_dir.mkdir(parents=True)
            (report_dir / "automation.log").write_text(
                "LogAutomationController: TPSample.Error.Accumulator.Add passed (0.01s)",
                encoding="utf-8",
            )

            evidence = automation_report.parse_editor_log_evidence(project)

        self.assertEqual(
            sorted(test.name for test in evidence.tests),
            ["TPSample.Error.Accumulator.Add", "TPSample.Input.Math.Normalize"],
        )


class RequiredArtifactsTests(unittest.TestCase):
    def test_reports_missing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            (artifacts / "verifier_result.json").write_text("{}", encoding="utf-8")
            (artifacts / "automation").mkdir()
            (artifacts / "automation" / "report.md").write_text("# r", encoding="utf-8")

            missing = runner_main.check_required_artifacts(
                ["verifier_result.json", "automation/report.md", "automation/editor.log", "build.log"],
                artifacts,
            )

        self.assertEqual(missing, ["automation/editor.log", "build.log"])

    def test_empty_required_list_is_fine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(runner_main.check_required_artifacts([], Path(tmp)), [])


class SourceChecksTests(unittest.TestCase):
    def test_target_includes_module_add_and_addrange(self) -> None:
        self.assertTrue(source_checks.target_includes_module(
            'ExtraModuleNames.Add("TPSampleTest");', "TPSampleTest"))
        self.assertTrue(source_checks.target_includes_module(
            'ExtraModuleNames.Add( "TPSampleTest" );', "TPSampleTest"))
        self.assertTrue(source_checks.target_includes_module(
            'ExtraModuleNames.AddRange(new string[] { "TPSample", "TPSampleTest" });',
            "TPSampleTest"))
        self.assertTrue(source_checks.target_includes_module(
            'ExtraModuleNames.AddRange(new string[] {\n "TPSample",\n "TPSampleTest"\n});',
            "TPSampleTest"))

    def test_target_includes_module_ignores_comments(self) -> None:
        self.assertFalse(source_checks.target_includes_module(
            '// ExtraModuleNames.Add("TPSampleTest");', "TPSampleTest"))

    def test_target_references_module_ignores_comments(self) -> None:
        self.assertFalse(source_checks.target_references_module(
            '// mention of TPSampleTest in a comment', "TPSampleTest"))
        self.assertTrue(source_checks.target_references_module(
            'ExtraModuleNames.Add("TPSampleTest");', "TPSampleTest"))


if __name__ == "__main__":
    unittest.main()
