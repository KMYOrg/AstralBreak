// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGA_Hero_Base.h"

#include "System/AstralGameData.h"

UAstralGA_Hero_Base::UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UAstralGA_Hero_Base::ApplyUltGain(float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(UAstralGameData::Get().UltGain, Amount);
}

void UAstralGA_Hero_Base::ApplyMarkGain(float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(UAstralGameData::Get().MarkGain, Amount);
}

void UAstralGA_Hero_Base::ApplyStaminaDrain(float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(UAstralGameData::Get().StaminaDrain, -Amount);
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
