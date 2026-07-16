from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARK_ROOT))

from runner.adapter import agent_environment  # noqa: E402
from runner.lsp_telemetry import summarize_lsp_trace  # noqa: E402


class LspTelemetryTests(unittest.TestCase):
    def test_agent_environment_is_child_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_trace = os.environ.get("UE_LSP_TRACE_PATH")
            env = agent_environment(root / "project", root / "artifacts")
            self.assertNotEqual(env.get("UE_LSP_TRACE_PATH"), old_trace)
            self.assertEqual(os.environ.get("UE_LSP_TRACE_PATH"), old_trace)

    def test_trace_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trace.jsonl"
            records = [
                {"operation": "status", "status": "success", "elapsed_ms": 10},
                {"operation": "references", "status": "success", "elapsed_ms": 20, "possibly_incomplete": True},
                {"operation": "definition", "status": "failure", "elapsed_ms": 30},
            ]
            path.write_text("\n".join(json.dumps(item) for item in records) + "\nnot-json\n", encoding="utf-8")
            result = summarize_lsp_trace(path)
            self.assertEqual(result["query_count"], 3)
            self.assertEqual(result["semantic_query_count"], 2)
            self.assertEqual(result["failed_query_count"], 1)
            self.assertEqual(result["possibly_incomplete_count"], 1)
            self.assertEqual(result["mean_query_ms"], 20.0)
            self.assertEqual(result["malformed_line_count"], 1)

    def test_missing_trace_is_zero_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = summarize_lsp_trace(Path(temp) / "missing.jsonl")
            self.assertEqual(result["query_count"], 0)
            self.assertIsNone(result["mean_query_ms"])


if __name__ == "__main__":
    unittest.main()
