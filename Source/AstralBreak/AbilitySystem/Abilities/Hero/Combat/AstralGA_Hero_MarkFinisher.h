#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_MarkFinisher.generated.h"

class UAnimMontage;

/**
 * 고유 자원 강화 공격 — 표식(MarkStack)을 소비하는 강화 근접 일격.
 * 비용은 표준 CostGameplayEffect 경로(BP에서 GE_Cost_MarkFinisher 지정 — MarkStack -N Instant).
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_MarkFinisher : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_MarkFinisher(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	UFUNCTION()
	void OnMontageCompleted();

	UFUNCTION()
	void OnMontageInterrupted();

	/** 히트 노티파이 — 서버 권위 판정 (공용 ApplyDamageSweep) */
	UFUNCTION()
	void OnHitEventReceived(FGameplayEventData EventData);

protected:
	/** 강화 공격 모션 (히트 노티파이 포함) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered")
	TObjectPtr<UAnimMontage> AttackMontage;

	/** 강화 데미지 — 기본 공격보다 높게 (Damage GE는 GameData 전역, SetByCaller.Damage 주입) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered")
	float BaseDamage = 60.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered|Trace")
	float TraceRadius = 100.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered|Trace")
	float TraceDistance = 250.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered|Trace")
	float TraceStartOffset = 50.f;
};
