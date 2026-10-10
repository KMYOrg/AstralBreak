#include "AstralDodgeTypes.h"

#include "Combat/AstralFacingTypes.h"

namespace AstralDodge
{
	FVector ResolveDirection(const FAstralDodgeDirectionInput& Input)
	{
		// 1. 이동 입력 — 기존 규칙 그대로
		FVector Direction = Input.HorizontalInput;
		Direction.Z = 0.f;
		if (Direction.Normalize())
		{
			return Direction;
		}

		// 2. 무입력 + 락온 — 타겟 반대로 "물러난다" (캐릭터가 타겟을 안 보고 있어도 성립)
		if (Input.bHasLockTarget)
		{
			FVector Away = Input.AvatarLocation - Input.TargetLocation;
			Away.Z = 0.f;
			if (Away.Normalize())
			{
				return Away;
			}
			// 수평 겹침 — 기존 규칙으로 폴백
		}

		// 3. 기존 백스텝/전방
		FVector Forward = Input.AvatarForward;
		Forward.Z = 0.f;
		if (!Forward.Normalize())
		{
			Forward = FVector::ForwardVector;
		}
		return Input.bBackstepWhenIdle ? -Forward : Forward;
	}
}

//////////////////////////////////////////////////////////////////////////
// FAstralDodgeActivationData

FVector FAstralDodgeActivationData::GetDirection() const
{
	return FRotator(0.f, AstralFacing::DequantizeYaw(QuantizedYaw), 0.f).Vector().GetSafeNormal2D();
}

//////////////////////////////////////////////////////////////////////////
// FGameplayAbilityTargetData_AstralDodge

FString FGameplayAbilityTargetData_AstralDodge::ToString() const
{
	return FString::Printf(TEXT("AstralDodge(Yaw=%u)"), Data.QuantizedYaw);
}

bool FGameplayAbilityTargetData_AstralDodge::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	Ar << Data.QuantizedYaw;
	bOutSuccess = true;
	return true;
}

bool FGameplayAbilityTargetData_AstralDodge::Extract(const FGameplayAbilityTargetDataHandle& Handle, FAstralDodgeActivationData& OutData)
{
	if (Handle.Num() != 1)
	{
		return false;
	}

	const FGameplayAbilityTargetData* Payload = Handle.Get(0);
	if (!Payload || Payload->GetScriptStruct() != FGameplayAbilityTargetData_AstralDodge::StaticStruct())
	{
		return false;
	}

	OutData = static_cast<const FGameplayAbilityTargetData_AstralDodge*>(Payload)->Data;
	return true;
}

FGameplayAbilityTargetDataHandle FGameplayAbilityTargetData_AstralDodge::MakeHandle(const FAstralDodgeActivationData& Data)
{
	FGameplayAbilityTargetDataHandle Handle;
	Handle.Add(new FGameplayAbilityTargetData_AstralDodge(Data));
	return Handle;
}
