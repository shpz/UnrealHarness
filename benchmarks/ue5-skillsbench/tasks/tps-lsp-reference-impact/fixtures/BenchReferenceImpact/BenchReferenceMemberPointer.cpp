#include "BenchReferenceRouter.h"

using FBenchNamedRouteMethod = void (UBenchReferenceRouter::*)(const FName&);

FBenchNamedRouteMethod BenchGetNamedRouteMethod()
{
	return static_cast<FBenchNamedRouteMethod>(&UBenchReferenceRouter::RouteEvent);
}

void BenchInvokeNamedRouteMethod(UBenchReferenceRouter& Router, const FName& EventName)
{
	const FBenchNamedRouteMethod Method = BenchGetNamedRouteMethod();
	(Router.*Method)(EventName);
}
