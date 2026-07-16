#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BenchActionUtility.generated.h"

UCLASS()
class TPSAMPLE_API ABenchActionUtility : public AActor
{
	GENERATED_BODY()

public:
	// Same spelling and signature, but this class does not implement IBenchSemanticAction.
	void ExecuteAction(const FName& ActionName);
};
