from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


TASK_DIR = Path("benchmarks/ue5-skillsbench/tasks/tps-build-fix-module-dependency")


class BuildModuleDependencyTaskContractTests(unittest.TestCase):
    def test_setup_removes_umg_dependency_and_oracle_restores_it(self) -> None:
        setup = _load_module("build_module_dependency_setup", TASK_DIR / "setup.py")
        oracle = _load_module("build_module_dependency_oracle", TASK_DIR / "oracle.py")

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "TPSample"
            _write_project_shell(project)

            with _pushd(project):
                setup.main()

            build_cs = project / "Source" / "TPSample" / "TPSample.Build.cs"
            self.assertNotIn('"UMG"', build_cs.read_text(encoding="utf-8"))
            self.assertTrue((project / "Source" / "TPSample" / "TPSampleDependencyWidget.h").exists())
            self.assertTrue((project / "Source" / "TPSample" / "TPSampleDependencyWidget.cpp").exists())

            oracle._restore_umg_dependency(project)

            self.assertIn('"UMG"', build_cs.read_text(encoding="utf-8"))


def _write_project_shell(project: Path) -> None:
    source = project / "Source" / "TPSample"
    source.mkdir(parents=True)
    (source / "TPSample.Build.cs").write_text(
        """
using UnrealBuildTool;

public class TPSample : ModuleRules
{
    public TPSample(ReadOnlyTargetRules Target) : base(Target)
    {
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
            "UMG"
        });
    }
}
""".strip(),
        encoding="utf-8",
    )


class _pushd:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.previous = Path.cwd()

    def __enter__(self) -> None:
        os.chdir(self.path)

    def __exit__(self, exc_type, exc, tb) -> None:
        os.chdir(self.previous)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
