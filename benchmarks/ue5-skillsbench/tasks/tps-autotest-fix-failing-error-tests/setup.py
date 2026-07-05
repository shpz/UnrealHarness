"""Inject a buggy error accumulator and failing Automation tests."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    project_path = Path.cwd()
    _write_helper(project_path)
    _write_test_module(project_path)
    _register_uproject(project_path / "TPSample.uproject")
    _register_editor_target(project_path / "Source" / "TPSampleEditor.Target.cs")


def _write_helper(project_path: Path) -> None:
    public_dir = project_path / "Source" / "TPSample" / "Public"
    private_dir = project_path / "Source" / "TPSample" / "Private"
    public_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "TPSampleErrorAccumulator.h").write_text(_helper_header(), encoding="utf-8")
    (private_dir / "TPSampleErrorAccumulator.cpp").write_text(_buggy_helper_source(), encoding="utf-8")


def _write_test_module(project_path: Path) -> None:
    module = project_path / "Source" / "TPSampleTest"
    private = module / "Private"
    private.mkdir(parents=True, exist_ok=True)
    (module / "TPSampleTest.Build.cs").write_text(_build_cs(), encoding="utf-8")
    (private / "TPSampleTestModule.cpp").write_text(_module_cpp(), encoding="utf-8")
    (private / "TPSampleErrorAccumulatorTest.cpp").write_text(_tests_cpp(), encoding="utf-8")


def _helper_header() -> str:
    return r"""#pragma once

#include "CoreMinimal.h"

struct TPSAMPLE_API FTPSampleErrorEvent
{
    FString Code;
    FString Message;
};

class TPSAMPLE_API FTPSampleErrorAccumulator
{
public:
    void ReportError(const FString& Code, const FString& Message);
    int32 Flush(TFunctionRef<void(const FString& Code, const FString& Message)> OnError);
    int32 Num() const;

private:
    TArray<FTPSampleErrorEvent> PendingErrors;
};
"""


def _buggy_helper_source() -> str:
    return r"""#include "TPSampleErrorAccumulator.h"

void FTPSampleErrorAccumulator::ReportError(const FString& Code, const FString& Message)
{
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
#include "TPSampleErrorAccumulator.h"

struct FErrorTestHelper
{
    int32 BroadcastCount = 0;
    TArray<FString> Codes;

    void Record(const FString& Code, const FString& Message)
    {
        ++BroadcastCount;
        Codes.Add(Code);
    }
};

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleErrorRecordsTest, "TPSample.Error.Accumulator.RecordsErrors", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleErrorRecordsTest::RunTest(const FString& Parameters)
{
    FTPSampleErrorAccumulator Accumulator;
    FErrorTestHelper Helper;
    Accumulator.ReportError(TEXT("Input.Missing"), TEXT("Input mapping is missing"));

    TestEqual(TEXT("pending count"), Accumulator.Num(), 1);
    Accumulator.Flush([&Helper](const FString& Code, const FString& Message)
    {
        Helper.Record(Code, Message);
    });
    TestEqual(TEXT("broadcast count"), Helper.BroadcastCount, 1);
    TestEqual(TEXT("broadcast code"), Helper.Codes[0], FString(TEXT("Input.Missing")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleErrorFlushClearsTest, "TPSample.Error.Accumulator.FlushClearsQueue", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleErrorFlushClearsTest::RunTest(const FString& Parameters)
{
    FTPSampleErrorAccumulator Accumulator;
    FErrorTestHelper Helper;
    Accumulator.ReportError(TEXT("Input.Invalid"), TEXT("Input value is invalid"));

    Accumulator.Flush([&Helper](const FString& Code, const FString& Message)
    {
        Helper.Record(Code, Message);
    });
    TestEqual(TEXT("queue cleared"), Accumulator.Num(), 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTPSampleErrorDedupeTest, "TPSample.Error.Accumulator.DedupesBroadcast", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FTPSampleErrorDedupeTest::RunTest(const FString& Parameters)
{
    FTPSampleErrorAccumulator Accumulator;
    FErrorTestHelper Helper;
    Accumulator.ReportError(TEXT("Input.Duplicate"), TEXT("First message"));
    Accumulator.ReportError(TEXT("Input.Duplicate"), TEXT("Duplicate message"));

    Accumulator.Flush([&Helper](const FString& Code, const FString& Message)
    {
        Helper.Record(Code, Message);
    });
    TestEqual(TEXT("duplicate code should broadcast once"), Helper.BroadcastCount, 1);
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
