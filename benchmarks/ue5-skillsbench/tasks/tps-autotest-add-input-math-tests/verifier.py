"""Verifier for tps-autotest-add-input-math-tests."""
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


REQUIRED_PREFIX = "TPSample.Input.Math."
REQUIRED_DEPENDENCIES = {"Core", "CoreUObject", "Engine", "UnrealEd", "TPSample"}


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))
    report = parse_automation_report(project_path)

    checks = []
    checks.extend(_registration_checks(project_path))
    checks.extend(_source_checks(project_path))

    math_tests = [test for test in report.tests if test.name.startswith(REQUIRED_PREFIX)]
    checks.append({
        "name": "automation_results_present",
        "passed": report.can_confirm_results,
        "details": report.source_path or "no Automation report found",
    })
    checks.append({
        "name": "math_scope_has_three_tests",
        "passed": len(math_tests) >= 3,
        "details": ", ".join(test.name for test in math_tests),
    })
    checks.append({
        "name": "all_math_tests_passed",
        "passed": bool(math_tests) and all(test.passed for test in math_tests),
        "details": f"failed={sum(1 for test in math_tests if not test.passed)}",
    })

    failure_class = _first_failure_class(checks, report.executed_tests)
    result = make_result(
        passed=failure_class is None,
        failure_class=failure_class,
        checks=checks,
        automation=report.to_automation_dict(requested_scopes=["TPSample.Input.Math.*"]),
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
    game_target = project_path / "Source" / "TPSample.Target.cs"
    uproject = project_path / "TPSample.uproject"

    descriptor = _read_uproject(uproject)
    modules = descriptor.get("Modules") if isinstance(descriptor, dict) else []
    test_module = next((module for module in modules or [] if module.get("Name") == "TPSampleTest"), None)
    build_text = _read_text(build_cs)
    editor_target_text = _read_text(editor_target)
    game_target_text = _read_text(game_target)
    dependencies = set(re.findall(r'"([^"]+)"', build_text))

    return [
        {
            "name": "test_module_build_cs_exists",
            "passed": build_cs.exists(),
            "details": str(build_cs),
        },
        {
            "name": "uproject_registers_editor_test_module",
            "passed": bool(test_module and test_module.get("Type") == "Editor"),
        },
        {
            "name": "editor_target_includes_test_module",
            "passed": 'ExtraModuleNames.Add("TPSampleTest")' in editor_target_text,
        },
        {
            "name": "game_target_excludes_test_module",
            "passed": "TPSampleTest" not in game_target_text,
        },
        {
            "name": "test_module_dependencies",
            "passed": REQUIRED_DEPENDENCIES.issubset(dependencies),
            "details": ", ".join(sorted(dependencies)),
        },
    ]


def _source_checks(project_path: Path) -> list[dict]:
    test_files = list((project_path / "Source" / "TPSampleTest" / "Private").glob("*.cpp"))
    combined = "\n".join(_read_text(path) for path in test_files)
    names = re.findall(r'"(TPSample\.Input\.Math\.[^"]+)"', combined)
    uses_supported_flags = (
        "EAutomationTestFlags::EngineFilter" in combined
        and "EAutomationTestFlags::ProductFilter" not in combined
        and (
            "EAutomationTestFlags::ApplicationContextMask" in combined
            or "EAutomationTestFlags::EditorContext" in combined
        )
    )
    return [
        {
            "name": "math_test_source_exists",
            "passed": any("InputMath" in path.name and path.name.endswith("Test.cpp") for path in test_files),
        },
        {
            "name": "math_test_source_defines_three_tests",
            "passed": len(set(names)) >= 3,
            "details": ", ".join(sorted(set(names))),
        },
        {
            "name": "math_tests_use_supported_flags",
            "passed": uses_supported_flags,
        },
    ]


def _first_failure_class(checks: list[dict], executed_tests: int) -> str | None:
    registration_names = {
        "test_module_build_cs_exists",
        "uproject_registers_editor_test_module",
        "editor_target_includes_test_module",
        "game_target_excludes_test_module",
        "test_module_dependencies",
        "math_test_source_exists",
        "math_test_source_defines_three_tests",
        "math_tests_use_supported_flags",
    }
    for check in checks:
        if check["passed"]:
            continue
        if check["name"] in registration_names:
            return "registration"
        if check["name"] == "all_math_tests_passed" and executed_tests > 0:
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
