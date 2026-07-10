#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "BenchScoreTracker.generated.h"

/** Accumulates a clamped score value for the bench arena. */
UCLASS()
class UBenchScoreTracker : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category="Bench")
	void AddScore(int32 Amount);

	UFUNCTION(BlueprintPure, Category="Bench")
	int32 GetScore() const { return Score; }

private:
	UPROPERTY()
	int32 Score = 0;
};
