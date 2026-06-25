"""Inject a build-breaking fixture, trigger a UBT build to generate .obj files, then poison their timestamps."""
import json
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path


def resolve_engine_root(engine_association: str) -> Path:
    if "." in engine_association and engine_association.replace(".", "").isdigit():
        for hive, key_fmt in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine\{}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\{}"),
        ]:
            try:
                with winreg.OpenKey(hive, key_fmt.format(engine_association)) as key:
                    value, _ = winreg.QueryValueEx(key, "InstalledDirectory")
                    if value and Path(value).exists():
                        return Path(value)
            except OSError:
                continue

    for hive, key_fmt in [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds\{}"),
    ]:
        try:
            with winreg.OpenKey(hive, key_fmt.format(engine_association)) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value and Path(value).exists():
                    return Path(value)
        except OSError:
            continue

    raise RuntimeError(f"Could not resolve Unreal EngineAssociation '{engine_association}' from registry.")


def get_engine_paths(project_path: Path) -> Path:
    uproject_path = project_path / "TPSample.uproject"
    descriptor = json.loads(uproject_path.read_text(encoding="utf-8"))
    engine_association = descriptor.get("EngineAssociation", "")
    if not engine_association:
        raise RuntimeError("Missing EngineAssociation in .uproject")
    root = resolve_engine_root(engine_association)
    build_bat = root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
    if not build_bat.exists():
        raise RuntimeError(f"Build.bat not found: {build_bat}")
    return build_bat


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd().resolve()
    source_dir = project_path / "Source" / "TPSample"
    if not source_dir.exists():
        raise RuntimeError(f"Source directory not found: {source_dir}")

    # 1. Inject fixture referencing missing modules (NavigationSystem + GameplayTasks)
    fixture_path = source_dir / "SkillsBenchBuildProbe.cpp"
    fixture_source = '''#include "CoreMinimal.h"
#include "GameplayTask.h"
#include "NavigationSystem.h"
#include "NavigationPath.h"
#include "Engine/World.h"

namespace SkillsBench
{
int32 CountProjectedNavigationPoints(UWorld* World, const FVector& Start, const FVector& End)
{
	if (World == nullptr)
	{
		return 0;
	}

	// Uses NavigationSystem module
	UNavigationPath* Path = UNavigationSystemV1::FindPathToLocationSynchronously(World, Start, End);
	int32 Count = Path != nullptr ? Path->PathPoints.Num() : 0;

	// Uses GameplayTasks module (just reference a type to ensure linkage)
	UClass* TaskClass = UGameplayTask::StaticClass();
	return Count + (TaskClass ? 0 : 0);
}
}
'''
    fixture_path.write_text(fixture_source, encoding="utf-8")
    print(f"Injected build-repair fixture: {fixture_path}")

    # 2. Trigger a real UBT build. It will compile successfully but fail at link stage (LNK2019)
    #    because Build.cs does NOT list NavigationSystem / GameplayTasks as dependencies.
    build_bat = get_engine_paths(project_path)
    uproject_file = project_path / "TPSample.uproject"

    print(f"Triggering UBT build to generate .obj files...")
    result = subprocess.run(
        [str(build_bat), "TPSampleEditor", "Win64", "Development", str(uproject_file), "-waitmutex", "-NoUBA"],
        capture_output=True,
        text=True,
        cwd=str(project_path),
        shell=False,
    )
    print(f"UBT build exited with code {result.returncode} (expected non-zero due to missing modules)")
    if result.stdout:
        print(result.stdout[-2000:])  # Print tail of stdout for debugging
    if result.stderr:
        print(result.stderr[-2000:])

    # 3. Find all TPSample module .obj files and set their timestamps to the future
    intermediate_dir = project_path / "Intermediate" / "Build" / "Win64"
    obj_files = list(intermediate_dir.rglob("Module.TPSample*.cpp.obj"))
    if not obj_files:
        # Fallback: any .obj under Intermediate/Build/Win64 that belongs to TPSample
        obj_files = [p for p in intermediate_dir.rglob("*.obj") if "TPSample" in p.name]

    if not obj_files:
        raise RuntimeError(f"Could not find any TPSample .obj files under {intermediate_dir}")

    future_time = time.time() + 86400 * 7  # 7 days in the future
    for obj in obj_files:
        os.utime(obj, (future_time, future_time))
        print(f"Poisoned timestamp: {obj} -> {time.ctime(future_time)}")

    print(f"Setup complete. Poisoned {len(obj_files)} .obj file(s).")


if __name__ == "__main__":
    main()
