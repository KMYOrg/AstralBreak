#include "AstralTargetingStatics.h"

namespace AstralTargeting
{
	float ComputeYawDeg(const FVector& ViewLocation, float ViewYaw, const FVector& TargetLocation)
	{
		const FVector ToTarget2D = (TargetLocation - ViewLocation).GetSafeNormal2D();
		if (ToTarget2D.IsNearlyZero())
		{
			return 0.f;
		}

		const float TargetYaw = ToTarget2D.Rotation().Yaw;
		return FMath::FindDeltaAngleDegrees(ViewYaw, TargetYaw);
	}

	bool PassesAcquireFilter(float Distance, float YawDeg, const FAstralTargetingParams& Params)
	{
		// 오버랩 스피어는 캡슐 가장자리에 닿는 후보까지 돌려주므로 중심 거리로 한 번 더 자른다
		if (Distance > Params.AcquireRange)
		{
			return false;
		}

		return FMath::Abs(YawDeg) <= Params.MaxAcquireYaw;
	}

	float ScoreCandidate(float Distance, float YawDeg, bool bIsCurrentTarget, const FAstralTargetingParams& Params)
	{
		const float ScreenCenterScore = (Params.MaxAcquireYaw > 0.f)
			? 1.f - FMath::Clamp(FMath::Abs(YawDeg) / Params.MaxAcquireYaw, 0.f, 1.f)
			: 1.f;

		const float DistanceScore = (Params.AcquireRange > 0.f)
			? 1.f - FMath::Clamp(Distance / Params.AcquireRange, 0.f, 1.f)
			: 1.f;

		float Score = ScreenCenterScore * Params.ScreenWeight + DistanceScore * Params.DistanceWeight;
		if (bIsCurrentTarget)
		{
			Score += Params.CurrentTargetBonus;
		}
		return Score;
	}

	int32 SelectBestCandidate(const TArray<FAstralTargetCandidate>& Candidates, int32 CurrentIndex, const FAstralTargetingParams& Params)
	{
		int32 BestIndex = INDEX_NONE;
		float BestScore = TNumericLimits<float>::Lowest();

		for (int32 Index = 0; Index < Candidates.Num(); ++Index)
		{
			if (Candidates[Index].Score > BestScore)
			{
				BestScore = Candidates[Index].Score;
				BestIndex = Index;
			}
		}

		if (BestIndex == INDEX_NONE)
		{
			return INDEX_NONE;
		}

		// 선정 축 히스테리시스 — 현재 타겟이 있으면 임계를 넘는 후보만 교체 (인접한 두 적 사이의 흔들림 방지)
		if (Candidates.IsValidIndex(CurrentIndex) && BestIndex != CurrentIndex)
		{
			if (BestScore <= Candidates[CurrentIndex].Score + Params.RetargetThreshold)
			{
				return CurrentIndex;
			}
		}

		return BestIndex;
	}

	int32 SelectCycleCandidate(const TArray<FAstralTargetCandidate>& Candidates, float CurrentYawDeg, float Direction)
	{
		if (FMath::IsNearlyZero(Direction))
		{
			return INDEX_NONE;
		}
		const float DirectionSign = FMath::Sign(Direction);

		int32 BestIndex = INDEX_NONE;
		float BestAbsStep = TNumericLimits<float>::Max();

		for (int32 Index = 0; Index < Candidates.Num(); ++Index)
		{
			const FAstralTargetCandidate& Candidate = Candidates[Index];
			if (Candidate.bIsCurrentTarget)
			{
				continue;
			}

			// 최단 부호각 — ±180 래핑에서 단순 뺄셈은 방향이 뒤집힌다
			const float Step = FMath::FindDeltaAngleDegrees(CurrentYawDeg, Candidate.YawDeg);
			if (Step * DirectionSign <= 0.f)
			{
				continue;
			}

			const float AbsStep = FMath::Abs(Step);
			if (BestIndex == INDEX_NONE)
			{
				BestIndex = Index;
				BestAbsStep = AbsStep;
				continue;
			}

			const float Diff = AbsStep - BestAbsStep;
			if (Diff < -CycleAngleTolerance)
			{
				BestIndex = Index;
				BestAbsStep = AbsStep;
			}
			else if (Diff <= CycleAngleTolerance)
			{
				// 각도 동률 — 입력 배열 순서에 의존하지 않도록 Score → Distance로 결정
				const FAstralTargetCandidate& Best = Candidates[BestIndex];
				const bool bBetterScore = Candidate.Score > Best.Score + KINDA_SMALL_NUMBER;
				const bool bSameScore = FMath::IsNearlyEqual(Candidate.Score, Best.Score);
				if (bBetterScore || (bSameScore && Candidate.Distance < Best.Distance))
				{
					BestIndex = Index;
					BestAbsStep = AbsStep;
				}
			}
		}

		return BestIndex;
	}
}
