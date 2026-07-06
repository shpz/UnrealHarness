"""Shared Automation report parsing helpers."""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class AutomationTestResult:
    name: str
    passed: bool
    error: str | None = None


@dataclasses.dataclass
class AutomationReportResult:
    parser: str
    source_path: str | None
    tests: list[AutomationTestResult]

    @property
    def executed_tests(self) -> int:
        return len(self.tests)

    @property
    def passed_tests(self) -> int:
        return sum(1 for test in self.tests if test.passed)

    @property
    def failed_tests(self) -> int:
        return sum(1 for test in self.tests if not test.passed)

    @property
    def skipped_tests(self) -> int:
        return 0

    @property
    def can_confirm_results(self) -> bool:
        return self.parser != "none" and self.executed_tests > 0

    def to_automation_dict(self, requested_scopes: list[str] | None = None) -> dict[str, Any]:
        return {
            "requested_scopes": requested_scopes or [],
            "executed_tests": self.executed_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "report_parser": self.parser,
        }


def parse_automation_report(project_path: Path) -> AutomationReportResult:
    for index_path in _find_native_index_files(project_path):
        parsed = _parse_native_index(index_path)
        if parsed.tests:
            return parsed

    autotest_results = project_path / "Saved" / "Automation" / "autotest_results.json"
    if autotest_results.exists():
        parsed = _parse_autotest_results(autotest_results)
        if parsed.tests:
            return parsed

    for log_path in _find_editor_logs(project_path):
        parsed = _parse_editor_log(log_path)
        if parsed.tests:
            return parsed

    return AutomationReportResult(parser="none", source_path=None, tests=[])


def _find_native_index_files(project_path: Path) -> list[Path]:
    reports_root = project_path / "Saved" / "Automation" / "Reports"
    if not reports_root.exists():
        return []
    return sorted(
        (path for path in reports_root.rglob("index.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _parse_native_index(index_path: Path) -> AutomationReportResult:
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return AutomationReportResult(parser="native-index-json", source_path=str(index_path), tests=[])

    tests: list[AutomationTestResult] = []
    for test in raw.get("tests") or []:
        state = str(test.get("state") or test.get("status") or "")
        passed = bool(re.match(r"^(Success|Passed|Pass)$", state, re.IGNORECASE))
        failed = bool(re.match(r"^(Fail|Failed|Error)$", state, re.IGNORECASE))
        if not passed and not failed:
            continue
        name = str(
            test.get("fullTestPath")
            or test.get("testDisplayName")
            or test.get("name")
            or ""
        )
        if not name:
            continue
        errors: list[str] = []
        for entry in test.get("entries") or []:
            event = entry.get("event") or {}
            if str(event.get("type") or "").lower() in {"error", "warning"} and event.get("message"):
                errors.append(str(event["message"]))
        tests.append(AutomationTestResult(name=name, passed=passed, error="\n".join(errors) or None))

    return AutomationReportResult(parser="native-index-json", source_path=str(index_path), tests=tests)


_SYNTHETIC_SUFFIXES = ("(NO TESTS PARSED)", "(TIMEOUT)")


def _is_synthetic_test_name(name: str) -> bool:
    return any(name.strip().endswith(suffix) for suffix in _SYNTHETIC_SUFFIXES)


def _parse_autotest_results(results_path: Path) -> AutomationReportResult:
    try:
        raw = json.loads(results_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return AutomationReportResult(parser="autotest-results-json", source_path=str(results_path), tests=[])

    tests: list[AutomationTestResult] = []
    for module in raw.get("modules") or []:
        results = module.get("results") or {}
        for test in results.get("tests") or []:
            name = str(test.get("name") or "").strip()
            if not name or _is_synthetic_test_name(name):
                continue
            tests.append(
                AutomationTestResult(
                    name=name,
                    passed=bool(test.get("passed")),
                    error=str(test.get("error")) if test.get("error") else None,
                )
            )

    return AutomationReportResult(parser="autotest-results-json", source_path=str(results_path), tests=tests)


def _find_editor_logs(project_path: Path) -> list[Path]:
    logs_root = project_path / "Saved" / "Logs"
    if not logs_root.exists():
        return []
    patterns = ["UnrealEditor-Cmd.log", "UnrealEditor*.log", f"{project_path.name}*.log"]
    candidates: dict[Path, None] = {}
    for pattern in patterns:
        for path in logs_root.glob(pattern):
            if path.is_file():
                candidates[path] = None
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def _parse_editor_log(log_path: Path) -> AutomationReportResult:
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return AutomationReportResult(parser="editor-log-summary", source_path=str(log_path), tests=[])

    tests: list[AutomationTestResult] = []
    passed_re = re.compile(r"LogAutomationController:\s+(.+?)\s+passed\s*\(", re.IGNORECASE)
    failed_re = re.compile(r"LogAutomationController:\s+(.+?)\s+failed", re.IGNORECASE)
    for line in lines:
        passed = passed_re.search(line)
        if passed:
            tests.append(AutomationTestResult(name=passed.group(1).strip(), passed=True))
            continue
        failed = failed_re.search(line)
        if failed:
            tests.append(AutomationTestResult(name=failed.group(1).strip(), passed=False))

    return AutomationReportResult(parser="editor-log-summary", source_path=str(log_path), tests=tests)
