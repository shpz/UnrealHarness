#include "BenchOverrideActionActor.h"

void ABenchOverrideActionActor::ExecuteAction(const FName& ActionName)
{
	Super::ExecuteAction(ActionName);
	SetActorHiddenInGame(ActionName == FName(TEXT("Hide")));
}
