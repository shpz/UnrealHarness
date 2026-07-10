#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BenchWaveDirector.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FBenchWaveChanged, int32, WaveIndex, float, Intensity);

USTRUCT(BlueprintType)
struct FBenchWaveSpec
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Bench")
	int32 EnemyCount = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Bench", meta=(ClampMin="0.0"))
	float SpawnInterval = 1.f;
};

/** Drives enemy wave progression and broadcasts wave changes. */
UCLASS(Blueprintable)
class ABenchWaveDirector : public AActor
{
	GENERATED_BODY()

public:
	ABenchWaveDirector();

	UPROPERTY(BlueprintAssignable, Category="Bench")
	FBenchWaveChanged OnWaveChanged;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Bench")
	TArray<FBenchWaveSpec> Waves;

	UPROPERTY(EditAnywhere, Category="Bench", Replicated)
	int32 CurrentWave = INDEX_NONE;

	UFUNCTION(BlueprintCallable, Category="Bench")
	void AdvanceWave();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
};
