from __future__ import annotations

import importlib
from pathlib import Path
import unittest


autotest = importlib.import_module("skills.ue-autotest.scripts.autotest")


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
