#include "AstralAimCorrection.h"

namespace
{
	/**
	 * 전체 보정을 가중치대로 나눠 체인에 적용 — 뿌리부터, 각 본은 앞 본들이 옮겨 놓은 자기 피벗을 축 중심으로 돈다.
	 * 반환 = 그 결과 무기 본 트랜스폼(체인 끝까지의 강체 이동을 그대로 받는다). OutPivot = 체인 피벗의 가중 평균(유효 회전 중심)
	 */
	FTransform ApplyCorrection(const FAstralAimCorrectionInput& In, const FQuat& Correction, float WeightSum, TArray<FTransform, TInlineAllocator<4>>& OutChain, FVector& OutPivot)
	{
		FVector Axis;
		float Angle;
		Correction.ToAxisAndAngle(Axis, Angle);

		// 앞 본들의 회전이 자손에 준 강체 이동 (UE 곱 순서: X' = X * Carried)
		FTransform Carried = FTransform::Identity;
		OutChain.Reset();
		OutPivot = FVector::ZeroVector;
		for (int32 Index = 0; Index < In.Chain.Num(); ++Index)
		{
			const FTransform Moved = In.Chain[Index] * Carried;
			const float Share = FMath::Max(In.Weights[Index], 0.f) / WeightSum;
			const FVector Pivot = Moved.GetLocation();
			OutPivot += Pivot * Share;

			// 자기 피벗 기준 회전: 피벗을 원점으로 → 회전 → 되돌림. 본 위치는 그대로, 회전만 앞에 곱해진다
			const FTransform Spin = FTransform(-Pivot) * FTransform(FQuat(Axis, Angle * Share)) * FTransform(Pivot);
			OutChain.Add(Moved * Spin);
			Carried = Carried * Spin;
		}
		return In.WeaponBone * Carried;
	}

	/**
	 * 현재 총열 오차(도)와 다음 보정 회전. 회전 중심이 Pivot 하나라고 보고 정확히 푼다 — 총구가 피벗을 따라 움직이는 것(시차)까지:
	 * 회전 R 뒤 총열 직선이 조준점 T 를 지나려면, 되돌린 조준점 R⁻¹(T−P) 가 지금 총열 직선 (M−P) + s·b 위에 있어야 하고 |R⁻¹(T−P)| = |T−P| 다.
	 * → s² + 2s(m·b) + |m|² − D² = 0 의 양의 근으로 그 점 u 를 찾고 R = u → T−P 최소 회전. 피벗이 본마다 달라 남는 작은 잔차는 반복이 정리한다.
	 * 조준점이 총구와 겹치면 false
	 */
	bool MeasureCorrection(const FAstralAimCorrectionInput& In, const FTransform& WeaponBone, const FVector& Pivot, FQuat& OutDelta, float& OutErrorDegrees)
	{
		const FTransform Muzzle = In.MuzzleInWeaponBone * WeaponBone;
		const FVector Barrel = Muzzle.GetUnitAxis(EAxis::X);
		const FVector ToTarget = In.Target - Muzzle.GetLocation();
		if (ToTarget.IsNearlyZero())
		{
			return false;
		}
		OutErrorDegrees = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Barrel, ToTarget.GetUnsafeNormal()), -1.f, 1.f)));

		const FVector M = Muzzle.GetLocation() - Pivot;
		const FVector TargetFromPivot = In.Target - Pivot;
		const double MB = FVector::DotProduct(M, Barrel);
		const double Disc = MB * MB - M.SizeSquared() + TargetFromPivot.SizeSquared();
		if (Disc < 0.0)
		{
			// 조준점이 피벗에 너무 가까워 총열 직선이 닿지 않는다 — 방향만 맞춘다
			OutDelta = FQuat::FindBetweenNormals(Barrel, ToTarget.GetUnsafeNormal());
			return true;
		}
		const FVector OnBarrelLine = M + Barrel * (-MB + FMath::Sqrt(Disc));
		OutDelta = FQuat::FindBetweenVectors(OnBarrelLine, TargetFromPivot);
		return true;
	}
}

FAstralAimCorrectionResult AstralAimCorrection::Solve(const FAstralAimCorrectionInput& In)
{
	FAstralAimCorrectionResult Out;
	if (In.Chain.Num() == 0 || In.Chain.Num() != In.Weights.Num())
	{
		return Out;
	}

	float WeightSum = 0.f;
	for (const float Weight : In.Weights)
	{
		WeightSum += FMath::Max(Weight, 0.f);
	}
	if (WeightSum <= KINDA_SMALL_NUMBER)
	{
		return Out;
	}

	FVector Pivot;
	FQuat Delta;
	float Error;
	FTransform WeaponBone = ApplyCorrection(In, FQuat::Identity, WeightSum, Out.Chain, Pivot);
	if (!MeasureCorrection(In, WeaponBone, Pivot, Delta, Error))
	{
		return Out;
	}
	Out.InitialErrorDegrees = Error;

	const float MaxAngle = FMath::DegreesToRadians(FMath::Max(In.MaxAngleDegrees, 0.f));
	FQuat Correction = FQuat::Identity;
	for (int32 Iteration = 0; Iteration < FMath::Max(In.Iterations, 1); ++Iteration)
	{
		if (Error < 0.001f)
		{
			break;
		}

		Correction = Delta * Correction;
		Correction.Normalize();
		if (Correction.W < 0.f)
		{
			Correction = -Correction;   // 같은 회전의 짧은 표현(각 ≤ 180)
		}

		// 최대각 제한 — 축은 유지하고 각만 자른다
		FVector Axis;
		float Angle;
		Correction.ToAxisAndAngle(Axis, Angle);
		if (Angle > MaxAngle)
		{
			Correction = FQuat(Axis, MaxAngle);
		}

		WeaponBone = ApplyCorrection(In, Correction, WeightSum, Out.Chain, Pivot);
		if (!MeasureCorrection(In, WeaponBone, Pivot, Delta, Error))
		{
			Error = 0.f;
			break;
		}
	}

	Out.Correction = Correction;
	Out.ResidualErrorDegrees = Error;
	Out.bValid = true;
	return Out;
}
