#include "BenchScoreTracker.h"

void UBenchScoreTracker::AddScore(int32 Amount)
{
	Score = FMath::Max(0, Score + Amount);
}
