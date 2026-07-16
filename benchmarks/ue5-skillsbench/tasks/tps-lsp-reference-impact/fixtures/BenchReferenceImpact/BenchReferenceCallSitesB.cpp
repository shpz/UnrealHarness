#include "BenchReferenceRouter.h"

bool BenchRouteIfNamed(UBenchReferenceRouter& Router, const FName& EventName)
{
	if (!EventName.IsNone())
	{
		Router.RouteEvent(EventName);
		return true;
	}
	return false;
}
