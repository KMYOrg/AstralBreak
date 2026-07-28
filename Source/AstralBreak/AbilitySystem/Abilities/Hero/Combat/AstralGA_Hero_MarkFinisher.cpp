#include "AstralGA_Hero_MarkFinisher.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Animation/AnimMontage.h"
#include "GameFramework/Pawn.h"

UAstralGA_Hero_MarkFinisher::UAstralGA_Hero_MarkFinisher(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

	// 모드 분기 — Melee 모드 전용 (BasicAttack과 동일 패턴)
	ActivationRequiredTags.AddTag(AstralGameplayTags::State_CombatStyle_Melee);

	ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack_Empowered);

	// asset tag + 상호배타 (BasicAttack과 동일 패턴)
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Attack_Empowered);
	SetAssetTags(AssetTags);

	BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Attack);
	CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Defense);
}

void UAstralGA_Hero_MarkFinisher::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 비용(GE_Cost_MarkFinisher — MarkStack 소비) 게이트 + 소비. 부족하면 CheckCost가 거부
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
		return;
	}

	if (!AttackMontage)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
		return;
	}

	if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, AttackMontage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
	{
		MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->ReadyForActivation();
	}

	if (UAbilityTask_WaitGameplayEvent* HitEventTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Hit, nullptr, false, true))
	{
		HitEventTask->EventReceived.AddDynamic(this, &ThisClass::OnHitEventReceived);
		HitEventTask->ReadyForActivation();
	}
}

void UAstralGA_Hero_MarkFinisher::OnHitEventReceived(FGameplayEventData EventData)
{
	if (!HasAuthority(&CurrentActivationInfo))
	{
		return;
	}

	APawn* Avatar = Cast<APawn>(GetAvatarActorFromActorInfo());
	UAbilitySystemComponent* SourceASC = GetAbilitySystemComponentFromActorInfo();

	const int32 NumTargetsHit = UAstralCombatStatics::ApplyDamageSweep(SourceASC, Avatar, BaseDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel());
	if (NumTargetsHit > 0)
	{
		ApplyUltGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, UltGainOnHit * NumTargetsHit);
	}
}

void UAstralGA_Hero_MarkFinisher::OnMontageCompleted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_MarkFinisher::OnMontageInterrupted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}
