"""Oracle action: run the required Automation scopes and write reports."""
from __future__ import annotations

import json
from pathlib import Path
import sys


RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))

from automation_report import parse_automation_report  # noqa: E402
from unreal import invoke_automation, invoke_build  # noqa: E402


SCOPES = ["TPSample.Input", "TPSample.Error"]


def main() -> int:
    project_path = Path.cwd()
    automation_dir = project_path / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Scoped"

    build_result = invoke_build(
        project_path=project_path,
        target="TPSampleEditor",
        platform="Win64",
        configuration="Development",
        uproject_name="TPSample.uproject",
        clean=False,
        build_log_path=project_path / "Saved" / "Automation" / "build.log",
    )
    if build_result["exit_code"] != 0:
        return build_result["exit_code"]

    automation_result = invoke_automation(
        project_path=project_path,
        test_filter="+".join(SCOPES),
        automation_dir=automation_dir,
        uproject_name="TPSample.uproject",
    )
    report = parse_automation_report(project_path)
    _write_autotest_results(project_path, report, automation_result)
    _write_markdown_report(project_path, report)
    if automation_result["exit_code"] != 0:
        return automation_result["exit_code"]
    return 0 if report.can_confirm_results and report.failed_tests == 0 else 1


def _write_autotest_results(project_path: Path, report, automation_result: dict) -> None:
    output = project_path / "Saved" / "Automation" / "autotest_results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "modules": [
            {
                "name": "TPSampleTest",
                "filter": "+".join(SCOPES),
                "exitCode": automation_result["exit_code"],
                "timedOut": False,
                "logFile": automation_result["automation_log_path"],
                "rawReportDir": automation_result["automation_dir"],
                "results": {
                    "tests": [
                        {"name": test.name, "passed": test.passed, "error": test.error}
                        for test in report.tests
                    ],
                    "summary": {
                        "total": report.executed_tests,
                        "passed": report.passed_tests,
                        "failed": report.failed_tests,
                        "duration_ms": 0,
                    },
                },
            }
        ],
        "overall": {
            "total": report.executed_tests,
            "passed": report.passed_tests,
            "failed": report.failed_tests,
        },
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markdown_report(project_path: Path, report) -> None:
    output = project_path / "Saved" / "Automation" / "Reports" / "scoped-report.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TPSample Scoped Automation Report",
        "",
        "- Scope: `TPSample.Input.*` and `TPSample.Error.*`",
        f"- Total: {report.executed_tests}",
        f"- Passed: {report.passed_tests}",
        f"- Failed: {report.failed_tests}",
        "",
        "## Failure Summary",
        "",
    ]
    failed = [test for test in report.tests if not test.passed]
    if failed:
        for test in failed:
            lines.append(f"- `{test.name}`: {test.error or 'No error details captured'}")
    else:
        lines.append("No failures.")
    output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
