#include "AstralRangedAttackTypes.h"

#include "GameFramework/Actor.h"

namespace AstralRangedAttack
{
	EAstralFireAssistResult CheckFireAssist(float Distance2D, float BodyYaw, float BearingYaw, const FAstralFireAssistParams& Params)
	{
		if (Distance2D > Params.MaxRange)
		{
			return EAstralFireAssistResult::OutOfRange;
		}

		// 접촉 거리에서는 방위가 프레임마다 크게 흔들린다 — 각도 검사 생략
		if (Distance2D >= Params.MinDistanceForYawCheck)
		{
			const float Error = FMath::Abs(FMath::FindDeltaAngleDegrees(BodyYaw, BearingYaw));
			if (Error > Params.MaxAssistYaw)
			{
				return EAstralFireAssistResult::OutOfAssistYaw;
			}
		}

		return EAstralFireAssistResult::Ok;
	}

	const TCHAR* ToString(EAstralFireAssistResult Value)
	{
		switch (Value)
		{
		case EAstralFireAssistResult::Ok:             return TEXT("Ok");
		case EAstralFireAssistResult::OutOfRange:     return TEXT("OutOfRange");
		case EAstralFireAssistResult::OutOfAssistYaw: return TEXT("OutOfAssistYaw");
		}
		return TEXT("?");
	}

	FAstralReportedAimCheck CheckReportedAimDirection(const FVector& Reported, const FVector& Reference, float MaxDivergenceDeg)
	{
		FAstralReportedAimCheck Check;
		const FVector Ref = Reference.ContainsNaN() ? FVector::ZeroVector : Reference.GetSafeNormal();
		const FVector Rep = Reported.ContainsNaN() ? FVector::ZeroVector : Reported.GetSafeNormal();

		if (Rep.IsZero())
		{
			Check.Result = EAstralReportedAimResult::Rejected;
			Check.Direction = Ref.IsZero() ? FVector::ForwardVector : Ref;
			return Check;
		}

		// 기준이 없으면(컨트롤 회전 해석 불가) 비교할 근거가 없다 — 보고 그대로
		if (Ref.IsZero())
		{
			Check.Result = EAstralReportedAimResult::Accepted;
			Check.Direction = Rep;
			return Check;
		}

		const double MaxDeg = FMath::Clamp<double>(MaxDivergenceDeg, 0.0, 180.0);
		const double Divergence = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Rep, Ref), -1.0, 1.0)));
		Check.Divergence = static_cast<float>(Divergence);
		if (Divergence <= MaxDeg)
		{
			Check.Result = EAstralReportedAimResult::Accepted;
			Check.Direction = Rep;
			return Check;
		}

		// 회전축 = 기준 × 보고 (양의 각으로 돌리면 보고 쪽으로 간다). 정반대(외적 0)면 기준에 수직인 아무 축 — 위쪽 기준, 기준이 수직이면 전방 기준
		FVector Axis = FVector::CrossProduct(Ref, Rep);
		if (!Axis.Normalize())
		{
			Axis = FVector::CrossProduct(Ref, FVector::UpVector);
			if (!Axis.Normalize())
			{
				Axis = FVector::CrossProduct(Ref, FVector::ForwardVector);
				Axis.Normalize();
			}
		}

		Check.Result = EAstralReportedAimResult::Clamped;
		Check.Direction = FQuat(Axis, FMath::DegreesToRadians(MaxDeg)).RotateVector(Ref).GetSafeNormal();
		return Check;
	}

	FVector ClampReportedAimPoint(const FVector& AimPoint, const FVector& Direction, const FVector& MuzzleLocation, float TraceRange)
	{
		const FVector Dir = Direction.GetSafeNormal();
		const FVector ToPoint = AimPoint - MuzzleLocation;

		// 총구 뒤·옆(클라 총구와의 차이로 극근접 지형이 뒤가 된 경우 등) — 전방 보장
		if (AimPoint.ContainsNaN() || FVector::DotProduct(ToPoint.GetSafeNormal(), Dir) <= 0.0)
		{
			return MuzzleLocation + Dir * TraceRange;
		}

		// 클라 조준점은 자기 총구 투영점에서 사거리 안 — 서버 총구와의 차를 넉넉히 봐도 1.1배 밖은 비정상
		if (ToPoint.SizeSquared() > FMath::Square(TraceRange * 1.1))
		{
			return MuzzleLocation + ToPoint.GetSafeNormal() * TraceRange;
		}
		return AimPoint;
	}

	const TCHAR* ToString(EAstralReportedAimResult Value)
	{
		switch (Value)
		{
		case EAstralReportedAimResult::Accepted: return TEXT("Accepted");
		case EAstralReportedAimResult::Clamped:  return TEXT("Clamped");
		case EAstralReportedAimResult::Rejected: return TEXT("Rejected");
		}
		return TEXT("?");
	}
}

