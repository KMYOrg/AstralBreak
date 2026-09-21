// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGA_Hero_Base.h"

#include "Character/Hero/AstralCharacter_Hero.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "Combat/AstralFacingTypes.h"
#include "Combat/AstralTargetingStatics.h"
#include "System/AstralGameData.h"

UAstralGA_Hero_Base::UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

//////////////////////////////////////////////////////////////////////////
// 타게팅 바인딩

FAstralTargetHandle UAstralGA_Hero_Base::ResolveEffectiveTarget() const
{
	return ResolveEffectiveTarget(GetAvatarActorFromActorInfo());
}

FAstralTargetHandle UAstralGA_Hero_Base::ResolveEffectiveTarget(const AActor* Avatar)
{
	// GetAstralCharacterFromActorInfo는 베이스(AAstralCharacter)를 돌려주므로 히어로 캐스트는 여기서
	const AAstralCharacter_Hero* Hero = Cast<AAstralCharacter_Hero>(Avatar);
	const UAstralTargetingComponent* Targeting = Hero ? Hero->GetTargetingComponent() : nullptr;
	return Targeting ? Targeting->GetEffectiveTarget() : FAstralTargetHandle();
}

FAstralFacingProposal UAstralGA_Hero_Base::CaptureFacingProposal(const AActor* Avatar, int32 StageIndex) const
{
	// uint8 변환 전 범위 확인 — 스테이지 수 검증(ValidateComboStageMontages)이 놓친 경우의 마지막 방어
	if (!ensureMsgf(StageIndex >= 0 && StageIndex <= 255, TEXT("[Facing] %s: StageIndex %d — uint8 범위 밖"), *GetName(), StageIndex))
	{
		StageIndex = FMath::Clamp(StageIndex, 0, 255);
	}

	FAstralFacingProposal Proposal = FAstralFacingProposal::MakeNone(static_cast<uint8>(StageIndex));

	const FAstralTargetHandle Target = ResolveEffectiveTarget(Avatar);
	if (!Avatar || !Target.IsSet())
	{
		return Proposal;
	}

	const float CurrentYaw = Avatar->GetActorRotation().Yaw;
	const float DesiredYaw = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), Target.GetAimLocation(), CurrentYaw);

	Proposal.Source = EAstralFacingSource::LockOn;
	Proposal.TargetActor = Target.TargetActor;
	Proposal.TargetPointId = NAME_None; // M5까지 부위 없음
	Proposal.QuantizedDesiredYaw = AstralFacing::QuantizeYaw(DesiredYaw);
	return Proposal;
}

//////////////////////////////////////////////////////////////////////////
// 자원 바인딩

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
