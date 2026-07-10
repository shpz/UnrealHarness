#include "BenchSignalRelay.h"

FBenchSignalRelay::FBenchSignalRelay()
{
	Handlers = { &FBenchSignalRelay::Boost, &FBenchSignalRelay::Dampen, &FBenchSignalRelay::Fold };
}

float FBenchSignalRelay::Dispatch(int32 Channel, float Value) const
{
	const FHandlerFn Handler = Handlers[((Channel % 3) + 3) % 3];
	return (this->*Handler)(Value);
}
