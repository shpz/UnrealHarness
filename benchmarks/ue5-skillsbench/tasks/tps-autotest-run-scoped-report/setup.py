"""Inject a registered TPSampleTest module with scoped Automation tests."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> None:
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()
    source = project_path / "Source"
    test_module = source / "TPSampleTest"
    private = test_module / "Private"
    private.mkdir(parents=True, exist_ok=True)

    (test_module / "TPSampleTest.Build.cs").write_text(_build_cs(), encoding="utf-8")
    (private / "TPSampleTestModule.cpp").write_text(_module_cpp(), encoding="utf-8")
    (private / "TPSampleScopedAutomationTests.cpp").write_text(_tests_cpp(), encoding="utf-8")
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

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleInputNormalizeTest, "TPSample.Input.Math.Normalize", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleInputNormalizeTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("normalization scope is available"), true);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleInputDeadZoneTest, "TPSample.Input.Math.DeadZone", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleInputDeadZoneTest::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("dead zone check"), 1 + 1, 2);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleInputQuantizeTest, "TPSample.Input.Math.Quantize", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleInputQuantizeTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("quantize check"), 10 % 5 == 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleErrorAddTest, "TPSample.Error.Accumulator.Add", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleErrorAddTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("error add scope is available"), true);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleErrorFlushTest, "TPSample.Error.Accumulator.Flush", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleErrorFlushTest::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("flush count"), 3, 3);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleErrorDedupeTest, "TPSample.Error.Accumulator.Dedupe", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleErrorDedupeTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("dedupe check"), true);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSamplePerformanceMemoryTest, "TPSample.Performance.Memory.Budget", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSamplePerformanceMemoryTest::RunTest(const FString& Parameters)
{
    TestTrue(TEXT("performance scope should not be selected by this task"), true);
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


if __name__ == "__main__":
    main()
