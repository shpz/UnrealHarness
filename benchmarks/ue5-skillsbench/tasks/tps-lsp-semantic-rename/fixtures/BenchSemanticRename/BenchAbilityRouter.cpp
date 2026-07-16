#include "BenchAbilityRouter.h"

bool UBenchAbilityRouter::TriggerAbility(const FName& AbilityName)
{
	return !AbilityName.IsNone();
}
