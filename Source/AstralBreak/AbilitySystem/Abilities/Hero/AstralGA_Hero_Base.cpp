// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGA_Hero_Base.h"

#include "AstralLogChannels.h"
#include "Character/Hero/AstralCharacter_Hero.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "Combat/AstralTargetingStatics.h"
#include "System/AstralGameData.h"

UAstralGA_Hero_Base::UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

FAstralTargetHandle UAstralGA_Hero_Base::ResolveEffectiveTarget() const
{
	// GetAstralCharacterFromActorInfo는 베이스(AAstralCharacter)를 돌려주므로 히어로 캐스트는 여기서
	const AAstralCharacter_Hero* Hero = Cast<AAstralCharacter_Hero>(GetAvatarActorFromActorInfo());
	const UAstralTargetingComponent* Targeting = Hero ? Hero->GetTargetingComponent() : nullptr;
	return Targeting ? Targeting->GetEffectiveTarget() : FAstralTargetHandle();
}

FRotator UAstralGA_Hero_Base::ComputeFacingToward(const FVector& AimLocation) const
{
	const AActor* Avatar = GetAvatarActorFromActorInfo();
	if (!Avatar)
	{
		return FRotator::ZeroRotator;
	}

	const float CurrentYaw = Avatar->GetActorRotation().Yaw;
	const float DesiredYaw = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), AimLocation, CurrentYaw);
	return FRotator(0.f, DesiredYaw, 0.f);
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
