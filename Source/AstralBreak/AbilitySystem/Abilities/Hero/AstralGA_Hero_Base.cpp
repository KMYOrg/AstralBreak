// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGA_Hero_Base.h"

#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "AbilitySystem/Tasks/AstralAbilityTask_AttackTraceWindows.h"
#include "System/AstralGameData.h"

UAstralGA_Hero_Base::UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

bool UAstralGA_Hero_Base::ApplyAttackHit(const FAstralAttackTraceHit& Hit, float Damage) const
{
	return UAstralCombatStatics::ApplyAttackHit(GetAbilitySystemComponentFromActorInfo(), GetAvatarActorFromActorInfo(), Hit.EffectCauser, Hit.HitResult, Damage, GetAbilityLevel());
}

void UAstralGA_Hero_Base::ApplyUltGain(float Amount) const
{
	ApplyUltGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, Amount);
}

void UAstralGA_Hero_Base::ApplyMarkGain(float Amount) const
{
	ApplyMarkGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, Amount);
}

void UAstralGA_Hero_Base::ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const
{
	if (!ActorInfo || !ActorInfo->IsNetAuthority())
	{
		return;
	}

	const TSubclassOf<UGameplayEffect> EffectClass = UAstralGameData::Get().StaminaRegenBlockEffect.LoadSynchronous();
	if (!EffectClass)
	{
		return;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(Handle, ActorInfo, ActivationInfo, EffectClass, GetAbilityLevel());
	if (SpecHandle.IsValid())
	{
		ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, SpecHandle);
	}
}

void UAstralGA_Hero_Base::ApplyUltGain(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(Handle, ActorInfo, ActivationInfo, UAstralGameData::Get().UltGainGameplayEffect_SetByCaller.LoadSynchronous(), AstralGameplayTags::SetByCaller_UltGain, Amount);
}

void UAstralGA_Hero_Base::ApplyMarkGain(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(Handle, ActorInfo, ActivationInfo, UAstralGameData::Get().MarkGainGameplayEffect_SetByCaller.LoadSynchronous(), AstralGameplayTags::SetByCaller_MarkGain, Amount);
}

void UAstralGA_Hero_Base::ApplySetByCallerEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, TSubclassOf<UGameplayEffect> EffectClass, const FGameplayTag& SetByCallerTag, float Amount) const
{
	if (!EffectClass || FMath::IsNearlyZero(Amount) || !ActorInfo || !ActorInfo->IsNetAuthority())
	{
		return;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(Handle, ActorInfo, ActivationInfo, EffectClass, GetAbilityLevel());
	if (SpecHandle.IsValid())
	{
		SpecHandle.Data->SetSetByCallerMagnitude(SetByCallerTag, Amount);
		ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, SpecHandle);
	}
}
