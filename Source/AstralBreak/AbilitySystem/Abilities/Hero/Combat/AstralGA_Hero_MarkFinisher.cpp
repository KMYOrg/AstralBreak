#include "AstralGA_Hero_MarkFinisher.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Tasks/AstralAbilityTask_WeaponTrace.h"
#include "Animation/AnimMontage.h"
#include "Equipment/AstralWeaponActor.h"
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

	// 무기 트레이스 밴드 (Begin=태스크 시작, End=종료)
	if (UAbilityTask_WaitGameplayEvent* TraceBeginTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin, nullptr, false, true))
	{
		TraceBeginTask->EventReceived.AddDynamic(this, &ThisClass::OnWeaponTraceBegin);
		TraceBeginTask->ReadyForActivation();
	}
	if (UAbilityTask_WaitGameplayEvent* TraceEndTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_WeaponTrace_End, nullptr, false, true))
	{
		TraceEndTask->EventReceived.AddDynamic(this, &ThisClass::OnWeaponTraceEnd);
		TraceEndTask->ReadyForActivation();
	}
}

void UAstralGA_Hero_MarkFinisher::OnWeaponTraceBegin(FGameplayEventData EventData)
{
	// 서버 권위 판정 — authority 인스턴스에서만 태스크 생성
	if (!HasAuthority(&CurrentActivationInfo))
	{
		return;
	}

	StopWeaponTrace();

	ActiveWeaponActor = UAstralAbilityTask_WeaponTrace::FindWeaponActorFromAbility(this);
	if (!ActiveWeaponActor)
	{
		return;
	}

	WeaponTraceTask = UAstralAbilityTask_WeaponTrace::WeaponTrace(this, ActiveWeaponActor, WeaponTraceRadius);
	if (WeaponTraceTask)
	{
		WeaponTraceTask->OnHitTarget.AddDynamic(this, &ThisClass::OnWeaponHit);
		WeaponTraceTask->ReadyForActivation();
	}
}

void UAstralGA_Hero_MarkFinisher::OnWeaponTraceEnd(FGameplayEventData EventData)
{
	StopWeaponTrace();
}

void UAstralGA_Hero_MarkFinisher::StopWeaponTrace()
{
	if (WeaponTraceTask)
	{
		WeaponTraceTask->EndTask();
		WeaponTraceTask = nullptr;
	}
	ActiveWeaponActor = nullptr;
}

void UAstralGA_Hero_MarkFinisher::OnWeaponHit(const FHitResult& HitResult)
{
	if (UAstralCombatStatics::ApplyWeaponDamage(GetAbilitySystemComponentFromActorInfo(), GetAvatarActorFromActorInfo(), ActiveWeaponActor, HitResult, BaseDamage, GetAbilityLevel()))
	{
		ApplyUltGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, UltGainOnHit);
	}
}

void UAstralGA_Hero_MarkFinisher::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	WeaponTraceTask = nullptr;
	ActiveWeaponActor = nullptr;

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

void UAstralGA_Hero_MarkFinisher::OnMontageCompleted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_MarkFinisher::OnMontageInterrupted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}
