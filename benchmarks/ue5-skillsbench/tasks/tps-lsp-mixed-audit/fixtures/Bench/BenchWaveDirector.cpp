#include "BenchWaveDirector.h"

#include "Net/UnrealNetwork.h"

ABenchWaveDirector::ABenchWaveDirector()
{
	bReplicates = true;
}

void ABenchWaveDirector::AdvanceWave()
{
	if (Waves.IsValidIndex(CurrentWave + 1))
	{
		++CurrentWave;
		const FBenchWaveSpec& Spec = Waves[CurrentWave];
		OnWaveChanged.Broadcast(CurrentWave, Spec.EnemyCount * Spec.SpawnInterval);
	}
}

void ABenchWaveDirector::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ABenchWaveDirector, CurrentWave);
}
