"""Verifier for engine-resolve: build project after GUID registry conversion."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runner"))
from unreal import invoke_build


def main():
    import os

    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))

    build_log = artifacts_path / "build.log"

    checks = []
    build_result = None
    failure_class = None
    passed = False

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
        build_passed = build_result["exit_code"] == 0
        checks.append({
            "name": "ubt_build",
            "passed": build_passed,
            "duration_ms": int(build_result["duration_seconds"] * 1000),
            "detail": build_result["command_line"],
        })

        if not build_passed:
            failure_class = "build"

        passed = failure_class is None
    except Exception as e:
        passed = False
        failure_class = "verifier-error"
        checks.append({"name": "verifier_exception", "passed": False, "detail": str(e)})

    verifier_result = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": checks,
        "build": {
            "exit_code": build_result["exit_code"] if build_result else -1,
            "duration_seconds": build_result["duration_seconds"] if build_result else None,
            "log": str(build_log),
            "engine_root": build_result["engine_root"] if build_result else None,
        } if build_result else None,
    }

    out_path = artifacts_path / "verifier_result.json"
    out_path.write_text(json.dumps(verifier_result, indent=2), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
