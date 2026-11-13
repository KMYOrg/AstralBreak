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
		FAstralEnemyThreatSettings Settings;
		Settings.DamageWeight = DamageWeight;
		return SelectThreatIndex(Origin, Candidates, Settings, Roll);
	}

	float ComputeDistanceFactor(float DistanceWeight, double NearestDistance, double Distance)
	{
		if (DistanceWeight <= 0.f)
		{
			return 1.f;
		}

		// 겹쳐 있으면(거리 0) 가장 가까운 것으로 본다
		const double Closeness = Distance > UE_KINDA_SMALL_NUMBER ? FMath::Clamp(NearestDistance / Distance, 0.0, 1.0) : 1.0;
		return 1.f + DistanceWeight * static_cast<float>(Closeness);
	}

	float ComputeSpreadFactor(float SpreadWeight, int32 NumOtherAttackers)
	{
		return 1.f / (1.f + FMath::Max(SpreadWeight, 0.f) * FMath::Max(NumOtherAttackers, 0));
	}

	int32 SelectThreatIndex(const FVector& Origin, TConstArrayView<FAstralEnemyThreatCandidate> Candidates, const FAstralEnemyThreatSettings& Settings, float Roll)
	{
		const float DamageWeight = Settings.DamageWeight;

		float TotalDamage = 0.f;
		for (const FAstralEnemyThreatCandidate& Candidate : Candidates)
		{
			if (IsThreatEligible(Candidate))
			{
				TotalDamage += FMath::Max(Candidate.RecentDamage, 0.f);
			}
		}

		// 아무도 안 때렸다 — (옵션이 꺼져 있으면) 추첨하지 않고 가장 가까운 후보. 자격 없는 후보는 '죽은 후보' 자리에 실어 단위 A 의 함수를 그대로 쓴다
		if (TotalDamage <= 0.f && !Settings.bDrawWithoutDamage)
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

		// 거리 배수의 기준 — 자격 있는 후보 중 가장 가까운 것까지의 거리
		double NearestDistance = -1.0;
		if (Settings.DistanceWeight > 0.f)
		{
			for (const FAstralEnemyThreatCandidate& Candidate : Candidates)
			{
				if (IsThreatEligible(Candidate))
				{
					const double Distance = FVector::Dist(Origin, Candidate.Location);
					NearestDistance = NearestDistance < 0.0 ? Distance : FMath::Min(NearestDistance, Distance);
				}
			}
		}

		TArray<float, TInlineAllocator<8>> Weights;
		Weights.Reserve(Candidates.Num());
		for (const FAstralEnemyThreatCandidate& Candidate : Candidates)
		{
			if (!IsThreatEligible(Candidate))
			{
				Weights.Add(0.f);
				continue;
			}

			const float DamageShare = TotalDamage > 0.f ? FMath::Max(Candidate.RecentDamage, 0.f) / TotalDamage : 0.f;
			Weights.Add(ComputeThreatWeight(Candidate.Hostility, DamageWeight, DamageShare)
				* ComputeDistanceFactor(Settings.DistanceWeight, NearestDistance, FVector::Dist(Origin, Candidate.Location))
				* ComputeSpreadFactor(Settings.SpreadWeight, Candidate.NumOtherAttackers));
		}
		return SelectWeightedIndex(Weights, Roll);
	}

	float SelectEngageBearing(float PreferredDegrees, TConstArrayView<float> OccupiedDegrees, float MinSeparationDegrees)
	{
		const float Preferred = FRotator::NormalizeAxis(PreferredDegrees);
		const float MinSeparation = FMath::Max(MinSeparationDegrees, 0.f);

		// 정확히 MinSeparation 만큼 떨어진 후보가 부동소수 오차로 떨어지지 않게 한다
		constexpr float Tolerance = 0.01f;
		const auto IsFree = [&OccupiedDegrees, MinSeparation](float Bearing)
		{
			for (const float Occupied : OccupiedDegrees)
			{
				if (FMath::Abs(FMath::FindDeltaAngleDegrees(Occupied, Bearing)) < MinSeparation - Tolerance)
				{
					return false;
				}
			}
			return true;
		};

		if (OccupiedDegrees.Num() == 0 || MinSeparation <= 0.f || IsFree(Preferred))
		{
			return Preferred;
		}

		// 빈 구간의 가장자리 = 잡힌 자리의 ±MinSeparation. 그 가운데 Preferred 에 가장 가까운 것 — 동률은 먼저 본 것 유지(<)
		bool bFound = false;
		float Best = Preferred;
		float BestDelta = 0.f;
		for (const float Occupied : OccupiedDegrees)
		{
			for (const float Sign : { 1.f, -1.f })
			{
				const float Candidate = FRotator::NormalizeAxis(Occupied + Sign * MinSeparation);
				if (!IsFree(Candidate))
				{
					continue;
				}

				const float Delta = FMath::Abs(FMath::FindDeltaAngleDegrees(Preferred, Candidate));
				if (!bFound || Delta < BestDelta - Tolerance)
				{
					bFound = true;
					Best = Candidate;
					BestDelta = Delta;
				}
			}
		}
		if (bFound)
		{
			return Best;
		}

		// 가득 참 — 가장 넓은 틈의 한가운데
		TArray<float, TInlineAllocator<8>> Sorted;
		Sorted.Reserve(OccupiedDegrees.Num());
		for (const float Occupied : OccupiedDegrees)
		{
			Sorted.Add(FRotator::NormalizeAxis(Occupied));
		}
		Sorted.Sort();

		float WidestStart = Sorted.Last();
		float WidestGap = Sorted[0] + 360.f - Sorted.Last();
		for (int32 Index = 0; Index + 1 < Sorted.Num(); ++Index)
		{
			const float Gap = Sorted[Index + 1] - Sorted[Index];
			if (Gap > WidestGap)
			{
				WidestGap = Gap;
				WidestStart = Sorted[Index];
			}
		}
		return FRotator::NormalizeAxis(WidestStart + WidestGap * 0.5f);
	}
}
