#include "AstralGA_Hero_Sprint.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Hero/Components/AstralHeroMovementComponent.h"

UAstralGA_Hero_Sprint::UAstralGA_Hero_Sprint(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	ActivationPolicy = EAstralAbilityActivationPolicy::WhileInputActive;

	// 활성 중 부여 — 회복 GE(GE_Stamina_Regen)의 Ongoing Tag Requirements가 이 태그로 inhibit
	ActivationOwnedTags.AddTag(AstralGameplayTags::State_Movement_Sprinting);
}

bool UAstralGA_Hero_Sprint::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!ActorInfo || !ActorInfo->AvatarActor.IsValid())
	{
		return false;
	}

	// 지상 + 이동 입력 존재 시에만 발동 (제자리 발동 방지)
	const UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(ActorInfo);
	if (!HeroMC || !HeroMC->IsMovingOnGround())
	{
		return false;
	}

	if (HeroMC->GetCurrentAcceleration().SizeSquared2D() <= UE_KINDA_SMALL_NUMBER)
	{
		return false;
	}

	// 고갈 종료는 0, 재발동은 임계값 이상 — WhileInputActive의 매 프레임 재활성 플리커 차단
	const UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();
	if (!ASC || ASC->GetNumericAttribute(UAstralHeroResourceSet::GetStaminaAttribute()) < SprintReactivationThreshold)
	{
		return false;
	}

	return Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
}

void UAstralGA_Hero_Sprint::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(ActorInfo);
	if (!HeroMC)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	HeroMC->SetSprinting(true);
	bSprintStarted = true;

	// 지상 이탈 감시 — 점프/낙하 시 종료 (착지 후 WhileInputActive가 자동 재발동)
	if (AAstralCharacter* Character = Cast<AAstralCharacter>(ActorInfo->AvatarActor.Get()))
	{
		Character->MovementModeChangedDelegate.AddDynamic(this, &UAstralGA_Hero_Sprint::OnMovementModeChanged);
	}

	// Stamina 드레인 GE 적용 (주기적 무한 — EndAbility에서 제거)
	if (DrainEffectClass)
	{
		const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(DrainEffectClass, GetAbilityLevel());
		if (SpecHandle.IsValid())
		{
			DrainEffectHandle = ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, SpecHandle);
		}
	}

	if (UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get())
	{
		StaminaChangedDelegateHandle = ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetStaminaAttribute()).AddUObject(this, &UAstralGA_Hero_Sprint::OnStaminaChanged);
	}

	UAbilityTask_WaitInputRelease* Task = UAbilityTask_WaitInputRelease::WaitInputRelease(this, /*bTestAlreadyReleased=*/true);
	Task->OnRelease.AddDynamic(this, &UAstralGA_Hero_Sprint::OnInputReleased);
	Task->ReadyForActivation();
}

void UAstralGA_Hero_Sprint::OnInputReleased(float TimeHeld)
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}

void UAstralGA_Hero_Sprint::OnMovementModeChanged(ACharacter* Character, EMovementMode PrevMovementMode, uint8 PreviousCustomMode)
{
	const UCharacterMovementComponent* CMC = Character ? Character->GetCharacterMovement() : nullptr;
	if (CMC && !CMC->IsMovingOnGround())
	{
		EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
	}
}

void UAstralGA_Hero_Sprint::OnStaminaChanged(const FOnAttributeChangeData& Data)
{
	if (Data.NewValue <= 0.0f)
	{
		EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
	}
}

void UAstralGA_Hero_Sprint::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(ActorInfo))
	{
		HeroMC->SetSprinting(false);
	}

	if (AAstralCharacter* Character = (ActorInfo ? Cast<AAstralCharacter>(ActorInfo->AvatarActor.Get()) : nullptr))
	{
		Character->MovementModeChangedDelegate.RemoveDynamic(this, &UAstralGA_Hero_Sprint::OnMovementModeChanged);
	}

	if (UAbilitySystemComponent* ASC = ActorInfo ? ActorInfo->AbilitySystemComponent.Get() : nullptr)
	{
		if (DrainEffectHandle.IsValid())
		{
			ASC->RemoveActiveGameplayEffect(DrainEffectHandle);
		}

		if (StaminaChangedDelegateHandle.IsValid())
		{
			ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetStaminaAttribute()).Remove(StaminaChangedDelegateHandle);
		}
	}

	DrainEffectHandle.Invalidate();
	StaminaChangedDelegateHandle.Reset();

	// 실제 스프린트가 있었을 때만 회복 지연 시작 — 커밋 실패로 끝난 활성화엔 걸지 않음
	if (bSprintStarted)
	{
		ApplyRegenBlockEffect(Handle, ActorInfo, ActivationInfo);
	}
	bSprintStarted = false;

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

UAstralHeroMovementComponent* UAstralGA_Hero_Sprint::GetHeroMovementComponent(const FGameplayAbilityActorInfo* ActorInfo) const
{
	const AAstralCharacter* Character = (ActorInfo ? Cast<AAstralCharacter>(ActorInfo->AvatarActor.Get()) : nullptr);
	return (Character ? Cast<UAstralHeroMovementComponent>(Character->GetCharacterMovement()) : nullptr);
}
