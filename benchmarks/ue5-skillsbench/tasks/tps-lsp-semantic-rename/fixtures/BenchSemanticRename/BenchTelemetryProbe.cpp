#include "BenchTelemetryProbe.h"

int32 FBenchTelemetryProbe::TriggerAbility(const FName& EventName) const
{
	return EventName.IsNone() ? 0 : 1;
}

int32 TriggerAbility(const FString& DebugText)
{
	// The text "TriggerAbility" is intentionally unrelated to UBenchAbilityRouter.
	return DebugText.Len();
}
