// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Hero_Base.generated.h"

class UGameplayEffect;

/**
 *
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Base : public UAstralGameplayAbility
{
	GENERATED_BODY()
public:
	UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	/**
	 * 스태미나 소모 시점(Sprint 종료 / Dodge 커밋 등)에 RegenBlockEffectClass를 오너에 적용
	 * 서버 권위에서만 적용 — 회복 GE의 periodic 틱 자체가 서버 실행
	 */
	void ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const;

protected:
	/** 스태미나 회복 지연 GE (BP에서 GE_Stamina_RegenBlock 지정 — 딜레이 값은 GE의 Duration) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Stamina")
	TSubclassOf<UGameplayEffect> RegenBlockEffectClass;
};
