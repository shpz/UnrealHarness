from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import textwrap
import unittest


autotest = importlib.import_module("skills.ue-autotest.scripts.autotest")


class AutotestOverallExitCodeTests(unittest.TestCase):
    def test_overall_exit_code_passes(self) -> None:
        results = {
            "modules": [{"timedOut": False, "results": {"tests": []}}],
            "overall": {"failed": 0},
        }
        self.assertEqual(autotest._overall_exit_code(results), 0)

    def test_overall_exit_code_fails_on_failed_tests(self) -> None:
        results = {
            "modules": [{"timedOut": False, "results": {"tests": []}}],
            "overall": {"failed": 2},
        }
        self.assertEqual(autotest._overall_exit_code(results), 1)

    def test_overall_exit_code_fails_on_timeout(self) -> None:
        results = {
            "modules": [{"timedOut": True, "results": {"tests": []}}],
            "overall": {"failed": 0},
        }
        self.assertEqual(autotest._overall_exit_code(results), 1)


class AutotestPlaceholderTests(unittest.TestCase):
    def test_build_module_results_does_not_inject_placeholder(self) -> None:
        run_result = {
            "exitCode": 0,
            "timedOut": False,
            "logFile": Path("C:/tmp/log.log"),
            "reportDir": Path("C:/tmp/report"),
        }
        module_result = autotest._build_module_results(
            buckets={"TPSampleTest": []},
            mod="TPSampleTest",
            module_prefixes={"TPSampleTest": "TPSample.Error"},
            filters=["TPSample.Error"],
            run_result=run_result,
        )

        self.assertEqual(module_result["name"], "TPSampleTest")
        self.assertEqual(module_result["results"]["tests"], [])
        self.assertFalse(module_result["timedOut"])

    def test_build_module_results_timeout_has_empty_tests(self) -> None:
        run_result = {
            "exitCode": 124,
            "timedOut": True,
            "logFile": Path("C:/tmp/log.log"),
            "reportDir": Path("C:/tmp/report"),
        }
        module_result = autotest._build_module_results(
            buckets={"TPSampleTest": []},
            mod="TPSampleTest",
            module_prefixes={"TPSampleTest": "TPSample.Error"},
            filters=["TPSample.Error"],
            run_result=run_result,
        )

        self.assertEqual(module_result["name"], "TPSampleTest")
        self.assertTrue(module_result["timedOut"])
        self.assertEqual(module_result["results"]["tests"], [])
        self.assertEqual(module_result["results"]["summary"]["total"], 0)


class AutotestLogFallbackTests(unittest.TestCase):
    def _parse_log(self, content: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "UnrealEditor-Cmd.log"
            log_file.write_text(content, encoding="utf-8")
            return autotest.parse_test_results(
                log_file, autotest._DEFAULT_CONFIG["logPatterns"]
            )

    def test_parses_english_passed_failed_lines(self) -> None:
        results = self._parse_log(
            textwrap.dedent(
                """
                LogAutomationController: TPSample.Input.Math.Normalize passed (0.01s)
                LogAutomationController: TPSample.Input.Math.DeadZone failed
                LogAutomationController: Error: Expected zero vector
                """
            ).strip()
        )

        self.assertEqual(results["summary"]["total"], 2)
        self.assertEqual(results["summary"]["passed"], 1)
        self.assertEqual(results["summary"]["failed"], 1)
        failed = next(t for t in results["tests"] if not t["passed"])
        self.assertEqual(failed["error"], "Expected zero vector")

    def test_parses_localized_test_completed_lines(self) -> None:
        results = self._parse_log(
            textwrap.dedent(
                """
                [2026.07.05-06.05.11:700][538]LogAutomationController: Display: Test Completed. Result={成功} Name={Add} Path={TPSample.Error.Accumulator.Add}
                [2026.07.05-06.05.26:133][544]LogAutomationController: Error: Test Completed. Result={失败} Name={Dedupe} Path={TPSample.Error.Accumulator.Dedupe}
                [2026.07.05-06.05.26:157][547]LogAutomationController: Display: Test Completed. Result={Success} Name={Flush} Path={TPSample.Error.Accumulator.Flush}
                """
            ).strip()
        )

        self.assertEqual(results["summary"]["total"], 3)
        self.assertEqual(results["summary"]["passed"], 2)
        self.assertEqual(results["summary"]["failed"], 1)
        by_name = {t["name"]: t["passed"] for t in results["tests"]}
        self.assertTrue(by_name["TPSample.Error.Accumulator.Add"])
        self.assertFalse(by_name["TPSample.Error.Accumulator.Dedupe"])
        self.assertTrue(by_name["TPSample.Error.Accumulator.Flush"])
