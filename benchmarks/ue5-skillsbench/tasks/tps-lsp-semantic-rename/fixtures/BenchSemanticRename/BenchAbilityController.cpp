#include "BenchAbilityController.h"
#include "BenchAbilityRouter.h"

bool ABenchAbilityController::ForwardAbility(UBenchAbilityRouter& Router, const FName& AbilityName) const
{
	return Router.TriggerAbility(AbilityName);
}
