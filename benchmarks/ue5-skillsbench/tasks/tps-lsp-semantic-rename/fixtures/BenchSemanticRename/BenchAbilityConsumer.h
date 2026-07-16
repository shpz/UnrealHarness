#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "BenchAbilityConsumer.generated.h"

class UBenchAbilityRouter;

UCLASS()
class TPSAMPLE_API UBenchAbilityConsumer : public UObject
{
	GENERATED_BODY()

public:
	bool RequestAbility(UBenchAbilityRouter* Router, const FName& AbilityName) const;
};
