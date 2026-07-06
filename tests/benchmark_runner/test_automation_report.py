from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import textwrap
import unittest


automation_report = importlib.import_module("benchmarks.ue5-skillsbench.runner.automation_report")


class AutomationReportTests(unittest.TestCase):
    def test_parse_native_index_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            report_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Input"
            report_dir.mkdir(parents=True)
            (report_dir / "index.json").write_text(
                json.dumps(
                    {
                        "tests": [
                            {"fullTestPath": "TPSample.Input.Math.Normalize", "state": "Success"},
                            {
                                "fullTestPath": "TPSample.Error.Accumulator.Dedupe",
                                "state": "Fail",
                                "entries": [{"event": {"type": "Error", "message": "Expected 1"}}],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = automation_report.parse_automation_report(project)

        self.assertEqual(result.parser, "native-index-json")
        self.assertEqual(result.executed_tests, 2)
        self.assertEqual(result.passed_tests, 1)
        self.assertEqual(result.failed_tests, 1)
        self.assertEqual([test.name for test in result.tests], [
            "TPSample.Input.Math.Normalize",
            "TPSample.Error.Accumulator.Dedupe",
        ])
        self.assertTrue(result.source_path.endswith("index.json"))

    def test_parse_autotest_results_json_when_native_report_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            automation_dir = project / "Saved" / "Automation"
            automation_dir.mkdir(parents=True)
            (automation_dir / "autotest_results.json").write_text(
                json.dumps(
                    {
                        "modules": [
                            {
                                "name": "TPSampleTest",
                                "results": {
                                    "tests": [
                                        {"name": "TPSample.Input.Math.Normalize", "passed": True},
                                        {"name": "TPSample.Input.Math.DeadZone", "passed": True},
                                    ]
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = automation_report.parse_automation_report(project)

        self.assertEqual(result.parser, "autotest-results-json")
        self.assertEqual(result.executed_tests, 2)
        self.assertEqual(result.passed_tests, 2)
        self.assertEqual(result.failed_tests, 0)

    def test_parse_editor_log_summary_as_last_resort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            logs = project / "Saved" / "Logs"
            logs.mkdir(parents=True)
            (logs / "UnrealEditor-Cmd.log").write_text(
                textwrap.dedent(
                    """
                    LogAutomationController: TPSample.Input.Math.Normalize passed (0.01s)
                    LogAutomationController: TPSample.Input.Math.DeadZone passed (0.01s)
                    LogAutomationController: TPSample.Performance.Memory.Budget failed
                    """
                ).strip(),
                encoding="utf-8",
            )

            result = automation_report.parse_automation_report(project)

        self.assertEqual(result.parser, "editor-log-summary")
        self.assertEqual(result.executed_tests, 3)
        self.assertEqual(result.passed_tests, 2)
        self.assertEqual(result.failed_tests, 1)

    def test_missing_report_does_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = automation_report.parse_automation_report(Path(tmp))

        self.assertEqual(result.parser, "none")
        self.assertEqual(result.executed_tests, 0)
        self.assertFalse(result.can_confirm_results)

    def test_autotest_results_ignore_synthetic_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            automation_dir = project / "Saved" / "Automation"
            automation_dir.mkdir(parents=True)
            (automation_dir / "autotest_results.json").write_text(
                json.dumps(
                    {
                        "modules": [
                            {
                                "name": "TPSampleTest",
                                "results": {
                                    "tests": [
                                        {"name": "TPSampleTest (NO TESTS PARSED)", "passed": False},
                                        {"name": "TPSampleTest (TIMEOUT)", "passed": False},
                                        {"name": "TPSample.Input.Math.Normalize", "passed": True},
                                    ]
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = automation_report.parse_automation_report(project)

        self.assertEqual(result.parser, "autotest-results-json")
        self.assertEqual(result.executed_tests, 1)
        self.assertEqual(result.passed_tests, 1)
        self.assertEqual([test.name for test in result.tests], ["TPSample.Input.Math.Normalize"])


if __name__ == "__main__":
    unittest.main()
