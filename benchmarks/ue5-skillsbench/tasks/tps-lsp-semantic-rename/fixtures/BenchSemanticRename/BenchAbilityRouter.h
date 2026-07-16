#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "BenchAbilityRouter.generated.h"

UCLASS(ClassGroup=(SkillsBench), meta=(BlueprintSpawnableComponent))
class TPSAMPLE_API UBenchAbilityRouter : public UActorComponent
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category="SkillsBench|Ability")
	bool TriggerAbility(const FName& AbilityName);
};
