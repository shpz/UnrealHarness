from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
import unittest


verifier_result = importlib.import_module("benchmarks.ue5-skillsbench.runner.verifier_result")


class VerifierResultSchemaTests(unittest.TestCase):
    def test_make_result_and_validate_accept_minimal_valid_result(self) -> None:
        result = verifier_result.make_result(
            passed=False,
            failure_class="automation-discovery",
            checks=[{"name": "automation_scope", "passed": False}],
            automation={"executed_tests": 0},
        )

        self.assertEqual(verifier_result.validate_result_schema(result), [])
        self.assertFalse(result["passed"])
        self.assertEqual(result["failure_class"], "automation-discovery")
        self.assertEqual(result["automation"]["executed_tests"], 0)

    def test_validate_result_schema_reports_missing_or_wrong_required_fields(self) -> None:
        errors = verifier_result.validate_result_schema(
            {"passed": "no", "failure_class": 123, "checks": "bad"}
        )

        self.assertTrue(any("passed" in error for error in errors))
        self.assertTrue(any("failure_class" in error for error in errors))
        self.assertTrue(any("checks" in error for error in errors))

    def test_write_result_rejects_invalid_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "verifier_result.json"
            with self.assertRaises(ValueError):
                verifier_result.write_result(path, {"passed": True})

            valid = verifier_result.make_result(True, None, [])
            verifier_result.write_result(path, valid)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), valid)


if __name__ == "__main__":
    unittest.main()
