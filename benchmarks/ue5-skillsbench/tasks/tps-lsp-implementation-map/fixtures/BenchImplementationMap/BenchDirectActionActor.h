#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BenchSemanticAction.h"
#include "BenchDirectActionActor.generated.h"

UCLASS()
class TPSAMPLE_API ABenchDirectActionActor : public AActor, public IBenchSemanticAction
{
	GENERATED_BODY()

public:
	virtual void ExecuteAction(const FName& ActionName) override;
};
