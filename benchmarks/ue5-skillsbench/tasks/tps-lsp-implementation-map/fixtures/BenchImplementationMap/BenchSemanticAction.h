#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "BenchSemanticAction.generated.h"

UINTERFACE(MinimalAPI, NotBlueprintable)
class UBenchSemanticAction : public UInterface
{
	GENERATED_BODY()
};

class IBenchSemanticAction
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category="SkillsBench|SemanticAction")
	virtual void ExecuteAction(const FName& ActionName) = 0;
};
