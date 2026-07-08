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

    def test_verifier_accepts_tset_dedup_in_flush(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(
                project,
                helper_code='''
void FTPSampleErrorAccumulator::ReportError(const FString& Code, const FString& Message)
{
    PendingErrors.Add({Code, Message});
}

int32 FTPSampleErrorAccumulator::Flush(TFunctionRef<void(const FString& Code, const FString& Message)> OnError)
{
    int32 BroadcastCount = 0;
    TSet<FString> BroadcastCodes;
    for (const FTPSampleErrorEvent& Event : PendingErrors)
    {
        if (!BroadcastCodes.Contains(Event.Code))
        {
            OnError(Event.Code, Event.Message);
            BroadcastCodes.Add(Event.Code);
            ++BroadcastCount;
        }
    }
    PendingErrors.Reset();
    return BroadcastCount;
}
''',
            )
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

    def test_verifier_accepts_index_based_dedup_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(
                project,
                helper_code='''
void FTPSampleErrorAccumulator::ReportError(const FString& Code, const FString& Message)
{
    for (int32 Index = 0; Index < PendingErrors.Num(); ++Index)
    {
        if (PendingErrors[Index].Code == Code)
        {
            PendingErrors[Index].Message = Message;
            return;
        }
    }
    PendingErrors.Add({Code, Message});
}
''',
            )
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

    def test_verifier_rejects_whitespace_only_helper_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            # Commit the fixed helper as HEAD so the only uncommitted change is a comment.
            subprocess.run(["git", "add", "Source/TPSample/Private/TPSampleErrorAccumulator.cpp"], cwd=project, check=True, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", "fix helper"], cwd=project, check=True, capture_output=True, text=True)
            # Modify helper with only whitespace/comment changes
            helper_path = project / "Source" / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp"
            original = helper_path.read_text(encoding="utf-8")
            helper_path.write_text(original + "\n// no-op comment\n", encoding="utf-8")
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

            self.assertNotEqual(result.returncode, 0)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertEqual(verifier_result["failure_class"], "cheating")

    def test_verifier_rejects_block_comment_dedup_token_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            # Commit the baseline helper so the only uncommitted change is a comment.
            subprocess.run(["git", "add", "Source/TPSample/Private/TPSampleErrorAccumulator.cpp"], cwd=project, check=True, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", "fix helper"], cwd=project, check=True, capture_output=True, text=True)
            # Modify helper with only a multi-line block comment that contains a dedup token.
            helper_path = project / "Source" / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp"
            original = helper_path.read_text(encoding="utf-8")
            helper_path.write_text(
                original + "\n/*\n * Consider using TSet<FString> here to dedupe.\n */\n",
                encoding="utf-8",
            )
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

            self.assertNotEqual(result.returncode, 0)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertEqual(verifier_result["failure_class"], "cheating")


_BUGGY_HELPER_BASELINE = """\
void FTPSampleErrorAccumulator::ReportError(const FString& Code, const FString& Message)
{
    PendingErrors.Add({Code, Message});
}
"""


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
    helper_path = source / "TPSample" / "Private" / "TPSampleErrorAccumulator.cpp"
    # Seed a git baseline so the verifier can detect meaningful production diffs.
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True, text=True)
    helper_path.write_text(_BUGGY_HELPER_BASELINE, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=project, check=True, capture_output=True, text=True)
    helper_path.write_text(helper_code, encoding="utf-8")


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
        # Unit tests verify artifact parsing; no engine rerun available here.
        "SKILLSBENCH_RERUN_AUTOMATION": "0",
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
