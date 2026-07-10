#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BenchAimSolver.generated.h"

/** Scores how well this actor is aimed at a target. */
UCLASS()
class ABenchAimSolver : public AActor
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category="Bench")
	float ScoreTarget(AActor* Target) const;
};
