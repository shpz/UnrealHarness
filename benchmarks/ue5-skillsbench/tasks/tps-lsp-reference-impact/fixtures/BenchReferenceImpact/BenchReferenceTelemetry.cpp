#include "BenchReferenceTelemetry.h"

void FBenchReferenceTelemetry::RouteEvent(const FName& EventName)
{
	(void)EventName;
}

void BenchSendTelemetry(FBenchReferenceTelemetry& Telemetry, const FName& EventName)
{
	Telemetry.RouteEvent(EventName);
}
