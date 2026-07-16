#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "BenchReferenceRouter.generated.h"

UCLASS()
class TPSAMPLE_API UBenchReferenceRouter : public UObject
{
	GENERATED_BODY()

public:
	void RouteEvent(const FName& EventName);
	void RouteEvent(int32 EventCode);
};
