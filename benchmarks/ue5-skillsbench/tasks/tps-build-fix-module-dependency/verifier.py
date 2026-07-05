"""Verifier for tps-build-fix-module-dependency."""
from __future__ import annotations

import os
from pathlib import Path
import sys


RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))

from unreal import invoke_build  # noqa: E402
from verifier_result import make_result, write_result  # noqa: E402


def main() -> int:
    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))
    build_cs = project_path / "Source" / "TPSample" / "TPSample.Build.cs"
    widget_header = project_path / "Source" / "TPSample" / "TPSampleDependencyWidget.h"
    widget_source = project_path / "Source" / "TPSample" / "TPSampleDependencyWidget.cpp"
    build_log = artifacts_path / "build.log"

    checks = [
        {"name": "dependency_widget_header_exists", "passed": widget_header.exists(), "details": str(widget_header)},
        {"name": "dependency_widget_source_exists", "passed": widget_source.exists(), "details": str(widget_source)},
        {"name": "umg_dependency_present", "passed": '"UMG"' in _read_text(build_cs), "details": str(build_cs)},
    ]

    build_result = None
    if all(check["passed"] for check in checks):
        try:
            build_result = invoke_build(
                project_path=project_path,
                target="TPSampleEditor",
                platform="Win64",
                configuration="Development",
                uproject_name="TPSample.uproject",
                clean=True,
                build_log_path=build_log,
            )
            checks.append({
                "name": "ubt_build",
                "passed": build_result["exit_code"] == 0,
                "duration_ms": int(build_result["duration_seconds"] * 1000),
                "details": build_result["command_line"],
            })
        except Exception as exc:
            checks.append({"name": "verifier_exception", "passed": False, "details": str(exc)})

    failure_class = None
    for check in checks:
        if check["passed"]:
            continue
        failure_class = "build"
        break

    result = make_result(
        passed=failure_class is None,
        failure_class=failure_class,
        checks=checks,
        build={
            "exit_code": build_result["exit_code"] if build_result else -1,
            "duration_seconds": build_result["duration_seconds"] if build_result else None,
            "log": str(build_log),
            "target": "TPSampleEditor",
            "platform": "Win64",
            "configuration": "Development",
        },
    )
    write_result(artifacts_path / "verifier_result.json", result)
    return 0 if result["passed"] else 1


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
