#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_BasicAttack_Melee.generated.h"

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_BasicAttack_Melee : public UAstralGA_Hero_Base
{
	GENERATED_BODY()
	
public:
	UAstralGA_Hero_BasicAttack_Melee(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	UFUNCTION()
	void OnMontageCompleted();

	UFUNCTION()
	void OnMontageInterrupted();

	UFUNCTION()
	void OnHitEventReceived(FGameplayEventData EventData);

	/** 서버 측 적중 판정 + Damage GE 적용 */
	void PerformHitDetection();

protected:
	/** 공격 모션 (BP에서 AM_Hero_BasicAttack_Melee_01 지정) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|BasicAttack")
	TObjectPtr<UAnimMontage> AttackMontage;

	/** Damage GE 클래스 (BP에서 GE_Damage_Base 지정) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|BasicAttack")
	TSubclassOf<UGameplayEffect> DamageEffectClass;

	/** Sphere Trace 반경 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|BasicAttack|Trace")
	float TraceRadius = 80.f;

	/** Trace 거리 (캐릭터 정면) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|BasicAttack|Trace")
	float TraceDistance = 200.f;

	/** Trace 시작 오프셋 (캐릭터 중심에서 정면) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|BasicAttack|Trace")
	float TraceStartOffset = 50.f;

	/** SetByCaller로 주입할 BaseDamage */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|BasicAttack")
	float BaseDamage = 25.f;
};
