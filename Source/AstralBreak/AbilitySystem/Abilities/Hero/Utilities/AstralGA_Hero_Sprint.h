#pragma once

#include "CoreMinimal.h"
#include "ActiveGameplayEffectHandle.h"
#include "GameplayEffectTypes.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_Sprint.generated.h"

class ACharacter;
class UGameplayEffect;
class UAstralHeroMovementComponent;

UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Sprint : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_Sprint(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	//~UGameplayAbility interface
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;
	//~End of UGameplayAbility interface

	UFUNCTION()
	void OnInputReleased(float TimeHeld);

	/** 지상 이탈(점프/낙하) 시 종료 — Shift 유지 상태로 착지하면 WhileInputActive가 자동 재발동 */
	UFUNCTION()
	void OnMovementModeChanged(ACharacter* Character, EMovementMode PrevMovementMode, uint8 PreviousCustomMode);

	/** Stamina 변경 감시 — 고갈(<=0) 시 종료 */
	void OnStaminaChanged(const FOnAttributeChangeData& Data);

	UAstralHeroMovementComponent* GetHeroMovementComponent(const FGameplayAbilityActorInfo* ActorInfo) const;

protected:

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Sprint")
	TSubclassOf<UGameplayEffect> DrainEffectClass;

	/** 재발동에 필요한 최소 Stamina — 고갈 종료는 0, 재발동은 이 값 이상 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Sprint", Meta = (ClampMin = "0.0"))
	float SprintReactivationThreshold = 15.0f;

private:

	FActiveGameplayEffectHandle DrainEffectHandle;
	FDelegateHandle StaminaChangedDelegateHandle;

	/** Commit 이후 실제로 스프린트가 시작됐는지 — 커밋 실패로 끝난 활성화에 회복 지연을 걸지 않기 위한 게이트 */
	bool bSprintStarted = false;
};
