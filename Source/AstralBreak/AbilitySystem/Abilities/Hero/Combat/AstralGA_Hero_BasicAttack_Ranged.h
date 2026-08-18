#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_BasicAttack_Ranged.generated.h"

class AAstralRangedWeaponActor;
class UAnimMontage;

/**
 * 원거리 기본 공격 공통 베이스 — 발사 방식 무관 부분만 소유:
 * Ranged 모드 게이트·상호배타 정책, 커밋→발사→몽타주 흐름, 화면 중앙(카메라) 레이 조준 해석.
 * 발사 방식(투사체/히트스캔/...)은 ExecuteRangedAttack 훅의 파생이 구현하고,
 * 어느 파생이 부여되는지는 무기 계열의 AbilitySet(데이터)이 결정한다 — 입력은 공통(InputTag.Attack.Basic).
 * 조준: 카메라 레이 위 총구 투영 지점부터 사거리까지 트레이스 (원격 PC 카메라 POV는 ServerUpdateCamera 보고값).
 */
UCLASS(Abstract)
class ASTRALBREAK_API UAstralGA_Hero_BasicAttack_Ranged : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_BasicAttack_Ranged(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	/** 서버 — 발사 방식 훅. 파생이 구현 (투사체 스폰 / 히트스캔 판정 / ...) */
	virtual void ExecuteRangedAttack() {}

	/** 장착 중인 원거리 무기 (SourceObject 경유) — 원거리 무기가 아니면 null */
	AAstralRangedWeaponActor* GetRangedWeaponActor() const;

	/**
	 * 화면 중앙(카메라) 레이 조준 해석 (서버) — OutMuzzle→OutTargetPoint가 발사선.
	 * 조준점이 총구 뒤(극근접 지형 등)면 카메라 레이 방향의 원거리 지점으로 보정해 전방을 보장.
	 * 컨트롤러 부재 등 해석 불가 시 false
	 */
	bool ComputeAimTarget(const AAstralRangedWeaponActor* WeaponActor, FVector& OutMuzzleLocation, FVector& OutTargetPoint) const;

	UFUNCTION()
	void OnMontageFinished();

protected:
	/** 발사 모션 (플레이스홀더 가능 — 미지정이면 즉발 종료) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged")
	TObjectPtr<UAnimMontage> FireMontage;

	/** 명중 데미지 (Damage GE는 GameData 전역, SetByCaller.Damage 주입) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged")
	float BaseDamage = 15.f;

	/** 명중 시 표식 수급 — 기획상 표식의 주 축적원 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged", Meta = (ClampMin = "0.0"))
	float MarkGainOnHit = 10.f;

	/** 조준점 확정 트레이스 사거리 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged")
	float AimTraceRange = 10000.f;
};
