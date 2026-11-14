#include "AstralGA_Hero_Ult.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "AbilitySystem/Effects/AstralGE_Cost_Ult.h"
#include "Animation/AnimMontage.h"
#include "GameModes/AstralChainBurstComponent.h"

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

	// 액터당 인스턴스 — 앞 활성화의 값이 남아 있다
	bCastCommitted = false;
	bHitAny = false;

	// 비용 게이트 + 소비 — 게이지가 가득이 아니면 CheckCost 가 거부한다
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
		return;
	}
	bCastCommitted = true;

	// 시전 시작 — 서버에서 비용 확정이 성공한 직후 (설계 §3 끝 'B 다듬기'). 체인 컴포넌트가 나머지 히어로의 오의를 막고 열린 체인의 타이머를 멈춘다.
	// 예측 클라이언트는 알리지 않는다. 체인 컴포넌트는 레이드 GameState 에만 있다 — 없는 맵(허브 등)에서는 아무 일도 없다
	if (ActorInfo && ActorInfo->IsNetAuthority())
	{
		if (UAstralChainBurstComponent* ChainBurst = UAstralChainBurstComponent::FindChainBurstComponent(ActorInfo->OwnerActor.Get()))
		{
			ChainBurst->NotifyUltStarted(ActorInfo->AbilitySystemComponent.Get());
		}
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

	// 맞혔는가 = 스윕에 적이 한 명이라도 걸렸는가 (피해가 무효로 돌아간 적도 걸린 것이다). 끝날 때 체인 등록 / 게이지 반환을 가른다
	const int32 NumTargetsHit = UAstralCombatStatics::ApplyDamageSweep(CurrentActorInfo->AbilitySystemComponent.Get(), GetAvatarActorFromActorInfo(), BaseDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel());
	bHitAny |= (NumTargetsHit > 0);
}

void UAstralGA_Hero_Ult::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	// 오의가 끝났다(끊긴 것 포함) — 서버에서, 비용을 실제로 쓴 활성화에 한 번만
	if (bCastCommitted && IsEndAbilityValid(Handle, ActorInfo))
	{
		bCastCommitted = false;

		if (ActorInfo && ActorInfo->IsNetAuthority())
		{
			UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();

			// 못 맞힌 오의 — 최대치의 일부를 돌려준다. 수급 경로(UltGain 메타 · UltGainMultiplier)를 타지 않고 게이지에 직접 더한다.
			// 이것은 오의 자체의 규칙이라 체인 컴포넌트가 없는 맵에서도 같다
			if (!bHitAny && ASC && MissRefundRatio > 0.f && ASC->HasAttributeSetForAttribute(UAstralHeroResourceSet::GetUltGaugeAttribute()))
			{
				const float Refund = ASC->GetNumericAttribute(UAstralHeroResourceSet::GetMaxUltGaugeAttribute()) * MissRefundRatio;
				ASC->ApplyModToAttribute(UAstralHeroResourceSet::GetUltGaugeAttribute(), EGameplayModOp::Additive, Refund);
			}

			// 시전 종료 — 맞혔으면 이 시각으로 체인에 등록되고 팀 게이지가 나간다. 못 맞혔으면 멈춘 타이머만 다시 돈다
			if (UAstralChainBurstComponent* ChainBurst = UAstralChainBurstComponent::FindChainBurstComponent(ActorInfo->OwnerActor.Get()))
			{
				ChainBurst->NotifyUltEnded(ASC, bHitAny);
			}
		}
	}

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

void UAstralGA_Hero_Ult::OnMontageCompleted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_Ult::OnMontageInterrupted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}