bool FAstralRangedActivationData::operator==(const FAstralRangedActivationData& Other) const
{
	return BodyFacing == Other.BodyFacing
		&& FallbackAimPoint.Equals(Other.FallbackAimPoint, KINDA_SMALL_NUMBER);
}

TArray<TWeakObjectPtr<AActor>> FGameplayAbilityTargetData_AstralRangedActivation::GetActors() const
{
	TArray<TWeakObjectPtr<AActor>> Actors;
	if (Data.BodyFacing.TargetActor.IsValid())
	{
		Actors.Add(Data.BodyFacing.TargetActor);
	}
	return Actors;
}

FString FGameplayAbilityTargetData_AstralRangedActivation::ToString() const
{
	return FString::Printf(TEXT("AstralRangedActivation(Source=%s Target=%s BodyYaw=%u FallbackAim=%s)"),
		AstralFacing::ToString(Data.BodyFacing.Source), *GetNameSafe(Data.BodyFacing.TargetActor.Get()),
		Data.BodyFacing.QuantizedDesiredYaw, *Data.FallbackAimPoint.ToString());
}

bool FGameplayAbilityTargetData_AstralRangedActivation::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	Data.BodyFacing.NetSerializeFields(Ar, Map);

	bool bPointSuccess = true;
	Data.FallbackAimPoint.NetSerialize(Ar, Map, bPointSuccess);

	bOutSuccess = bPointSuccess;
	return true;
}

bool FGameplayAbilityTargetData_AstralRangedActivation::Extract(const FGameplayAbilityTargetDataHandle& Handle, FAstralRangedActivationData& OutData)
{
	if (Handle.Num() != 1)
	{
		return false;
	}

	const FGameplayAbilityTargetData* Payload = Handle.Get(0);
	if (!Payload || Payload->GetScriptStruct() != FGameplayAbilityTargetData_AstralRangedActivation::StaticStruct())
	{
		return false;
	}

	FAstralRangedActivationData Data = static_cast<const FGameplayAbilityTargetData_AstralRangedActivation*>(Payload)->Data;

	if (Data.BodyFacing.Source > EAstralFacingSource::LockOn)
	{
		return false;
	}
	// 단발 — 단계는 0뿐
	if (Data.BodyFacing.StageIndex != 0)
	{
		return false;
	}
	// M5 전까지 부위 조준 없음
	if (!Data.BodyFacing.TargetPointId.IsNone())
	{
		return false;
	}
	// 임의 좌표를 신뢰하지 않는다 — 유한성만 (거리 검증은 발사 시점의 월드 판정)
	if (Data.FallbackAimPoint.ContainsNaN())
	{
		return false;
	}

	Data.BodyFacing.NormalizeNone();
	OutData = Data;
	return true;
}

FGameplayAbilityTargetDataHandle FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(const FAstralRangedActivationData& Data)
{
	FGameplayAbilityTargetDataHandle Handle;
	Handle.Add(new FGameplayAbilityTargetData_AstralRangedActivation(Data));
	return Handle;
}

FString FGameplayAbilityTargetData_AstralRangedFire::ToString() const
{
	return FString::Printf(TEXT("AstralRangedFire(AimPoint=%s Direction=%s)"), *Data.AimPoint.ToString(), *Data.AimDirection.ToString());
}

bool FGameplayAbilityTargetData_AstralRangedFire::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	bool bPointSuccess = true;
	Data.AimPoint.NetSerialize(Ar, Map, bPointSuccess);

	bool bDirectionSuccess = true;
	Data.AimDirection.NetSerialize(Ar, Map, bDirectionSuccess);

	bOutSuccess = bPointSuccess && bDirectionSuccess;
	return true;
}

bool FGameplayAbilityTargetData_AstralRangedFire::Extract(const FGameplayAbilityTargetDataHandle& Handle, FAstralRangedFireData& OutData)
{
	if (Handle.Num() != 1)
	{
		return false;
	}

	const FGameplayAbilityTargetData* Payload = Handle.Get(0);
	if (!Payload || Payload->GetScriptStruct() != FGameplayAbilityTargetData_AstralRangedFire::StaticStruct())
	{
		return false;
	}

	const FAstralRangedFireData& Data = static_cast<const FGameplayAbilityTargetData_AstralRangedFire*>(Payload)->Data;

	// 임의 좌표를 신뢰하지 않는다 — 유한성·단위 방향만 (허용각·거리는 발사 시점 서버 판정)
	if (Data.AimPoint.ContainsNaN() || Data.AimDirection.ContainsNaN())
	{
		return false;
	}
	if (!FMath::IsNearlyEqual(Data.AimDirection.Size(), 1.0, 0.01))
	{
		return false;
	}

	OutData = Data;
	return true;
}

FGameplayAbilityTargetDataHandle FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(const FAstralRangedFireData& Data)
{
	FGameplayAbilityTargetDataHandle Handle;
	Handle.Add(new FGameplayAbilityTargetData_AstralRangedFire(Data));
	return Handle;
}
