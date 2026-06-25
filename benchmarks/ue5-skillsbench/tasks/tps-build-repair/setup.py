"""Inject a build-breaking fixture that references two missing UE modules."""
import sys
from pathlib import Path


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    source_dir = project_path / "Source" / "TPSample"
    if not source_dir.exists():
        raise RuntimeError(f"Source directory not found: {source_dir}")

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


if __name__ == "__main__":
    main()
