#pragma once

#include "CoreMinimal.h"
#include "BenchSharedActionActor.h"
#include "BenchOverrideActionActor.generated.h"

UCLASS()
class TPSAMPLE_API ABenchOverrideActionActor : public ABenchSharedActionActor
{
	GENERATED_BODY()

public:
	virtual void ExecuteAction(const FName& ActionName) override;
};
