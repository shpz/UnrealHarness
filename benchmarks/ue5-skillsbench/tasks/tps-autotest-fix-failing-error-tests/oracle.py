"""Oracle action for tps-autotest-fix-failing-error-tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))

from automation_report import parse_automation_report  # noqa: E402
from unreal import invoke_automation, invoke_build  # noqa: E402


SCOPE = "TPSample.Error.Accumulator"


def main() -> int:
    project_path = Path.cwd()
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", project_path / "Saved" / "Automation"))

    (project_path / "Source" / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp").write_text(
        _fixed_helper_source(),
        encoding="utf-8",
    )

    build_result = invoke_build(
        project_path=project_path,
        target="TPSampleEditor",
        platform="Win64",
        configuration="Development",
        uproject_name="TPSample.uproject",
        clean=False,
        build_log_path=artifacts_path / "build.log",
    )
    if build_result["exit_code"] != 0:
        return build_result["exit_code"]

    automation_dir = project_path / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Error_Accumulator"
    automation_result = invoke_automation(
        project_path=project_path,
        test_filter=SCOPE,
        automation_dir=automation_dir,
        uproject_name="TPSample.uproject",
    )
    report = parse_automation_report(project_path)
    _write_autotest_results(project_path, report, automation_result)
    return 0 if automation_result["exit_code"] == 0 and report.failed_tests == 0 and report.executed_tests >= 3 else 1


def _fixed_helper_source() -> str:
    return r"""#include "TPSampleErrorAccumulator.h"

void FTPSampleErrorAccumulator::ReportError(const FString& Code, const FString& Message)
{
    for (FTPSampleErrorEvent& Event : PendingErrors)
    {
        if (Event.Code == Code)
        {
            Event.Message = Message;
            return;
        }
    }

    PendingErrors.Add({Code, Message});
}

int32 FTPSampleErrorAccumulator::Flush(TFunctionRef<void(const FString& Code, const FString& Message)> OnError)
{
    int32 BroadcastCount = 0;
    for (const FTPSampleErrorEvent& Event : PendingErrors)
    {
        OnError(Event.Code, Event.Message);
        ++BroadcastCount;
    }
    PendingErrors.Reset();
    return BroadcastCount;
}

int32 FTPSampleErrorAccumulator::Num() const
{
    return PendingErrors.Num();
}
"""


def _write_autotest_results(project_path: Path, report, automation_result: dict) -> None:
    output = project_path / "Saved" / "Automation" / "autotest_results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "modules": [
            {
                "name": "TPSampleTest",
                "filter": SCOPE,
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


if __name__ == "__main__":
    sys.exit(main())
