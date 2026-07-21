#include "AstralGA_Death.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_WaitDelay.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AstralLogChannels.h"
#include "Character/Components/AstralHealthComponent.h"

UAstralGA_Death::UAstralGA_Death(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerInitiated;
	ActivationPolicy = EAstralAbilityActivationPolicy::Manual;

	// 사망 상태에서 발동되는 어빌리티 — 베이스의 State.Death 전면 차단 opt-out
	ActivationBlockedTags.RemoveTag(AstralGameplayTags::State_Death);

	if (HasAnyFlags(RF_ClassDefaultObject))
	{
		// GameplayEvent.Death 수신 시 자동 트리거 (HealthComponent::HandleOutOfHealth가 발송)
		FAbilityTriggerData TriggerData;
		TriggerData.TriggerTag = AstralGameplayTags::GameplayEvent_Death;
		TriggerData.TriggerSource = EGameplayAbilityTriggerSource::GameplayEvent;
		AbilityTriggers.Add(TriggerData);
	}
}

void UAstralGA_Death::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	check(ActorInfo);

	UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();
	check(ASC);

	// SurvivesDeath 표시 어빌리티와 자기 자신을 제외하고 전부 취소
	FGameplayTagContainer AbilityTypesToIgnore;
	AbilityTypesToIgnore.AddTag(AstralGameplayTags::Ability_Behavior_SurvivesDeath);
	ASC->CancelAbilities(nullptr, &AbilityTypesToIgnore, this);

	SetCanBeCanceled(false);

	// TODO: ActivationGroup 도입 시 Exclusive_Blocking 전환

	if (bAutoStartDeath)
	{
		StartDeath();
	}

	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 연출 길이만큼 대기 후 종료 — 몽타주 도입 시 이 태스크를 몽타주 종료 콜백으로 교체
	if (UAbilityTask_WaitDelay* WaitTask = UAbilityTask_WaitDelay::WaitDelay(this, DeathDuration))
	{
		WaitTask->OnFinish.AddDynamic(this, &UAstralGA_Death::OnDeathDurationElapsed);
		WaitTask->ReadyForActivation();
	}
}

void UAstralGA_Death::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	check(ActorInfo);

	// 어빌리티가 어떤 경로로 끝나든 사망 완료 보장 — StartDeath 전이면 no-op
	FinishDeath();

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

void UAstralGA_Death::OnDeathDurationElapsed()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}

void UAstralGA_Death::StartDeath()
{
	if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(GetAvatarActorFromActorInfo()))
	{
		if (HealthComponent->GetDeathState() == EAstralDeathState::NotDead)
		{
			HealthComponent->StartDeath();
		}
	}
}

void UAstralGA_Death::FinishDeath()
{
	if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(GetAvatarActorFromActorInfo()))
	{
		if (HealthComponent->GetDeathState() == EAstralDeathState::DeathStarted)
		{
			HealthComponent->FinishDeath();
		}
	}
}
