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
