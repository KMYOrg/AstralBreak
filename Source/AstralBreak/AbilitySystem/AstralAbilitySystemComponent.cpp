#include "AstralAbilitySystemComponent.h"

#include "Abilities/AstralGameplayAbility.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Animation/AstralAnimInstance.h"
#include "AstralLogChannels.h"

UE_DEFINE_GAMEPLAY_TAG(TAG_Gameplay_AbilityInputBlocked, "Gameplay.AbilityInputBlocked");

FGameplayTag UAstralAbilitySystemComponent::GetCombatStyle() const
{
	FGameplayTagContainer OwnedTags;
	GetOwnedGameplayTags(OwnedTags);
	for (auto TagIt = OwnedTags.CreateConstIterator(); TagIt; ++TagIt)
	{
		if (*TagIt != AstralGameplayTags::State_CombatStyle && TagIt->MatchesTag(AstralGameplayTags::State_CombatStyle))
		{
			return *TagIt;
		}
	}
	return FGameplayTag();
}

void UAstralAbilitySystemComponent::SetCombatStyle(FGameplayTag NewStyle)
{
	if (!IsOwnerActorAuthoritative())
	{
		return;
	}

	// 부모 자체(State.CombatStyle)는 상태로 쓰지 않는다 — 자식만 유효
	if (!NewStyle.MatchesTag(AstralGameplayTags::State_CombatStyle) || NewStyle == AstralGameplayTags::State_CombatStyle)
	{
		UE_LOG(LogAstral, Warning, TEXT("SetCombatStyle: %s 는 State.CombatStyle 자식 태그가 아님 — 무시"), *NewStyle.ToString());
		return;
	}

	// 보유 중인 스타일 태그를 전부 내리고 새 태그만 올린다 — 스타일 집합을 코드가 모르므로 부모 태그 질의로 일괄 해제
	FGameplayTagContainer OwnedTags;
	GetOwnedGameplayTags(OwnedTags);
	for (auto TagIt = OwnedTags.CreateConstIterator(); TagIt; ++TagIt)
	{
		const FGameplayTag& OwnedTag = *TagIt;
		if (OwnedTag != NewStyle && OwnedTag != AstralGameplayTags::State_CombatStyle && OwnedTag.MatchesTag(AstralGameplayTags::State_CombatStyle))
		{
			SetLooseGameplayTagCount(OwnedTag, 0, EGameplayTagReplicationState::TagAndCountToAll);
		}
	}
	SetLooseGameplayTagCount(NewStyle, 1, EGameplayTagReplicationState::TagAndCountToAll);
}

UAstralAbilitySystemComponent::UAstralAbilitySystemComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InputPressedSpecHandles.Reset();
	InputReleasedSpecHandles.Reset();
	InputHeldSpecHandles.Reset();
}

void UAstralAbilitySystemComponent::InitAbilityActorInfo(AActor* InOwnerActor, AActor* InAvatarActor)
{
	FGameplayAbilityActorInfo* ActorInfo = AbilityActorInfo.Get();
	check(ActorInfo);
	check(InOwnerActor);

	const bool bHasNewPawnAvatar = Cast<APawn>(InAvatarActor) && (InAvatarActor != ActorInfo->AvatarActor);

	Super::InitAbilityActorInfo(InOwnerActor, InAvatarActor);

	if (bHasNewPawnAvatar)
	{
		if (UAstralAnimInstance* AstralAnimInst = Cast<UAstralAnimInstance>(ActorInfo->GetAnimInstance()))
		{
			AstralAnimInst->InitializeWithAbilitySystem(this);
		}

		TryActivateAbilitiesOnSpawn();
	}
}

void UAstralAbilitySystemComponent::TryActivateAbilitiesOnSpawn()
{
	ABILITYLIST_SCOPE_LOCK();
	for (const FGameplayAbilitySpec& AbilitySpec : ActivatableAbilities.Items)
	{
		if (const UAstralGameplayAbility* AstralAbilityCDO = Cast<UAstralGameplayAbility>(AbilitySpec.Ability))
		{
			AstralAbilityCDO->TryActivateAbilityOnSpawn(AbilityActorInfo.Get(), AbilitySpec);
		}
	}
}

void UAstralAbilitySystemComponent::AbilitySpecInputPressed(FGameplayAbilitySpec& Spec)
{
	Super::AbilitySpecInputPressed(Spec);
	
	if (Spec.IsActive())
	{
PRAGMA_DISABLE_DEPRECATION_WARNINGS
		const UGameplayAbility* Instance = Spec.GetPrimaryInstance();
		FPredictionKey OriginalPredictionKey = Instance ? Instance->GetCurrentActivationInfo().GetActivationPredictionKey() : Spec.ActivationInfo.GetActivationPredictionKey();
PRAGMA_ENABLE_DEPRECATION_WARNINGS
		InvokeReplicatedEvent(EAbilityGenericReplicatedEvent::InputPressed, Spec.Handle, OriginalPredictionKey);
	}
}

