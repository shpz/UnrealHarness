#include "BenchReferenceRouter.h"

void BenchRouteNamedEvent(UBenchReferenceRouter* Router, const FName& EventName)
{
	if (Router != nullptr)
	{
		Router->RouteEvent(EventName);
	}
}

void BenchRouteNumericEvent(UBenchReferenceRouter& Router)
{
	Router.RouteEvent(17);
}
