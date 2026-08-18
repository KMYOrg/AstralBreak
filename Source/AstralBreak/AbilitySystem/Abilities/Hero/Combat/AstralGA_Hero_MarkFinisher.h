#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_MarkFinisher.generated.h"

class AAstralWeaponActor;
class UAnimMontage;
class UAstralAbilityTask_WeaponTrace;

/**
 * 고유 자원 강화 공격 — 표식(MarkStack)을 소비하는 강화 근접 일격.
 * 비용은 표준 CostGameplayEffect 경로(BP에서 GE_Cost_MarkFinisher 지정 — MarkStack -N Instant).
 * 판정은 무기 소켓 연속 트레이스 (몽타주의 WeaponTrace 밴드, BasicAttack과 동일 구조).
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_MarkFinisher : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_MarkFinisher(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	UFUNCTION()
	void OnMontageCompleted();

	UFUNCTION()
	void OnMontageInterrupted();

	/** 트레이스 밴드 시작 — authority에서 무기 트레이스 태스크 시작 */
	UFUNCTION()
	void OnWeaponTraceBegin(FGameplayEventData EventData);

	UFUNCTION()
	void OnWeaponTraceEnd(FGameplayEventData EventData);

	/** 무기 적중 (타겟당 1회) — Damage GE + 오의 수급 */
	UFUNCTION()
	void OnWeaponHit(const FHitResult& HitResult);

	void StopWeaponTrace();

protected:
	/** 강화 공격 모션 (히트 노티파이 포함) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered")
	TObjectPtr<UAnimMontage> AttackMontage;

	/** 강화 데미지 — 기본 공격보다 높게 (Damage GE는 GameData 전역, SetByCaller.Damage 주입) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered")
	float BaseDamage = 60.f;

	/** 무기 트레이스 스피어 반경 — 강화 일격은 콤보보다 관대하게 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered|Trace")
	float WeaponTraceRadius = 35.f;

private:
	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilityTask_WeaponTrace> WeaponTraceTask;

	UPROPERTY(Transient)
	TObjectPtr<AAstralWeaponActor> ActiveWeaponActor;
};
