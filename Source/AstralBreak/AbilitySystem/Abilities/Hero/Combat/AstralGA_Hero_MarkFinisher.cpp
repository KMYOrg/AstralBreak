#include "AstralGA_Hero_MarkFinisher.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAttackMontageValidation.h"
#include "Animation/AnimMontage.h"
#include "Combat/AstralCombatTypes.h"

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

#if !UE_BUILD_SHIPPING
	if (!bMontageValidated)
	{
		bMontageValidated = true;
		AstralAttackMontage::ValidateFacingWarpBand(AttackMontage, FacingWarpTargetName, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin, GetName());
	}
#endif

	// 방향 보정 — 발동 시 1회 스냅샷 (락온 타겟이 있을 때만)
	const FAstralTargetHandle Target = ResolveEffectiveTarget();
	if (Target.IsSet())
	{
		FAstralFacingWarpCommand Command;
		Command.WarpTargetName = FacingWarpTargetName;
		Command.DesiredFacing = ComputeClampedFacing(Target.GetAimLocation(), MaxAssistYaw);
		SetFacingWarp(Command);
	}

	if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, AttackMontage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
	{
		MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->ReadyForActivation();
	}

	TraceTask = UAstralAbilityTask_AttackTraceWindows::WaitAttackTraceWindows(this, WeaponTraceRadius, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin, AstralGameplayTags::GameplayEvent_WeaponTrace_End);
	if (TraceTask)
	{
		TraceTask->OnHitTarget.AddDynamic(this, &ThisClass::OnAttackTraceHit);
		TraceTask->ReadyForActivation();
	}
}

void UAstralGA_Hero_MarkFinisher::OnAttackTraceHit(const FAstralAttackTraceHit& Hit)
{
	if (ApplyAttackHit(Hit, BaseDamage))
	{
		ApplyUltGain(UltGainOnHit);
	}
}

void UAstralGA_Hero_MarkFinisher::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	TraceTask = nullptr;

	// 워프 타겟 해제 — 이름 지정 (다른 시스템의 타겟은 건드리지 않는다)
	ClearFacingWarp(FacingWarpTargetName);

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
