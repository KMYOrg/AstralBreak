// Fill out your copyright notice in the Description page of Project Settings.

#include "AstralGA_Hero_Jump.h"

#include "Character/AstralCharacter.h"
#include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"

UAstralGA_Hero_Jump::UAstralGA_Hero_Jump(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

bool UAstralGA_Hero_Jump::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!ActorInfo || !ActorInfo->AvatarActor.IsValid())
	{
		return false;
	}

	const AAstralCharacter* Character = Cast<AAstralCharacter>(ActorInfo->AvatarActor.Get());
	if (!Character || !Character->CanJump())
	{
		return false;
	}

	return Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
}

void UAstralGA_Hero_Jump::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 비용/쿨다운 적용 (현재 없음, 추후 Stamina 비용 부착 대비)
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	CharacterJumpStart();

	// 가변 점프 높이: 입력을 떼면 StopJumping 후 종료
	UAbilityTask_WaitInputRelease* Task = UAbilityTask_WaitInputRelease::WaitInputRelease(this, /*bTestAlreadyReleased=*/true);
	Task->OnRelease.AddDynamic(this, &UAstralGA_Hero_Jump::OnInputReleased);
	Task->ReadyForActivation();
}

void UAstralGA_Hero_Jump::OnInputReleased(float TimeHeld)
{
	CharacterJumpStop();
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}

void UAstralGA_Hero_Jump::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	CharacterJumpStop();

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

void UAstralGA_Hero_Jump::CharacterJumpStart()
{
	if (AAstralCharacter* Character = GetAstralCharacterFromActorInfo())
	{
		if (Character->IsLocallyControlled() && !Character->bPressedJump)
		{
			Character->UnCrouch();
			Character->Jump();
		}
	}
}

void UAstralGA_Hero_Jump::CharacterJumpStop()
{
	if (AAstralCharacter* Character = GetAstralCharacterFromActorInfo())
	{
		if (Character->IsLocallyControlled() && Character->bPressedJump)
		{
			Character->StopJumping();
		}
	}
}
