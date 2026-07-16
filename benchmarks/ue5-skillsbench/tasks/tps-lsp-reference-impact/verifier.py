"""Verifier for exact overload reference impact analysis."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR.parent))
sys.path.insert(0, str(TASK_DIR.parents[1] / "runner"))

from _lsp_task_support import git_changes, normalized_relative_path, resolve_and_validate_reported_compdb
from unreal import invoke_build


def reference_tuple(entry: object) -> tuple[str, int, str] | None:
    if not isinstance(entry, dict):
        return None
    file_path = normalized_relative_path(entry.get("file"))
    line = entry.get("line")
    kind = entry.get("kind")
    if not file_path or not isinstance(line, int) or not isinstance(kind, str):
        return None
    return file_path, line, kind


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", ".")).resolve()
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts")).resolve()
    answer_key = json.loads((TASK_DIR / "answer_key.json").read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = []
    failure_class: str | None = None
    build_result = None

    def record(name: str, passed: bool, detail: str, fail_as: str) -> None:
        nonlocal failure_class
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed and failure_class is None:
            failure_class = fail_as

    report_path = project_path / "reference_impact.json"
    report = None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        record("report_parse", True, str(report_path), "missing-report")
    except (OSError, json.JSONDecodeError) as exc:
        record("report_parse", False, str(exc), "missing-report")

    if isinstance(report, dict):
        try:
            compdb = resolve_and_validate_reported_compdb(project_path, report.get("compile_commands_path"))
            record("compdb_valid", True, str(compdb), "invalid-compdb")
        except RuntimeError as exc:
            record("compdb_valid", False, str(exc), "invalid-compdb")

        record(
            "target_symbol",
            report.get("target") == answer_key["target"],
            f"expected={answer_key['target']!r} actual={report.get('target')!r}",
            "wrong-target",
        )

        expected = {reference_tuple(entry) for entry in answer_key["references"]}
        raw_actual = report.get("references")
        actual_entries = raw_actual if isinstance(raw_actual, list) else []
        parsed_actual = [reference_tuple(entry) for entry in actual_entries]
        actual = {entry for entry in parsed_actual if entry is not None}
        structurally_valid = all(entry is not None for entry in parsed_actual) and len(actual) == len(actual_entries)
        record(
            "reference_set",
            structurally_valid and actual == expected,
            f"expected={sorted(expected)} actual={sorted(actual)} raw_count={len(actual_entries)}",
            "wrong-references",
        )

    try:
        changes = git_changes(project_path, "Source", "Config", "ReferenceHoneypots")
        record(
            "workspace_sources_untouched",
            not changes,
            "no Source/Config/honeypot changes" if not changes else "; ".join(changes),
            "source-modified",
        )
    except Exception as exc:
        record("workspace_sources_untouched", False, str(exc), "verifier-error")

    fixture_honeypot = TASK_DIR / "fixtures" / "ReferenceHoneypots"
    workspace_honeypot = project_path / "ReferenceHoneypots" / "ReferenceImpact"
    honeypot_ok = all(
        (workspace_honeypot / fixture.name).exists()
        and (workspace_honeypot / fixture.name).read_bytes() == fixture.read_bytes()
        for fixture in fixture_honeypot.iterdir()
        if fixture.is_file()
    )
    record("honeypots_untouched", honeypot_ok, str(workspace_honeypot), "honeypot-modified")

    try:
        build_log = artifacts_path / "build.log"
        build_result = invoke_build(
            project_path=project_path,
            target="TPSampleEditor",
            platform="Win64",
            configuration="Development",
            uproject_name="TPSample.uproject",
            clean=True,
            build_log_path=build_log,
        )
        record("ubt_build", build_result["exit_code"] == 0, build_result["command_line"], "build")
    except Exception as exc:
        record("ubt_build", False, str(exc), "verifier-error")

    passed = failure_class is None
    result = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": checks,
        "build": {
            "exit_code": build_result["exit_code"],
            "duration_seconds": build_result["duration_seconds"],
            "log": str(artifacts_path / "build.log"),
            "engine_root": build_result["engine_root"],
        } if build_result else None,
    }
    artifacts_path.mkdir(parents=True, exist_ok=True)
    (artifacts_path / "verifier_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
