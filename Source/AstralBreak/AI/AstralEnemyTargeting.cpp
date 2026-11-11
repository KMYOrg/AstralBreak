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

	int32 SelectWeightedIndex(TConstArrayView<float> Weights, float Roll)
	{
		double Total = 0.0;
		for (const float Weight : Weights)
		{
			Total += FMath::Max(Weight, 0.f);
		}
		if (Total <= 0.0)
		{
			return INDEX_NONE;
		}

		const double Threshold = FMath::Clamp(static_cast<double>(Roll), 0.0, 1.0) * Total;

		int32 LastPositiveIndex = INDEX_NONE;
		double Accumulated = 0.0;
		for (int32 Index = 0; Index < Weights.Num(); ++Index)
		{
			if (Weights[Index] <= 0.f)
			{
				continue;
			}

			LastPositiveIndex = Index;
			Accumulated += Weights[Index];
			if (Threshold < Accumulated)
			{
				return Index;
			}
		}

		// Roll 1 · 부동소수 오차 — 뽑힐 수 있는 마지막 칸
		return LastPositiveIndex;
	}

	float ComputeThreatWeight(float Hostility, float DamageWeight, float DamageShare)
	{
		return FMath::Max(Hostility, 0.f) * (1.f + FMath::Max(DamageWeight, 0.f) * FMath::Clamp(DamageShare, 0.f, 1.f));
	}

	bool IsWithinDuration(double StartTime, double Now, double Duration)
	{
		return StartTime >= 0.0 && (Now - StartTime) < Duration;
	}

	float SumDamageInWindow(TConstArrayView<FAstralEnemyDamageEntry> Entries, double Now, double Window)
	{
		float Sum = 0.f;
		for (const FAstralEnemyDamageEntry& Entry : Entries)
		{
			if (IsWithinDuration(Entry.Time, Now, Window))
			{
				Sum += FMath::Max(Entry.Damage, 0.f);
			}
		}
		return Sum;
	}

	bool IsThreatEligible(const FAstralEnemyThreatCandidate& Candidate)
	{
		return !Candidate.bDeadOrDying && !Candidate.bExcluded && Candidate.Hostility > 0.f;
	}

	int32 SelectThreatIndex(const FVector& Origin, TConstArrayView<FAstralEnemyThreatCandidate> Candidates, float DamageWeight, float Roll)
	{
		float TotalDamage = 0.f;
		for (const FAstralEnemyThreatCandidate& Candidate : Candidates)
		{
			if (IsThreatEligible(Candidate))
			{
				TotalDamage += FMath::Max(Candidate.RecentDamage, 0.f);
			}
		}

		// 아무도 안 때렸다 — 추첨하지 않고 가장 가까운 후보. 자격 없는 후보는 '죽은 후보' 자리에 실어 단위 A 의 함수를 그대로 쓴다
		if (TotalDamage <= 0.f)
		{
			TArray<FAstralEnemyTargetCandidate, TInlineAllocator<8>> NearestCandidates;
			NearestCandidates.Reserve(Candidates.Num());
			for (const FAstralEnemyThreatCandidate& Candidate : Candidates)
			{
				FAstralEnemyTargetCandidate& NearestCandidate = NearestCandidates.AddDefaulted_GetRef();
				NearestCandidate.Location = Candidate.Location;
				NearestCandidate.bDeadOrDying = !IsThreatEligible(Candidate);
			}
			return SelectNearestIndex(Origin, NearestCandidates);
		}

		TArray<float, TInlineAllocator<8>> Weights;
		Weights.Reserve(Candidates.Num());
		for (const FAstralEnemyThreatCandidate& Candidate : Candidates)
		{
			Weights.Add(IsThreatEligible(Candidate)
				? ComputeThreatWeight(Candidate.Hostility, DamageWeight, FMath::Max(Candidate.RecentDamage, 0.f) / TotalDamage)
				: 0.f);
		}
		return SelectWeightedIndex(Weights, Roll);
	}
}
