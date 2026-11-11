#include "AstralEnemyTargeting.h"

namespace AstralEnemyTargeting
{
	int32 SelectNearestIndex(const FVector& Origin, TConstArrayView<FAstralEnemyTargetCandidate> Candidates)
	{
		int32 NearestIndex = INDEX_NONE;
		double NearestDistSq = 0.0;

		for (int32 Index = 0; Index < Candidates.Num(); ++Index)
		{
			const FAstralEnemyTargetCandidate& Candidate = Candidates[Index];
			if (Candidate.bDeadOrDying)
			{
				continue;
			}

			// 동률은 앞쪽 유지(<) — 결과가 배열 순서 밖의 것에 기대지 않게 한다
			const double DistSq = FVector::DistSquared(Origin, Candidate.Location);
			if (NearestIndex == INDEX_NONE || DistSq < NearestDistSq)
			{
				NearestIndex = Index;
				NearestDistSq = DistSq;
			}
		}

		return NearestIndex;
	}
}
