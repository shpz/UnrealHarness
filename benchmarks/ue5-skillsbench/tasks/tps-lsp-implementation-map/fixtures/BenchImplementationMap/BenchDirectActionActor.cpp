#include "BenchDirectActionActor.h"

void ABenchDirectActionActor::ExecuteAction(const FName& ActionName)
{
	SetActorTickEnabled(!ActionName.IsNone());
}
