#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BenchAbilityController.generated.h"

class UBenchAbilityRouter;

UCLASS()
class TPSAMPLE_API ABenchAbilityController : public AActor
{
	GENERATED_BODY()

public:
	bool ForwardAbility(UBenchAbilityRouter& Router, const FName& AbilityName) const;
};
