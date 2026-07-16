"""Verifier for symbol-aware rename with generated and same-name decoys."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK_DIR.parent))
sys.path.insert(0, str(TASK_DIR.parents[1] / "runner"))

from _lsp_task_support import git_changes, resolve_and_validate_reported_compdb
from unreal import invoke_build


TARGET_FILES = {
    "Source/TPSample/BenchSemanticRename/BenchAbilityRouter.h",
    "Source/TPSample/BenchSemanticRename/BenchAbilityRouter.cpp",
    "Source/TPSample/BenchSemanticRename/BenchAbilityConsumer.cpp",
    "Source/TPSample/BenchSemanticRename/BenchAbilityController.cpp",
}


def changed_paths(lines: list[str]) -> set[str]:
    result: set[str] = set()
    for line in lines:
        raw = line[3:].strip() if len(line) >= 4 else line.strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        result.add(raw.replace("\\", "/"))
    return result


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", ".")).resolve()
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts")).resolve()
    checks: list[dict[str, object]] = []
    failure_class: str | None = None
    build_result = None

    def record(name: str, passed: bool, detail: str, fail_as: str) -> None:
        nonlocal failure_class
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed and failure_class is None:
            failure_class = fail_as

    report_path = project_path / "semantic_rename_report.json"
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
            "report_symbols",
            report.get("old_symbol") == "UBenchAbilityRouter::TriggerAbility"
            and report.get("new_symbol") == "UBenchAbilityRouter::ActivateAbility",
            json.dumps(report, ensure_ascii=False),
            "wrong-report",
        )

    expected_counts = {
        "BenchAbilityRouter.h": 1,
        "BenchAbilityRouter.cpp": 1,
        "BenchAbilityConsumer.cpp": 1,
        "BenchAbilityController.cpp": 1,
    }
    target_dir = project_path / "Source" / "TPSample" / "BenchSemanticRename"
    for filename, expected_count in expected_counts.items():
        path = target_dir / filename
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        passed = text.count("ActivateAbility") == expected_count and "TriggerAbility" not in text
        record(
            f"renamed_{filename}",
            passed,
            f"ActivateAbility={text.count('ActivateAbility')} TriggerAbility={text.count('TriggerAbility')}",
            "incomplete-rename",
        )

    telemetry_h = (target_dir / "BenchTelemetryProbe.h").read_text(encoding="utf-8")
    telemetry_cpp = (target_dir / "BenchTelemetryProbe.cpp").read_text(encoding="utf-8")
    decoys_ok = (
        telemetry_h.count("TriggerAbility") == 2
        and "ActivateAbility" not in telemetry_h
        and telemetry_cpp.count("TriggerAbility") == 3
        and "ActivateAbility" not in telemetry_cpp
    )
    record("same_name_decoys_untouched", decoys_ok, "telemetry/free-function decoys", "decoy-modified")

    fixture_honeypot = TASK_DIR / "fixtures" / "ReferenceHoneypots"
    workspace_honeypot = project_path / "ReferenceHoneypots" / "SemanticRename"
    honeypot_ok = all(
        (workspace_honeypot / fixture.name).exists()
        and (workspace_honeypot / fixture.name).read_bytes() == fixture.read_bytes()
        for fixture in fixture_honeypot.iterdir()
        if fixture.is_file()
    )
    record("generated_honeypots_untouched", honeypot_ok, str(workspace_honeypot), "generated-modified")

    try:
        source_change_lines = git_changes(project_path, "Source", "Config", "ReferenceHoneypots")
        paths = changed_paths(source_change_lines)
        record(
            "change_scope",
            paths == TARGET_FILES,
            f"expected={sorted(TARGET_FILES)} actual={sorted(paths)}",
            "out-of-scope-change",
        )
    except Exception as exc:
        record("change_scope", False, str(exc), "verifier-error")

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
        record(
            "ubt_build",
            build_result["exit_code"] == 0,
            build_result["command_line"],
            "build",
        )
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
