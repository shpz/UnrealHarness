from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFIER = Path("benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/verifier.py")
ORACLE = Path("benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/oracle.py")
SETUP = Path("benchmarks/ue5-skillsbench/tasks/tps-autotest-add-input-math-tests/setup.py")


class AddInputMathTaskVerifierTests(unittest.TestCase):
    def test_setup_helper_exports_functions_for_editor_test_module_linking(self) -> None:
        setup = _load_module("add_input_math_setup", SETUP)

        header = setup._header()

        self.assertIn("TPSAMPLE_API FVector2D NormalizeMoveInput", header)
        self.assertIn("TPSAMPLE_API FVector2D QuantizeLookInput", header)
        self.assertIn("TPSAMPLE_API bool IsInputWithinDeadZone", header)

    def test_oracle_generated_math_tests_avoid_ambiguous_float_test_equal(self) -> None:
        oracle = _load_module("add_input_math_oracle", ORACLE)

        tests_cpp = oracle._tests_cpp()

        self.assertIn("FMath::IsNearlyEqual(Result.X, 0.6, 0.001)", tests_cpp)
        self.assertIn("FMath::IsNearlyEqual(Result.Y, 0.8, 0.001)", tests_cpp)
        self.assertIn("FMath::IsNearlyEqual(Result.X, 0.3", tests_cpp)
        self.assertIn("FMath::IsNearlyEqual(Result.Y, -0.2", tests_cpp)
        self.assertNotIn('TestEqual(TEXT("quantized x")', tests_cpp)
        self.assertNotIn('TestEqual(TEXT("quantized y")', tests_cpp)

    def test_verifier_accepts_registered_editor_test_module_with_three_math_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            _write_test_module(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])
            self.assertEqual(verifier_result["automation"]["executed_tests"], 3)

    def test_verifier_accepts_input_math_test_with_application_context_mask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            _write_test_module_alternative(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertEqual(result.returncode, 0, result.stderr)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertTrue(verifier_result["passed"])

    def test_verifier_rejects_missing_test_module_even_when_report_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "TPSample"
            _write_project_shell(project)
            _write_report(
                project,
                [
                    "TPSample.Input.Math.Normalize",
                    "TPSample.Input.Math.DeadZone",
                    "TPSample.Input.Math.Quantize",
                ],
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()

            result = _run_verifier(project, artifacts)

            self.assertNotEqual(result.returncode, 0)
            verifier_result = json.loads((artifacts / "verifier_result.json").read_text(encoding="utf-8"))
            self.assertEqual(verifier_result["failure_class"], "registration")


def _write_project_shell(project: Path) -> None:
    source = project / "Source"
    source.mkdir(parents=True)
    (project / "TPSample.uproject").write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "5.7",
                "Modules": [{"Name": "TPSample", "Type": "Runtime", "LoadingPhase": "Default"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (source / "TPSampleEditor.Target.cs").write_text(
        'ExtraModuleNames.Add("TPSample");\nExtraModuleNames.Add("TPSampleTest");\n',
        encoding="utf-8",
    )
    (source / "TPSample.Target.cs").write_text(
        'ExtraModuleNames.Add("TPSample");\n',
        encoding="utf-8",
    )


def _write_test_module(project: Path) -> None:
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
    (private / "TPSampleInputMathTest.cpp").write_text(
        """
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNormalize, "TPSample.Input.Math.Normalize", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FNormalize::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDeadZone, "TPSample.Input.Math.DeadZone", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FDeadZone::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FQuantize, "TPSample.Input.Math.Quantize", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FQuantize::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }
""".strip(),
        encoding="utf-8",
    )
    descriptor = json.loads((project / "TPSample.uproject").read_text(encoding="utf-8"))
    descriptor["Modules"].append({"Name": "TPSampleTest", "Type": "Editor", "LoadingPhase": "Default"})
    (project / "TPSample.uproject").write_text(json.dumps(descriptor, indent=2), encoding="utf-8")


def _write_test_module_alternative(project: Path) -> None:
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
    (private / "InputMathTest.cpp").write_text(
        """
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FNormalize, "TPSample.Input.Math.Normalize", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FNormalize::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FDeadZone, "TPSample.Input.Math.DeadZone", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FDeadZone::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FQuantize, "TPSample.Input.Math.Quantize", EAutomationTestFlags::ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FQuantize::RunTest(const FString& Parameters) { TestTrue(TEXT("ok"), true); return true; }
""".strip(),
        encoding="utf-8",
    )
    descriptor = json.loads((project / "TPSample.uproject").read_text(encoding="utf-8"))
    descriptor["Modules"].append({"Name": "TPSampleTest", "Type": "Editor", "LoadingPhase": "Default"})
    (project / "TPSample.uproject").write_text(json.dumps(descriptor, indent=2), encoding="utf-8")


def _write_report(project: Path, names: list[str]) -> None:
    report_dir = project / "Saved" / "Automation" / "Reports" / "Raw" / "TPSample_Input_Math"
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


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
