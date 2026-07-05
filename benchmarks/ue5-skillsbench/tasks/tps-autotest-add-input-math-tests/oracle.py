"""Oracle action for tps-autotest-add-input-math-tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


RUNNER = Path(__file__).resolve().parents[2] / "runner"
sys.path.insert(0, str(RUNNER))

from automation_report import parse_automation_report  # noqa: E402
from unreal import invoke_automation, invoke_build  # noqa: E402


SCOPE = "TPSample.Input.Math"


def main() -> int:
    project_path = Path.cwd()
    artifacts_path = Path(os.environ.get("ARTIFACTS_PATH", project_path / "Saved" / "Automation"))

    _write_test_module(project_path)

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

    automation_dir = project_path / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Input_Math"
    automation_result = invoke_automation(
        project_path=project_path,
        test_filter=SCOPE,
        automation_dir=automation_dir,
        uproject_name="TPSample.uproject",
    )
    report = parse_automation_report(project_path)
    _write_autotest_results(project_path, report, automation_result)
    return 0 if automation_result["exit_code"] == 0 and report.failed_tests == 0 and report.executed_tests >= 3 else 1


def _write_test_module(project_path: Path) -> None:
    source = project_path / "Source"
    module = source / "TPSampleTest"
    private = module / "Private"
    private.mkdir(parents=True, exist_ok=True)
    (module / "TPSampleTest.Build.cs").write_text(_build_cs(), encoding="utf-8")
    (private / "TPSampleTestModule.cpp").write_text(_module_cpp(), encoding="utf-8")
    (private / "TPSampleInputMathTest.cpp").write_text(_tests_cpp(), encoding="utf-8")
    _register_uproject(project_path / "TPSample.uproject")
    _register_editor_target(source / "TPSampleEditor.Target.cs")


def _build_cs() -> str:
    return """using UnrealBuildTool;

public class TPSampleTest : ModuleRules
{
    public TPSampleTest(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
            "UnrealEd",
            "TPSample"
        });
    }
}
"""


def _module_cpp() -> str:
    return """#include "Modules/ModuleManager.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, TPSampleTest)
"""


def _tests_cpp() -> str:
    return r'''#include "Misc/AutomationTest.h"
#include "TPSampleInputMath.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleInputMathNormalizeTest, "TPSample.Input.Math.Normalize", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleInputMathNormalizeTest::RunTest(const FString& Parameters)
{
    const FVector2D Result = TPSampleInputMath::NormalizeMoveInput(FVector2D(3.0f, 4.0f), 0.1f);
    TestTrue(TEXT("normalized vector has unit length"), FMath::IsNearlyEqual(Result.Size(), 1.0f));
    TestTrue(TEXT("preserves direction"), FMath::IsNearlyEqual(Result.X, 0.6, 0.001) && FMath::IsNearlyEqual(Result.Y, 0.8, 0.001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleInputMathDeadZoneTest, "TPSample.Input.Math.DeadZone", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleInputMathDeadZoneTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("tiny input is inside dead zone"), TPSampleInputMath::IsInputWithinDeadZone(FVector2D(0.02f, 0.01f), 0.05f));
    TestEqual(TEXT("inside dead zone normalizes to zero"), TPSampleInputMath::NormalizeMoveInput(FVector2D(0.02f, 0.01f), 0.05f), FVector2D::ZeroVector);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleInputMathQuantizeTest, "TPSample.Input.Math.Quantize", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleInputMathQuantizeTest::RunTest(const FString& Parameters)
{
    const FVector2D Result = TPSampleInputMath::QuantizeLookInput(FVector2D(0.26f, -0.24f), 0.1f);
    TestTrue(TEXT("quantized x"), FMath::IsNearlyEqual(Result.X, 0.3));
    TestTrue(TEXT("quantized y"), FMath::IsNearlyEqual(Result.Y, -0.2));
    return true;
}
'''


def _register_uproject(uproject_path: Path) -> None:
    descriptor = json.loads(uproject_path.read_text(encoding="utf-8"))
    modules = descriptor.setdefault("Modules", [])
    if not any(module.get("Name") == "TPSampleTest" for module in modules):
        modules.append({"Name": "TPSampleTest", "Type": "Editor", "LoadingPhase": "Default"})
    uproject_path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")


def _register_editor_target(target_path: Path) -> None:
    text = target_path.read_text(encoding="utf-8")
    marker = 'ExtraModuleNames.Add("TPSample");'
    addition = 'ExtraModuleNames.Add("TPSampleTest");'
    if addition not in text:
        text = text.replace(marker, f"{marker}\n\t\t{addition}")
    target_path.write_text(text, encoding="utf-8")


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
