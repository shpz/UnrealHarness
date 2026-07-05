"""Verifier for tps-autotest-run-scoped-report."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))

from automation_report import parse_automation_report  # noqa: E402
from verifier_result import make_result, write_result  # noqa: E402


REQUIRED_PREFIXES = ["TPSample.Input.", "TPSample.Error."]
FORBIDDEN_PREFIXES = ["TPSample.Performance."]


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))
    report = parse_automation_report(project_path)
    markdown = _find_markdown_report(project_path)

    checks = []
    checks.append({
        "name": "automation_results_present",
        "passed": report.can_confirm_results,
        "details": report.source_path or "no Automation report found",
    })

    names = [test.name for test in report.tests]
    for prefix in REQUIRED_PREFIXES:
        checks.append({
            "name": f"scope_{prefix}",
            "passed": sum(1 for name in names if name.startswith(prefix)) >= 3,
            "details": prefix,
        })

    forbidden = [name for name in names if any(name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)]
    checks.append({
        "name": "performance_scope_excluded",
        "passed": not forbidden,
        "details": ", ".join(forbidden),
    })

    checks.append({
        "name": "all_selected_tests_passed",
        "passed": report.can_confirm_results and report.failed_tests == 0,
        "details": f"failed={report.failed_tests}",
    })
    checks.append({
        "name": "markdown_report",
        "passed": markdown is not None and _markdown_has_required_content(markdown),
        "details": str(markdown) if markdown else "missing",
    })
    checks.append({
        "name": "no_source_changes_after_setup",
        "passed": not _source_changes_after_setup(project_path),
    })

    failure_class = None
    ordered_checks = sorted(
        checks,
        key=lambda check: 0 if check["name"] == "performance_scope_excluded" else 1,
    )
    for check in ordered_checks:
        if check["passed"]:
            continue
        if check["name"] == "performance_scope_excluded":
            failure_class = "scope"
        elif check["name"] in {"automation_results_present", "all_selected_tests_passed"}:
            failure_class = "automation-discovery" if report.executed_tests == 0 else "test"
        elif check["name"] == "markdown_report":
            failure_class = "reporting"
        elif check["name"] == "no_source_changes_after_setup":
            failure_class = "cheating"
        else:
            failure_class = "automation-discovery"
        break

    result = make_result(
        passed=failure_class is None,
        failure_class=failure_class,
        checks=checks,
        automation=report.to_automation_dict(requested_scopes=["TPSample.Input.*", "TPSample.Error.*"]),
        artifacts={
            "automation_report": report.source_path,
            "markdown_report": str(markdown) if markdown else None,
        },
    )
    write_result(artifacts_path / "verifier_result.json", result)
    return 0 if result["passed"] else 1


def _find_markdown_report(project_path: Path) -> Path | None:
    root = project_path / "Saved" / "Automation" / "Reports"
    if not root.exists():
        return None
    candidates = [path for path in root.rglob("*.md") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _markdown_has_required_content(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    return "scope" in text and "passed" in text and ("failure" in text or "no failures" in text)


def _source_changes_after_setup(project_path: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "Source", "Config", "TPSample.uproject"],
        cwd=project_path,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


if __name__ == "__main__":
    sys.exit(main())
