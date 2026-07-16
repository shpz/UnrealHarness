"""Verifier for the mixed LSP audit task.

Pass requires all of:
1. lsp_audit.json classifies all five Bench classes correctly;
2. for faulty classes, the reported symbol matches and the line is within
   tolerance of the certified error location;
3. the reported compile_commands.json actually exists on disk;
4. Source/ and Config/ are untouched relative to the setup baseline.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR.parent))

from _lsp_task_support import validate_compile_database

ANSWER_KEY_PATH = TASK_DIR / "answer_key.json"
CERTIFICATION_PATH = TASK_DIR / "certification.json"


def get_source_changes(project_path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-c", "core.excludesfile=", "status", "--porcelain", "--", "Source", "Config"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))

    answer_key = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    line_tolerance = json.loads(CERTIFICATION_PATH.read_text(encoding="utf-8"))["line_tolerance"]
    expected_files = answer_key["files"]

    checks: list[dict[str, object]] = []
    failure_class: str | None = None

    def record(name: str, passed: bool, detail: str, fail_as: str) -> None:
        nonlocal failure_class
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed and failure_class is None:
            failure_class = fail_as

    audit_path = project_path / "lsp_audit.json"
    audit = None
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            record("audit_parse", False, f"lsp_audit.json invalid JSON: {e}", "missing-audit")
    else:
        record("audit_parse", False, "lsp_audit.json missing from project root", "missing-audit")

    if audit is not None:
        reported = audit.get("files", {})

        for stem, spec in expected_files.items():
            entry = reported.get(stem)
            if not isinstance(entry, dict):
                record(f"classification_{stem}", False, f"{stem} missing from audit", "wrong-classification")
                continue

            classified = entry.get("has_code_errors")
            record(
                f"classification_{stem}",
                classified is spec["has_code_errors"],
                f"expected has_code_errors={spec['has_code_errors']}, got {classified!r}",
                "wrong-classification",
            )

            if spec["has_code_errors"]:
                symbol = str(entry.get("error_symbol", ""))
                symbol_ok = bool(symbol) and (
                    symbol.lower() in spec["error_symbol"].lower()
                    or spec["error_symbol"].lower() in symbol.lower()
                )
                line = entry.get("error_line")
                line_ok = isinstance(line, int) and abs(line - spec["error_line"]) <= line_tolerance
                record(
                    f"evidence_{stem}",
                    symbol_ok and line_ok,
                    f"expected symbol~{spec['error_symbol']} line={spec['error_line']}±{line_tolerance}, "
                    f"got symbol={symbol!r} line={line!r}",
                    "wrong-evidence",
                )

        compdb_raw = audit.get("compile_commands_path")
        compdb_ok = False
        compdb_detail = f"compile_commands_path={compdb_raw!r}"
        if isinstance(compdb_raw, str) and compdb_raw:
            candidate = Path(compdb_raw)
            if not candidate.is_absolute():
                candidate = project_path / candidate
            candidate = candidate.resolve()
            expected = (project_path / "compile_commands.json").resolve()
            if candidate == expected:
                try:
                    validate_compile_database(candidate, project_path.resolve())
                    compdb_ok = True
                except RuntimeError as exc:
                    compdb_detail += f" invalid={exc}"
            else:
                compdb_detail += f" expected_workspace_path={expected}"
        record(
            "workspace_compdb_valid",
            compdb_ok,
            compdb_detail,
            "no-compdb",
        )

    try:
        changes = get_source_changes(project_path)
        record(
            "source_untouched",
            len(changes) == 0,
            "no changes under Source/ or Config/" if not changes else "; ".join(changes),
            "source-modified",
        )
    except subprocess.CalledProcessError as e:
        record("source_untouched", False, f"git status failed: {e.stderr}", "verifier-error")

    passed = failure_class is None
    verifier_result = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": checks,
    }

    artifacts_path.mkdir(parents=True, exist_ok=True)
    (artifacts_path / "verifier_result.json").write_text(
        json.dumps(verifier_result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(verifier_result, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
