#include "AstralAbilitySystemComponent.h"

#include "Abilities/AstralGameplayAbility.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
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
		TryActivateAbilityFromInput(AbilitySpecHandle);
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

void UAstralAbilitySystemComponent::TryActivateAbilityFromInput(const FGameplayAbilitySpecHandle& Handle)
{
	FGameplayAbilitySpec* Spec = FindAbilitySpecFromHandle(Handle);
	if (!Spec || !Spec->Ability)
	{
		return;
	}

	// primary instance 우선 (InstancedPerActor) — 인스턴스가 BP 파생의 오버라이드를 들고 있다
	const UAstralGameplayAbility* AstralAbility = Cast<UAstralGameplayAbility>(Spec->GetPrimaryInstance());
	if (!AstralAbility)
	{
		AstralAbility = Cast<UAstralGameplayAbility>(Spec->Ability);
	}

	// 실행 전 데이터 작성 훅 — ASC는 데이터의 종류를 모른다. 결과에 따라 활성화 경로만 고른다
	FGameplayEventData EventData;
	const EAstralInputActivationPreparation Preparation = (AstralAbility && AbilityActorInfo.IsValid())
		? AstralAbility->MakeActivationEventData(*AbilityActorInfo, EventData)
		: EAstralInputActivationPreparation::Default;

	switch (Preparation)
	{
	case EAstralInputActivationPreparation::Default:
		TryActivateAbility(Handle);
		return;

	case EAstralInputActivationPreparation::Failed:
		// 작성 실패는 일반 활성화로 폴백하지 않는다 — 데이터 없이 활성화되면 서버·클라 문맥이 갈린다
		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[ASC] %s: 활성화 데이터 작성 실패 — 이번 입력 무시"), *GetNameSafe(AstralAbility));
		return;

	case EAstralInputActivationPreparation::WithEventData:
	{
		// 이벤트 경로 가드 — 일반 활성화의 엔진 가드를 재구현하지 않는다 (Default 경로는 그대로)
		if (Spec->PendingRemove || Spec->RemoveAfterActivation)
		{
			return;
		}
		const AActor* Avatar = AbilityActorInfo->AvatarActor.Get();
		if (!Avatar || Avatar->GetLocalRole() == ROLE_SimulatedProxy)
		{
			return;
		}

		// 태그는 엔진이 EventTag에 스탬프만 한다 (라우팅 없음, SpecHandle 직접 지정) — 의미는 "입력으로 활성화"뿐
		TriggerAbilityFromGameplayEvent(Handle, AbilityActorInfo.Get(), AstralGameplayTags::GameplayEvent_ActivateFromInput, &EventData, *this);
		return;
	}
	}
}

void UAstralAbilitySystemComponent::ClearAbilityInput()
{
	InputPressedSpecHandles.Reset();
	InputReleasedSpecHandles.Reset();
	InputHeldSpecHandles.Reset();
}

