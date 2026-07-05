from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFIER = Path("benchmarks/ue5-skillsbench/tasks/tps-autotest-fix-failing-error-tests/verifier.py")


class FixFailingErrorTaskVerifierTests(unittest.TestCase):
    def test_verifier_accepts_repaired_error_accumulator_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            _write_test_module(project, strong_assertion=True)
            _write_report(
                project,
                [
                    "TPSample.Error.Accumulator.RecordsErrors",
                    "TPSample.Error.Accumulator.FlushClearsQueue",
                    "TPSample.Error.Accumulator.DedupesBroadcast",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])
            self.assertEqual(verifier_result["automation"]["executed_tests"], 3)

    def test_verifier_rejects_weakened_broadcast_assertion_even_with_passing_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            _write_test_module(project, strong_assertion=False)
            _write_report(
                project,
                [
                    "TPSample.Error.Accumulator.RecordsErrors",
                    "TPSample.Error.Accumulator.FlushClearsQueue",
                    "TPSample.Error.Accumulator.DedupesBroadcast",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertNotEqual(result.returncode, 0)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertEqual(verifier_result["failure_class"], "cheating")

    def test_verifier_accepts_alternative_helper_variable_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project, helper_code="void ReportError() { for (const FErrorEvent& Existing : PendingErrors) { if (Existing.Code == Code) { return; } } }")
            _write_test_module(project, strong_assertion=True)
            _write_report(
                project,
                [
                    "TPSample.Error.Accumulator.RecordsErrors",
                    "TPSample.Error.Accumulator.FlushClearsQueue",
                    "TPSample.Error.Accumulator.DedupesBroadcast",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])


def _write_project_shell(project: Path, helper_code: str | None = None) -> None:
    source = project / "Source"
    (source / "TPSample" / "Private").mkdir(parents=True)
    (project / "TPSample.uproject").write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "5.7",
                "Modules": [
                    {"Name": "TPSample", "Type": "Runtime", "LoadingPhase": "Default"},
                    {"Name": "TPSampleTest", "Type": "Editor", "LoadingPhase": "Default"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (source / "TPSampleEditor.Target.cs").write_text(
        'ExtraModuleNames.Add("TPSample");\nExtraModuleNames.Add("TPSampleTest");\n',
        encoding="utf-8",
    )
    if helper_code is None:
        helper_code = "void ReportError() { if (Event.Code == Code) { return; } }\n"
    (source / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp").write_text(
        helper_code,
        encoding="utf-8",
    )


def _write_test_module(project: Path, strong_assertion: bool) -> None:
    module = project / "Source" / "TPSampleTest"
    private = module / "Private"
    private.mkdir(parents=True)
    (module / "TPSampleTest.Build.cs").write_text(
        """
using UnrealBuildTool;

public class TPSampleTest : ModuleRules
{
    public TPSampleTest(ReadOnlyTargetRules Target) : base(Target)
    {
        PrivateDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
            "UnrealEd",
            "TPSample"
        });
    }
}
""".strip(),
        encoding="utf-8",
    )
    assertion = "TestEqual(TEXT(\"broadcast once\"), Helper.BroadcastCount, 1);" if strong_assertion else "TestTrue(TEXT(\"broadcasted\"), Helper.BroadcastCount >= 0);"
    (private / "TPSampleErrorAccumulatorTest.cpp").write_text(
        f"""
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRecordsErrors, "TPSample.Error.Accumulator.RecordsErrors", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FRecordsErrors::RunTest(const FString& Parameters) {{ TestTrue(TEXT("records"), true); return true; }}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFlushClearsQueue, "TPSample.Error.Accumulator.FlushClearsQueue", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FFlushClearsQueue::RunTest(const FString& Parameters) {{ TestTrue(TEXT("flush"), true); return true; }}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDedupesBroadcast, "TPSample.Error.Accumulator.DedupesBroadcast", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FDedupesBroadcast::RunTest(const FString& Parameters) {{ FErrorTestHelper Helper; {assertion} return true; }}
""".strip(),
        encoding="utf-8",
    )


def _write_report(project: Path, names: list[str]) -> None:
    report_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Error_Accumulator"
    report_dir.mkdir(parents=True)
    (report_dir / "index.json").write_text(
        json.dumps({"tests": [{"fullTestPath": name, "state": "Success"} for name in names]}),
        encoding="utf-8",
    )
    (project / "Saved" / "Automation" / "autotest_results.json").write_text("{}", encoding="utf-8")


def _run_verifier(project: Path, artifacts: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PROJECT_PATH": str(project),
        "ARTIFACTS_PATH": str(artifacts),
        "BENCHMARK_ROOT": str(Path("benchmarks/ue5-skillsbench").resolve()),
    }
    return subprocess.run(
        [sys.executable, str(VERIFIER.resolve())],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )


if __name__ == "__main__":
    unittest.main()
