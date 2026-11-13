#include "AstralGA_Hero_Ult.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Effects/AstralGE_Cost_Ult.h"
#include "Animation/AnimMontage.h"

UAstralGA_Hero_Ult::UAstralGA_Hero_Ult(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

	// 게이지가 가득일 때만 통과하고 전부 쓴다 — 검사는 표준 비용 경로(CheckCost)가 한다
	CostGameplayEffectClass = UAstralGE_Cost_Ult::StaticClass();

	HitEventTag = AstralGameplayTags::GameplayEvent_Ult_Hit;

	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Ult);
	AssetTags.AddTag(AstralGameplayTags::Ability_Behavior_SurvivesDefenseCancel);
	SetAssetTags(AssetTags);

	// Ability.Attack 을 owned 태그로 갖는다 — 방어(CanActivate) · 스타일 전환(ActivationBlockedTags)의 '공격 중' 검사가 이 태그를 본다
	ActivationOwnedTags.AddTag(AstralGameplayTags::State_Ult_Active);
	ActivationOwnedTags.AddTag(AstralGameplayTags::State_Invulnerable);
	ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack);

	ActivationBlockedTags.AddTag(AstralGameplayTags::State_Ult_Blocked);

	// 발동하면 하던 것을 끊고, 켜져 있는 동안 새로 못 한다
	CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Attack);
	CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Defense);
	CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Action_Dodge);

	BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Attack);
	BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Defense);
	BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Action_Dodge);
}

void UAstralGA_Hero_Ult::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 비용 게이트 + 소비 — 게이지가 가득이 아니면 CheckCost 가 거부한다
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
		return;
	}

	if (!UltMontage)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
		return;
	}

	if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, UltMontage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
	{
		MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->ReadyForActivation();
	}

	// 타격은 활성화마다 한 번 — 임시 몽타주에 같은 태그의 노티파이가 여러 개여도 처음 것만 받는다
	if (HitEventTag.IsValid())
	{
		if (UAbilityTask_WaitGameplayEvent* HitTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, HitEventTag, nullptr, /*OnlyTriggerOnce=*/true, /*OnlyMatchExact=*/true))
		{
			HitTask->EventReceived.AddDynamic(this, &ThisClass::OnHitEvent);
			HitTask->ReadyForActivation();
		}
	}
}

void UAstralGA_Hero_Ult::OnHitEvent(FGameplayEventData Payload)
{
	// 피해는 서버 권위 — 예측 클라이언트는 연출만 한다
	if (!CurrentActorInfo || !CurrentActorInfo->IsNetAuthority())
	{
		return;
	}

	UAstralCombatStatics::ApplyDamageSweep(CurrentActorInfo->AbilitySystemComponent.Get(), GetAvatarActorFromActorInfo(), BaseDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel());
}

void UAstralGA_Hero_Ult::OnMontageCompleted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_Ult::OnMontageInterrupted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}
