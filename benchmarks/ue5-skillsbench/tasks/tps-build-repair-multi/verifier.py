"""Verifier for multi-module build-repair: clean build + multiple fixture checks."""
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

    fixture1 = project_path / "Source" / "TPSample" / "SkillsBenchNavProbe.cpp"
    fixture2 = project_path / "Source" / "TPSample" / "SkillsBenchGameplayTaskProbe.cpp"
    fixture3 = project_path / "Source" / "TPSample" / "SkillsBenchAIModuleProbe.h"
    build_log = artifacts_path / "build.log"

    checks = []
    build_result = None
    failure_class = None
    passed = False

    try:
        # Check fixture 1 exists and has correct code
        f1_exists = fixture1.exists()
        f1_has_nav = False
        f1_has_ai = False
        if f1_exists:
            text = fixture1.read_text(encoding="utf-8")
            f1_has_nav = "UNavigationSystemV1::FindPathToLocationSynchronously" in text
            f1_has_ai = "AAIController::StaticClass" in text
        checks.append({"name": "fixture1_nav_probe", "passed": f1_exists and f1_has_nav and f1_has_ai, "detail": f"exists={f1_exists}, nav={f1_has_nav}, ai={f1_has_ai}"})

        # Check fixture 2 exists and has correct code
        f2_exists = fixture2.exists()
        f2_has_task = False
        f2_has_component = False
        if f2_exists:
            text = fixture2.read_text(encoding="utf-8")
            f2_has_task = "UGameplayTask::StaticClass" in text
            f2_has_component = "UGameplayTasksComponent::StaticClass" in text
        checks.append({"name": "fixture2_task_probe", "passed": f2_exists and f2_has_task and f2_has_component, "detail": f"exists={f2_exists}, task={f2_has_task}, component={f2_has_component}"})

        # Check fixture 3 exists and has correct code
        f3_exists = fixture3.exists()
        f3_has_uclass = False
        f3_has_ai = False
        if f3_exists:
            text = fixture3.read_text(encoding="utf-8")
            f3_has_uclass = "UCLASS()" in text
            f3_has_ai = "AAIController" in text
        checks.append({"name": "fixture3_ai_header", "passed": f3_exists and f3_has_uclass and f3_has_ai, "detail": f"exists={f3_exists}, uclass={f3_has_uclass}, ai={f3_has_ai}"})

        # Check Build.cs has required modules
        build_cs = project_path / "Source" / "TPSample" / "TPSample.Build.cs"
        build_cs_text = build_cs.read_text(encoding="utf-8") if build_cs.exists() else ""
        has_nav_mod = "\"NavigationSystem\"" in build_cs_text
        has_task_mod = "\"GameplayTasks\"" in build_cs_text
        has_ai_mod = "\"AIModule\"" in build_cs_text
        checks.append({"name": "build_cs_navigation_system", "passed": has_nav_mod, "detail": f"NavigationSystem in Build.cs"})
        checks.append({"name": "build_cs_gameplay_tasks", "passed": has_task_mod, "detail": f"GameplayTasks in Build.cs"})
        checks.append({"name": "build_cs_ai_module", "passed": has_ai_mod, "detail": f"AIModule in Build.cs"})

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

        # Determine overall failure class
        if not (f1_exists and f1_has_nav and f1_has_ai):
            failure_class = "wrong-fix"
        elif not (f2_exists and f2_has_task and f2_has_component):
            failure_class = "wrong-fix"
        elif not (f3_exists and f3_has_uclass and f3_has_ai):
            failure_class = "wrong-fix"
        elif not (has_nav_mod and has_task_mod and has_ai_mod):
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
