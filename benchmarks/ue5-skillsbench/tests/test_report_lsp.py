from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARK_ROOT))

from runner.report import make_report  # noqa: E402


def trial(condition: str, passed: bool, duration: float, semantic: int) -> dict:
    return {
        "task_id": "tps-lsp-example",
        "condition": condition,
        "overall_passed": passed,
        "metrics": {"wall_clock_seconds": duration + 1, "build_duration_seconds": 1},
        "agent": {"duration_seconds": duration, "failure_class": None},
        "verifier": {"failure_class": None},
        "lsp": {
            "semantic_query_count": semantic,
            "failed_query_count": 1 if semantic else 0,
            "possibly_incomplete_count": 1 if semantic else 0,
        },
    }


class ReportLspTests(unittest.TestCase):
    def test_lsp_condition_comparison_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "runs"
            output = Path(temp) / "reports"
            for index, value in enumerate(
                [trial("no-skills", False, 10, 0), trial("ue-lsp-only", True, 14, 3)], start=1
            ):
                run = root / f"sample-{index}"
                run.mkdir(parents=True)
                (run / "result.json").write_text(json.dumps(value), encoding="utf-8")
            generated = make_report(root, "sample", output)
            report = json.loads(Path(generated["json_path"]).read_text(encoding="utf-8"))
            lsp_row = next(row for row in report["summary"] if row["condition"] == "ue-lsp-only")
            self.assertEqual(lsp_row["delta_pp"], 100.0)
            self.assertEqual(lsp_row["mean_semantic_query_count"], 3.0)
            self.assertEqual(lsp_row["lsp_trial_count"], 1)
            self.assertEqual(lsp_row["agent_duration_delta_seconds"], 4.0)
            self.assertEqual(lsp_row["skill_usage_confidence"], "evidence-based-partial")


if __name__ == "__main__":
    unittest.main()
