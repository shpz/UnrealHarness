"""Verifier for smoke test: build baseline project from clean state."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runner"))
from unreal import invoke_build


def main():
    workspace_root = Path(__name__).resolve()
    # When called via runner, use env vars; fallback for direct testing
    project_path = Path(__import__("os").environ.get("PROJECT_PATH", workspace_root / "TPSample"))
    artifacts_path = Path(__import__("os").environ.get("ARTIFACTS_PATH", workspace_root / "artifacts"))

    build_log = artifacts_path / "build.log"
    result = invoke_build(
        project_path=project_path,
        target="TPSampleEditor",
        platform="Win64",
        configuration="Development",
        uproject_name="TPSample.uproject",
        clean=True,
        build_log_path=build_log,
    )

    passed = result["exit_code"] == 0
    failure_class = None
    if not passed:
        failure_class = "build"

    verifier_result = {
        "passed": passed,
        "failure_class": failure_class,
        "checks": [
            {"name": "ubt_build", "passed": passed, "duration_ms": int(result["duration_seconds"] * 1000), "detail": result["command_line"]}
        ],
        "build": {
            "exit_code": result["exit_code"],
            "duration_seconds": result["duration_seconds"],
            "log": str(build_log),
            "engine_root": result["engine_root"],
        },
    }

    out_path = artifacts_path / "verifier_result.json"
    out_path.write_text(json.dumps(verifier_result, indent=2), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
