#include "BenchAbilityConsumer.h"
#include "BenchAbilityRouter.h"

bool UBenchAbilityConsumer::RequestAbility(UBenchAbilityRouter* Router, const FName& AbilityName) const
{
	return Router != nullptr && Router->TriggerAbility(AbilityName);
}
