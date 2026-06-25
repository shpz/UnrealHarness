"""Inject a build-breaking fixture and create a read-only stub DLL to block linking."""
import os
import sys
import stat
from pathlib import Path


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()
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

    # 2. Create a read-only stub DLL in Binaries/Win64 to block the linker
    binaries_dir = project_path / "Binaries" / "Win64"
    binaries_dir.mkdir(parents=True, exist_ok=True)
    stub_dll = binaries_dir / "UnrealEditor-TPSample.dll"
    stub_dll.write_bytes(b"")  # empty file
    # Make it read-only on Windows
    os.chmod(stub_dll, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    # Also use Windows attrib for extra measure
    os.system(f'attrib +R "{stub_dll}"')
    print(f"Created read-only stub DLL: {stub_dll}")


if __name__ == "__main__":
    main()
