"""Inject multiple build-breaking fixtures across 3 new source files, each referencing different missing UE modules."""
import sys
from pathlib import Path


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    source_dir = project_path / "Source" / "TPSample"
    if not source_dir.exists():
        raise RuntimeError(f"Source directory not found: {source_dir}")

    # Fixture 1: NavigationSystem + AIModule (cpp)
    fixture1_path = source_dir / "SkillsBenchNavProbe.cpp"
    fixture1_source = '''#include "CoreMinimal.h"
#include "NavigationSystem.h"
#include "NavigationPath.h"
#include "AIController.h"
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

	// Uses AIModule module (just reference a type to ensure linkage)
	UClass* AIControllerClass = AAIController::StaticClass();
	return Count + (AIControllerClass ? 0 : 0);
}
}
'''
    fixture1_path.write_text(fixture1_source, encoding="utf-8")
    print(f"Injected fixture 1: {fixture1_path}")

    # Fixture 2: GameplayTasks (cpp)
    fixture2_path = source_dir / "SkillsBenchGameplayTaskProbe.cpp"
    fixture2_source = '''#include "CoreMinimal.h"
#include "GameplayTask.h"
#include "GameplayTasksComponent.h"

namespace SkillsBench
{
UClass* GetGameplayTaskBaseClass()
{
	// Uses GameplayTasks module
	return UGameplayTask::StaticClass();
}

UClass* GetGameplayTasksComponentClass()
{
	// Uses GameplayTasks module (component class)
	return UGameplayTasksComponent::StaticClass();
}
}
'''
    fixture2_path.write_text(fixture2_source, encoding="utf-8")
    print(f"Injected fixture 2: {fixture2_path}")

    # Fixture 3: AIModule (header) - declares a simple UCLASS with inline implementation
    fixture3_path = source_dir / "SkillsBenchAIModuleProbe.h"
    fixture3_source = '''#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "SkillsBenchAIModuleProbe.generated.h"

UCLASS()
class USkillsBenchAIModuleProbe : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable)
	TSubclassOf<AAIController> GetDefaultAIControllerClass() const
	{
		return AAIController::StaticClass();
	}
};
'''
    fixture3_path.write_text(fixture3_source, encoding="utf-8")
    print(f"Injected fixture 3: {fixture3_path}")


if __name__ == "__main__":
    main()
