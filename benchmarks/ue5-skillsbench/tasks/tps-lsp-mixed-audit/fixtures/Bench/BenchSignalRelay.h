#pragma once

#include "CoreMinimal.h"

/** Routes a signal value through one of several handler channels. */
class FBenchSignalRelay
{
public:
	using FHandlerFn = float (FBenchSignalRelay::*)(float) const;

	FBenchSignalRelay();

	float Dispatch(int32 Channel, float Value) const;

	float Boost(float Value) const { return Value * BoostFactor; }
	float Dampen(float Value) const { return Value / (BoostFactor + UE_KINDA_SMALL_NUMBER); }
	float Fold(float Value) const { return (Value < 0.f) ? -Value : +Value; }

private:
	TArray<FHandlerFn, TInlineAllocator<3>> Handlers;
	float BoostFactor = 2.f;
};
