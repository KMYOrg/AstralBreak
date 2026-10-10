#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "CollisionQueryParams.h"
#include "Combat/AstralFacingTypes.h"
#include "Engine/NetSerialization.h"
#include "AstralRangedAttackTypes.generated.h"

/**
 * 락온 6단계 — 원거리 공격의 초기 활성화 데이터·발사선 계약·순수 판정.
 * 월드 의존이 없는 것(발사 허용각)은 순수 함수로 두어 Automation 테스트로 덮는다.
 */

/** 발사 시점 조준 판정 결과 */
enum class EAstralFireAssistResult : uint8
{
	Ok,
	OutOfRange,
	OutOfAssistYaw,
};

/** 발사 허용 판정 파라미터 — Ranged GA 데이터가 소유 (Facing의 MaxTargetBearingError와 값이 같아도 시점·기준축이 다르다) */
struct FAstralFireAssistParams
{
	/** 고정 타겟까지 허용 거리 (락온 유지 반경 + 여유) */
	float MaxRange = 2200.f;
	/** 발사 순간 몸 전방 대비 타겟 방위 허용각 (도). 초과하면 등 뒤로 꺾지 않고 최초 조준점으로 발사 */
	float MaxAssistYaw = 60.f;
	/** 이 거리 미만이면 각도 검사를 건너뛴다 — 접촉 거리에서 방위가 불안정하다 */
	float MinDistanceForYawCheck = 100.f;
};

namespace AstralRangedAttack
{
	/**
	 * 발사 허용 판정 (순수) — BodyYaw·BearingYaw는 절대 yaw(도). 거리 거부가 각도보다 먼저.
	 * 타겟 유효성·CanDamage는 호출자가 먼저 본다
	 */
	ASTRALBREAK_API EAstralFireAssistResult CheckFireAssist(float Distance2D, float BodyYaw, float BearingYaw, const FAstralFireAssistParams& Params);

	ASTRALBREAK_API const TCHAR* ToString(EAstralFireAssistResult Value);
}

/**
 * 원거리 초기 활성화 데이터 — 입력 활성화 이벤트에 실려 클라·서버가 같은 값을 읽는다.
 *  - BodyFacing: 시작 몸 방향 제안 (Stage 0). Source == LockOn이면 TargetActor가 이 공격의 고정 타겟
 *  - FallbackAimPoint: 공격 시작에 조준한 월드 지점. 타겟 무효·각도 이탈·카메라 해석 실패 시 발사 순간 총구에서 이 점을 향해 쏜다.
 *    방향이 아니라 지점인 이유 — 방향을 총구에서 다시 쓰면 캡처 원점(아바타 중심)과의 오프셋만큼 평행 이동해 근거리 타겟을 비켜 간다
 */
USTRUCT()
struct ASTRALBREAK_API FAstralRangedActivationData
{
	GENERATED_BODY()

	UPROPERTY()
	FAstralFacingProposal BodyFacing;

	/** 1cm 양자화 — 총구 오프셋(수십 cm)보다 충분히 작다 */
	UPROPERTY()
	FVector_NetQuantize FallbackAimPoint = FVector_NetQuantize(ForceInitToZero);

	bool IsLockOn() const { return BodyFacing.Source == EAstralFacingSource::LockOn; }

	bool operator==(const FAstralRangedActivationData& Other) const;
	bool operator!=(const FAstralRangedActivationData& Other) const { return !(*this == Other); }
};

/** GAS TargetData 페이로드 — 활성화 이벤트(TriggerEventData.TargetData) 전용. 후속 송신은 없다 (단발) */
USTRUCT()
struct ASTRALBREAK_API FGameplayAbilityTargetData_AstralRangedActivation : public FGameplayAbilityTargetData
{
	GENERATED_BODY()

	UPROPERTY()
	FAstralRangedActivationData Data;

	FGameplayAbilityTargetData_AstralRangedActivation() = default;
	explicit FGameplayAbilityTargetData_AstralRangedActivation(const FAstralRangedActivationData& InData) : Data(InData) {}

	virtual UScriptStruct* GetScriptStruct() const override { return FGameplayAbilityTargetData_AstralRangedActivation::StaticStruct(); }
	virtual TArray<TWeakObjectPtr<AActor>> GetActors() const override;
	virtual FString ToString() const override;

	bool NetSerialize(FArchive& Ar, class UPackageMap* Map, bool& bOutSuccess);

	/** 구조 검증 + 추출 — 페이로드 정확히 1개 · 예상 ScriptStruct · BodyFacing 단계 0 · TargetPointId == NAME_None · 조준점 유한 */
	static bool Extract(const FGameplayAbilityTargetDataHandle& Handle, FAstralRangedActivationData& OutData);

	static FGameplayAbilityTargetDataHandle MakeHandle(const FAstralRangedActivationData& Data);
};

template<>
struct TStructOpsTypeTraits<FGameplayAbilityTargetData_AstralRangedActivation> : public TStructOpsTypeTraitsBase2<FGameplayAbilityTargetData_AstralRangedActivation>
{
	enum
	{
		WithNetSerializer = true,
		WithCopy = true,
	};
};

/** 확정된 발사선 — Ranged가 한 번 확정하고 무기 실행(Projectile GA 등)이 소비한다. 서버 로컬 값 객체, 네트워크 페이로드가 아니다 */
struct FAstralRangedShot
{
	FVector MuzzleLocation = FVector::ZeroVector;
	/** 유한하고 정규화된 최종 월드 방향 */
	FVector FireDirection = FVector::ForwardVector;
};

/** 총구 여유 검사 형상 — 실제 생성할 투사체와 같은 출처(무기 실행 파생)에서 제공한다 */
struct FAstralMuzzleClearance
{
	float Radius = 0.f;
	/** 투사체 판정이 Block으로 응답하는 오브젝트 타입 (벽·지형) */
	FCollisionObjectQueryParams Blockers;
};
