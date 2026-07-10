#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BenchPatrolRoute.generated.h"

class ACharacter;

/** Applies patrol movement tuning to a character walking this route. */
UCLASS()
class ABenchPatrolRoute : public AActor
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category="Bench")
	void ApplyCrouchSpeed(ACharacter* Patroller, float Speed) const;
};
