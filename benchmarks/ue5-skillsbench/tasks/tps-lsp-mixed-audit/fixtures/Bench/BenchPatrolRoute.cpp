#include "BenchPatrolRoute.h"

#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

void ABenchPatrolRoute::ApplyCrouchSpeed(ACharacter* Patroller, float Speed) const
{
	if (Patroller == nullptr)
	{
		return;
	}

	Patroller->GetCharacterMovement()->MaxWalkSpeedCrouching = Speed;
}
