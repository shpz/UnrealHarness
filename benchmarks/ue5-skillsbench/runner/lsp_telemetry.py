"""Best-effort parsing and aggregation of ue-lsp JSONL traces."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SEMANTIC_OPERATIONS = {"definition", "hover", "references", "implementation", "rename-preview"}


def summarize_lsp_trace(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    malformed_line_count = 0
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                malformed_line_count += 1
                continue
            if isinstance(value, dict):
                records.append(value)
            else:
                malformed_line_count += 1

    operations: dict[str, int] = {}
    elapsed: list[float] = []
    semantic_count = 0
    failed = 0
    incomplete = 0
    for record in records:
        operation = str(record.get("operation") or "unknown")
        operations[operation] = operations.get(operation, 0) + 1
        if operation in SEMANTIC_OPERATIONS:
            semantic_count += 1
        if record.get("status") != "success":
            failed += 1
        if bool(record.get("possibly_incomplete")):
            incomplete += 1
        duration = record.get("elapsed_ms")
        if isinstance(duration, (int, float)):
            elapsed.append(float(duration))

    return {
        "trace_path": str(path),
        "trace_exists": path.exists(),
        "query_count": len(records),
        "semantic_query_count": semantic_count,
        "operations": operations,
        "failed_query_count": failed,
        "possibly_incomplete_count": incomplete,
        "mean_query_ms": round(sum(elapsed) / len(elapsed), 3) if elapsed else None,
        "malformed_line_count": malformed_line_count,
        "usage_evidence": "evidence-based-partial" if semantic_count else "none",
    }
