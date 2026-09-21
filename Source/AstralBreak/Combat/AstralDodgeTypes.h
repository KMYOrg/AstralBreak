#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AstralDodgeTypes.generated.h"

/** ResolveDirection 입력 — 월드 조회는 호출자가 하고 값만 넘긴다 */
struct FAstralDodgeDirectionInput
{
	/** 이동 입력(가속도) — 수평 성분만 본다 */
	FVector HorizontalInput = FVector::ZeroVector;
	bool bHasLockTarget = false;
	FVector AvatarLocation = FVector::ZeroVector;
	FVector TargetLocation = FVector::ZeroVector;
	FVector AvatarForward = FVector::ForwardVector;
	/** 무입력·무락온일 때 백스텝(-Forward)할지 (GA 데이터 bDodgeBackwardWhenIdle) */
	bool bBackstepWhenIdle = true;
};

namespace AstralDodge
{
	/**
	 * 회피 방향 (수평 단위 벡터) — 우선순위:
	 *   1. 수평 이동 입력 있음 → 입력 방향
	 *   2. 무입력 + 유효 락온 → 타겟 반대 방향 (수평 겹침이면 3으로)
	 *   3. 그 외 → 기존 백스텝/전방 규칙
	 */
	ASTRALBREAK_API FVector ResolveDirection(const FAstralDodgeDirectionInput& Input);
}

/** 회피 초기 활성화 데이터 — 최종 Yaw만. 서버는 입력·타겟을 재현해 거부하지 않는다 (구조 검증만) */
USTRUCT()
struct ASTRALBREAK_API FAstralDodgeActivationData
{
	GENERATED_BODY()

	UPROPERTY()
	uint16 QuantizedYaw = 0;

	/** 복원한 수평 단위 방향 */
	FVector GetDirection() const;

	bool operator==(const FAstralDodgeActivationData& Other) const { return QuantizedYaw == Other.QuantizedYaw; }
};

USTRUCT()
struct ASTRALBREAK_API FGameplayAbilityTargetData_AstralDodge : public FGameplayAbilityTargetData
{
	GENERATED_BODY()

	UPROPERTY()
	FAstralDodgeActivationData Data;

	FGameplayAbilityTargetData_AstralDodge() = default;
	explicit FGameplayAbilityTargetData_AstralDodge(const FAstralDodgeActivationData& InData) : Data(InData) {}

	virtual UScriptStruct* GetScriptStruct() const override { return FGameplayAbilityTargetData_AstralDodge::StaticStruct(); }
	virtual FString ToString() const override;

	bool NetSerialize(FArchive& Ar, class UPackageMap* Map, bool& bOutSuccess);

	/** 구조 검증 + 추출 — 페이로드 정확히 1개 · 예상 ScriptStruct */
	static bool Extract(const FGameplayAbilityTargetDataHandle& Handle, FAstralDodgeActivationData& OutData);

	static FGameplayAbilityTargetDataHandle MakeHandle(const FAstralDodgeActivationData& Data);
};

template<>
struct TStructOpsTypeTraits<FGameplayAbilityTargetData_AstralDodge> : public TStructOpsTypeTraitsBase2<FGameplayAbilityTargetData_AstralDodge>
{
	enum
	{
		WithNetSerializer = true,
		WithCopy = true,
	};
};
