"""Verifier for concrete interface implementation mapping."""
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

    report_path = project_path / "implementation_map.json"
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
            "interface_name",
            report.get("interface") == answer_key["interface"],
            f"expected={answer_key['interface']!r} actual={report.get('interface')!r}",
            "wrong-interface",
        )

        expected = answer_key["concrete_classes"]
        actual = report.get("concrete_classes")
        actual = actual if isinstance(actual, dict) else {}
        record(
            "concrete_class_set",
            set(actual) == set(expected),
            f"expected={sorted(expected)} actual={sorted(actual)}",
            "wrong-class-set",
        )
        for class_name, expected_entry in expected.items():
            entry = actual.get(class_name)
            if not isinstance(entry, dict):
                record(f"mapping_{class_name}", False, "entry missing", "wrong-mapping")
                continue
            provider_ok = entry.get("provider_class") == expected_entry["provider_class"]
            header_ok = normalized_relative_path(entry.get("class_header")) == expected_entry["class_header"]
            impl_ok = normalized_relative_path(entry.get("implementation_file")) == expected_entry["implementation_file"]
            record(
                f"mapping_{class_name}",
                provider_ok and header_ok and impl_ok,
                json.dumps(entry, ensure_ascii=False),
                "wrong-mapping",
            )

    try:
        changes = git_changes(project_path, "Source", "Config")
        record(
            "source_untouched",
            not changes,
            "no Source/Config changes" if not changes else "; ".join(changes),
            "source-modified",
        )
    except Exception as exc:
        record("source_untouched", False, str(exc), "verifier-error")

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
