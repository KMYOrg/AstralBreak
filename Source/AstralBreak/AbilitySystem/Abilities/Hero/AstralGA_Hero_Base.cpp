// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGA_Hero_Base.h"

#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"

UAstralGA_Hero_Base::UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UAstralGA_Hero_Base::ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const
{
	if (!RegenBlockEffectClass || !ActorInfo || !ActorInfo->IsNetAuthority())
	{
		return;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(Handle, ActorInfo, ActivationInfo, RegenBlockEffectClass, GetAbilityLevel());
	if (SpecHandle.IsValid())
	{
		ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, SpecHandle);
	}
}

void UAstralGA_Hero_Base::ApplyUltGain(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, float Amount) const
{
	ApplySetByCallerGainEffect(Handle, ActorInfo, ActivationInfo, UltGainEffectClass, AstralGameplayTags::SetByCaller_UltGain, Amount);
}

void UAstralGA_Hero_Base::ApplyMarkGain(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, float Amount) const
{
	ApplySetByCallerGainEffect(Handle, ActorInfo, ActivationInfo, MarkGainEffectClass, AstralGameplayTags::SetByCaller_MarkGain, Amount);
}

void UAstralGA_Hero_Base::ApplySetByCallerGainEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, TSubclassOf<UGameplayEffect> EffectClass, const FGameplayTag& SetByCallerTag, float Amount) const
{
	if (!EffectClass || Amount <= 0.f || !ActorInfo || !ActorInfo->IsNetAuthority())
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