void UAstralAbilitySystemComponent::AbilitySpecInputReleased(FGameplayAbilitySpec& Spec)
{
	Super::AbilitySpecInputReleased(Spec);
	
	if (Spec.IsActive())
	{
PRAGMA_DISABLE_DEPRECATION_WARNINGS
		const UGameplayAbility* Instance = Spec.GetPrimaryInstance();
		FPredictionKey OriginalPredictionKey = Instance ? Instance->GetCurrentActivationInfo().GetActivationPredictionKey() : Spec.ActivationInfo.GetActivationPredictionKey();
PRAGMA_ENABLE_DEPRECATION_WARNINGS
		InvokeReplicatedEvent(EAbilityGenericReplicatedEvent::InputReleased, Spec.Handle, OriginalPredictionKey);
	}
}

void UAstralAbilitySystemComponent::AbilityInputTagPressed(const FGameplayTag& InputTag)
{
	if (InputTag.IsValid())
	{
		for (const FGameplayAbilitySpec& AbilitySpec : ActivatableAbilities.Items)
		{
			if (AbilitySpec.Ability && (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(InputTag)))
			{
				InputPressedSpecHandles.AddUnique(AbilitySpec.Handle);
				InputHeldSpecHandles.AddUnique(AbilitySpec.Handle);
			}
		}
	}
}

void UAstralAbilitySystemComponent::AbilityInputTagReleased(const FGameplayTag& InputTag)
{
	if (InputTag.IsValid())
	{
		for (const FGameplayAbilitySpec& AbilitySpec : ActivatableAbilities.Items)
		{
			if (AbilitySpec.Ability && (AbilitySpec.GetDynamicSpecSourceTags().HasTagExact(InputTag)))
			{
				InputReleasedSpecHandles.AddUnique(AbilitySpec.Handle);
				InputHeldSpecHandles.Remove(AbilitySpec.Handle);
			}
		}
	}
}

void UAstralAbilitySystemComponent::ProcessAbilityInput(float DeltaTime, bool bGamePaused)
{
	if (HasMatchingGameplayTag(TAG_Gameplay_AbilityInputBlocked))
	{
		ClearAbilityInput();
		return;
	}

	static TArray<FGameplayAbilitySpecHandle> AbilitiesToActivate;
	AbilitiesToActivate.Reset();

	//@TODO: See if we can use FScopedServerAbilityRPCBatcher ScopedRPCBatcher in some of these loops
	
	for (const FGameplayAbilitySpecHandle& SpecHandle : InputHeldSpecHandles)
	{
		if (const FGameplayAbilitySpec* AbilitySpec = FindAbilitySpecFromHandle(SpecHandle))
		{
			if (AbilitySpec->Ability && !AbilitySpec->IsActive())
			{
				const UAstralGameplayAbility* AstralAbilityCDO = Cast<UAstralGameplayAbility>(AbilitySpec->Ability);
				if (AstralAbilityCDO && AstralAbilityCDO->GetActivationPolicy() == EAstralAbilityActivationPolicy::WhileInputActive)
				{
					AbilitiesToActivate.AddUnique(AbilitySpec->Handle);
				}
			}
		}
	}
	
	for (const FGameplayAbilitySpecHandle& SpecHandle : InputPressedSpecHandles)
	{
		if (FGameplayAbilitySpec* AbilitySpec = FindAbilitySpecFromHandle(SpecHandle))
		{
			if (AbilitySpec->Ability)
			{
				AbilitySpec->InputPressed = true;

				if (AbilitySpec->IsActive())
				{
					AbilitySpecInputPressed(*AbilitySpec);
				}
				else
				{
					const UAstralGameplayAbility* AstralAbilityCDO = Cast<UAstralGameplayAbility>(AbilitySpec->Ability);

					if (AstralAbilityCDO && AstralAbilityCDO->GetActivationPolicy() == EAstralAbilityActivationPolicy::OnInputTriggered)
					{
						AbilitiesToActivate.AddUnique(AbilitySpec->Handle);
					}
				}
			}
		}
	}

	for (const FGameplayAbilitySpecHandle& AbilitySpecHandle : AbilitiesToActivate)
	{
		TryActivateAbility(AbilitySpecHandle);
	}

	for (const FGameplayAbilitySpecHandle& SpecHandle : InputReleasedSpecHandles)
	{
		if (FGameplayAbilitySpec* AbilitySpec = FindAbilitySpecFromHandle(SpecHandle))
		{
			if (AbilitySpec->Ability)
			{
				AbilitySpec->InputPressed = false;

				if (AbilitySpec->IsActive())
				{
					AbilitySpecInputReleased(*AbilitySpec);
				}
			}
		}
	}

	InputPressedSpecHandles.Reset();
	InputReleasedSpecHandles.Reset();
}

void UAstralAbilitySystemComponent::ClearAbilityInput()
{
	InputPressedSpecHandles.Reset();
	InputReleasedSpecHandles.Reset();
	InputHeldSpecHandles.Reset();
}

