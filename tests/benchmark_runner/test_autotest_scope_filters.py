from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

AUTOTEST_SCRIPT = Path("skills/ue-autotest/scripts/autotest.py")


def _load_autotest():
    spec = importlib.util.spec_from_file_location("ue_autotest_autotest", AUTOTEST_SCRIPT.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load autotest.py spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ue_autotest_autotest"] = module
    spec.loader.exec_module(module)
    return module


_autotest = _load_autotest()
build_run_filters = _autotest.build_run_filters


class ScopeFilterTests(unittest.TestCase):
    def test_single_scope(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["TPSample.Input.*"])
        self.assertEqual(filters, ["TPSample.Input"])

    def test_all_scopes(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["all"])
        self.assertEqual(filters, ["TPSample"])

    def test_multiple_scopes(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["TPSample.Input.*", "TPSample.Error.*"])
        self.assertEqual(filters, ["TPSample.Error", "TPSample.Input"])

    def test_plus_joined_scope(self) -> None:
        modules = ["TPSampleTest"]
        prefixes = {"TPSampleTest": "TPSample"}
        filters = build_run_filters(modules, prefixes, ["TPSample.Input.*+TPSample.Error.*"])
        self.assertEqual(filters, ["TPSample.Error", "TPSample.Input"])


if __name__ == "__main__":
    unittest.main()
