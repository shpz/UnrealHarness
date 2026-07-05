"""Verifier for tps-autotest-fix-failing-error-tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys


RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))

from automation_report import parse_automation_report  # noqa: E402
from verifier_result import make_result, write_result  # noqa: E402


REQUIRED_PREFIX = "TPSample.Error.Accumulator."
REQUIRED_TESTS = {
    "TPSample.Error.Accumulator.RecordsErrors",
    "TPSample.Error.Accumulator.FlushClearsQueue",
    "TPSample.Error.Accumulator.DedupesBroadcast",
}
REQUIRED_DEPENDENCIES = {"Core", "CoreUObject", "Engine", "UnrealEd", "TPSample"}


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))
    report = parse_automation_report(project_path)

    checks = []
    checks.extend(_registration_checks(project_path))
    checks.extend(_anti_cheat_checks(project_path))

    target_tests = [test for test in report.tests if test.name.startswith(REQUIRED_PREFIX)]
    target_names = {test.name for test in target_tests}
    checks.append({
        "name": "automation_results_present",
        "passed": report.can_confirm_results,
        "details": report.source_path or "no Automation report found",
    })
    checks.append({
        "name": "error_scope_has_required_tests",
        "passed": REQUIRED_TESTS.issubset(target_names),
        "details": ", ".join(sorted(target_names)),
    })
    checks.append({
        "name": "all_error_tests_passed",
        "passed": bool(target_tests) and all(test.passed for test in target_tests),
        "details": f"failed={sum(1 for test in target_tests if not test.passed)}",
    })

    failure_class = _first_failure_class(checks, report.executed_tests)
    result = make_result(
        passed=failure_class is None,
        failure_class=failure_class,
        checks=checks,
        automation=report.to_automation_dict(requested_scopes=["TPSample.Error.Accumulator.*"]),
        artifacts={
            "automation_report": report.source_path,
            "build_log": str(artifacts_path / "build.log") if (artifacts_path / "build.log").exists() else None,
        },
    )
    write_result(artifacts_path / "verifier_result.json", result)
    return 0 if result["passed"] else 1


def _registration_checks(project_path: Path) -> list[dict]:
    build_cs = project_path / "Source" / "TPSampleTest" / "TPSampleTest.Build.cs"
    editor_target = project_path / "Source" / "TPSampleEditor.Target.cs"
    uproject = project_path / "TPSample.uproject"

    descriptor = _read_uproject(uproject)
    modules = descriptor.get("Modules") if isinstance(descriptor, dict) else []
    test_module = next((module for module in modules or [] if module.get("Name") == "TPSampleTest"), None)
    build_text = _read_text(build_cs)
    dependencies = set(re.findall(r'"([^"]+)"', build_text))

    return [
        {"name": "test_module_build_cs_exists", "passed": build_cs.exists(), "details": str(build_cs)},
        {"name": "uproject_registers_editor_test_module", "passed": bool(test_module and test_module.get("Type") == "Editor")},
        {"name": "editor_target_includes_test_module", "passed": 'ExtraModuleNames.Add("TPSampleTest")' in _read_text(editor_target)},
        {"name": "test_module_dependencies", "passed": REQUIRED_DEPENDENCIES.issubset(dependencies), "details": ", ".join(sorted(dependencies))},
    ]


def _anti_cheat_checks(project_path: Path) -> list[dict]:
    test_path = project_path / "Source" / "TPSampleTest" / "Private" / "TPSampleErrorAccumulatorTest.cpp"
    helper_source = project_path / "Source" / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp"
    text = _read_text(test_path)
    helper_text = _read_text(helper_source)
    declared_tests = set(re.findall(r'"(TPSample\.Error\.Accumulator\.[^"]+)"', text))
    strong_broadcast_assertion = bool(
        re.search(r"BroadcastCount\s*,\s*1", text)
        or re.search(r"BroadcastCount\s*==\s*1", text)
    )
    weakened_patterns = [">= 0", "return true; }", "return true;\n}"]

    return [
        {"name": "error_test_source_exists", "passed": test_path.exists(), "details": str(test_path)},
        {"name": "error_test_source_keeps_required_tests", "passed": REQUIRED_TESTS.issubset(declared_tests), "details": ", ".join(sorted(declared_tests))},
        {"name": "broadcast_assertion_not_weakened", "passed": strong_broadcast_assertion and ">= 0" not in text},
        {"name": "production_helper_touched", "passed": bool(re.search(r"\b\w+\.Code\s*==\s*Code\b", helper_text)) or "FindByPredicate" in helper_text},
        {"name": "test_source_no_early_success_shortcut", "passed": not any(pattern in text for pattern in weakened_patterns[:1])},
    ]


def _first_failure_class(checks: list[dict], executed_tests: int) -> str | None:
    registration_names = {
        "test_module_build_cs_exists",
        "uproject_registers_editor_test_module",
        "editor_target_includes_test_module",
        "test_module_dependencies",
    }
    cheating_names = {
        "error_test_source_exists",
        "error_test_source_keeps_required_tests",
        "broadcast_assertion_not_weakened",
        "production_helper_touched",
        "test_source_no_early_success_shortcut",
    }
    for check in checks:
        if check["passed"]:
            continue
        if check["name"] in registration_names:
            return "registration"
        if check["name"] in cheating_names:
            return "cheating"
        if check["name"] == "all_error_tests_passed" and executed_tests > 0:
            return "test"
        return "automation-discovery"
    return None


def _read_uproject(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
