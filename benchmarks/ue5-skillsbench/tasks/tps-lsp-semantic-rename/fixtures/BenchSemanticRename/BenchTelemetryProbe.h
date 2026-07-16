#pragma once

#include "CoreMinimal.h"

class FBenchTelemetryProbe
{
public:
	int32 TriggerAbility(const FName& EventName) const;
};

TPSAMPLE_API int32 TriggerAbility(const FString& DebugText);
