#include "BenchAimSolver.h"

float ABenchAimSolver::ScoreTarget(AActor* Target) const
{
	if (Target == nullptr)
	{
		return 0.f;
	}

	const FVector Forward = GetActorForwardVector();
	return FVector::DotProduct(Forward, Target->GetActorRotation());
}
