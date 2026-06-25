"""Verifier for cache-poisoned build-repair: clean build + static fixture + Build.cs checks."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runner"))
from unreal import invoke_build


def main():
    import os

    project_path = Path(os.environ.get("PROJECT_PATH", "."))
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", "artifacts"))

    fixture_path = project_path / "Source" / "TPSample" / "SkillsBenchBuildProbe.cpp"
    build_log = artifacts_path / "build.log"

    checks = []
    build_result = None
    failure_class = None
    passed = False

    try:
        fixture_exists = fixture_path.exists()
        checks.append({"name": "fixture_exists", "passed": fixture_exists, "detail": str(fixture_path)})

        fixture_has_probe = False
        fixture_has_navigation_call = False
        fixture_has_gameplay_task = False
        if fixture_exists:
            text = fixture_path.read_text(encoding="utf-8")
            fixture_has_probe = "CountProjectedNavigationPoints" in text
            fixture_has_navigation_call = "UNavigationSystemV1::FindPathToLocationSynchronously" in text
            fixture_has_gameplay_task = "UGameplayTask::StaticClass" in text

        checks.append({"name": "fixture_probe_code", "passed": fixture_has_probe, "detail": "CountProjectedNavigationPoints must remain present."})
        checks.append({"name": "fixture_navigation_call", "passed": fixture_has_navigation_call, "detail": "NavigationSystem call must remain present."})
        checks.append({"name": "fixture_gameplay_task", "passed": fixture_has_gameplay_task, "detail": "GameplayTask reference must remain present."})

        # Check Build.cs has required modules
        build_cs = project_path / "Source" / "TPSample" / "TPSample.Build.cs"
        build_cs_text = build_cs.read_text(encoding="utf-8") if build_cs.exists() else ""
        has_nav_mod = "\"NavigationSystem\"" in build_cs_text
        has_task_mod = "\"GameplayTasks\"" in build_cs_text
        checks.append({"name": "build_cs_navigation_system", "passed": has_nav_mod, "detail": "NavigationSystem in Build.cs"})
        checks.append({"name": "build_cs_gameplay_tasks", "passed": has_task_mod, "detail": "GameplayTasks in Build.cs"})

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

        log_text = ""
        if build_log.exists():
            log_text = build_log.read_text(encoding="utf-8")

        has_compiler_errors = bool(re.search(r'error C\d+|fatal error|UnrealHeaderTool failed|error LNK\d*', log_text, re.IGNORECASE))
        checks.append({"name": "build_log_clean", "passed": not has_compiler_errors, "detail": "No compiler, linker, fatal, or UHT errors in build.log."})

        if not fixture_exists or not fixture_has_probe or not fixture_has_navigation_call or not fixture_has_gameplay_task:
            failure_class = "wrong-fix"
        elif not has_nav_mod or not has_task_mod:
            failure_class = "wrong-fix"
        elif not build_passed or has_compiler_errors:
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
