#include "AstralGA_Hero_Defend.h"

#include "AbilitySystemComponent.h"
#include "AstralLogChannels.h"
#include "Abilities/Tasks/AbilityTask_WaitDelay.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "Abilities/Tasks/AbilityTask_WaitInputRelease.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Engine/World.h"

UAstralGA_Hero_Defend::UAstralGA_Hero_Defend(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;
	ActivationPolicy   = EAstralAbilityActivationPolicy::WhileInputActive;

	// 활성 시 부여 (디버그/UI 등)
	ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Defense);

	// asset tag — 공격 GA의 CancelAbilitiesWithTag(Ability.Defense)가 이걸로 매칭
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Defense);
	SetAssetTags(AssetTags);
}

bool UAstralGA_Hero_Defend::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!ActorInfo || !ActorInfo->AvatarActor.IsValid())
	{
		return false;
	}

	const UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();
	if (!ASC)
	{
		return false;
	}

	// 가드 브레이크/저스태미나 상태에서 홀드 유지 시 매 프레임 재활성 플리커 차단 (Sprint 임계 미러)
	if (ASC->GetNumericAttribute(UAstralHeroResourceSet::GetStaminaAttribute()) < ReactivationStaminaThreshold)
	{
		return false;
	}

	// 공격 우선 — 공격(콤보 포함) 활성 중엔 방어 발동 거부. 가드 키가 유지되면
	// WhileInputActive의 매 프레임 재시도가 공격 종료 프레임에 자동으로 가드 진입시킨다
	if (ASC->HasMatchingGameplayTag(AstralGameplayTags::Ability_Attack))
	{
		return false;
	}

	return Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
}

void UAstralGA_Hero_Defend::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	UAbilitySystemComponent* ASC = ActorInfo ? ActorInfo->AbilitySystemComponent.Get() : nullptr;
	if (!ASC)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	// 진입 스태미나 비용 (GE_Cost_Defend) — 공격 직후 이어지는 진입 포함 모든 진입에 동일 적용
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	bDefenseStarted = true;
	bReleasedDuringParry = false;

	// 판정 결과 수신 — ResolveIncomingDamage(서버)가 발송하므로 서버 인스턴스만 실수신
	if (UAbilityTask_WaitGameplayEvent* ParriedTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Parried, nullptr, false, true))
	{
		ParriedTask->EventReceived.AddDynamic(this, &ThisClass::OnParried);
		ParriedTask->ReadyForActivation();
	}
	if (UAbilityTask_WaitGameplayEvent* GuardedTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Guarded, nullptr, false, true))
	{
		GuardedTask->EventReceived.AddDynamic(this, &ThisClass::OnGuarded);
		GuardedTask->ReadyForActivation();
	}

	// 가드 브레이크 감시 (Sprint 패턴)
	StaminaChangedDelegateHandle = ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetStaminaAttribute()).AddUObject(this, &UAstralGA_Hero_Defend::OnStaminaChanged);

	bParryPhase = true;
	SetDefensePhaseTag(AstralGameplayTags::State_Defense_Parrying, true);

	if (UAbilityTask_WaitDelay* ParryTask = UAbilityTask_WaitDelay::WaitDelay(this, ParryWindow))
	{
		ParryTask->OnFinish.AddDynamic(this, &ThisClass::OnParryWindowEnded);
		ParryTask->ReadyForActivation();
	}

	// 릴리즈 종료 — 탭이면 패링 윈도우를 완주한 뒤 종료
	if (UAbilityTask_WaitInputRelease* ReleaseTask = UAbilityTask_WaitInputRelease::WaitInputRelease(this, /*bTestAlreadyReleased=*/true))
	{
		ReleaseTask->OnRelease.AddDynamic(this, &ThisClass::OnInputReleased);
		ReleaseTask->ReadyForActivation();
	}
}

void UAstralGA_Hero_Defend::OnParryWindowEnded()
{
	bParryPhase = false;
	SetDefensePhaseTag(AstralGameplayTags::State_Defense_Parrying, false);

	// 탭 패링 — 윈도우 중 이미 릴리즈됐으면 가드로 전환하지 않고 종료
	if (bReleasedDuringParry)
	{
		EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
		return;
	}

	EnterGuard();
}

void UAstralGA_Hero_Defend::EnterGuard()
{
	SetDefensePhaseTag(AstralGameplayTags::State_Defense_Guarding, true);
}

void UAstralGA_Hero_Defend::OnInputReleased(float TimeHeld)
{
	if (bParryPhase)
	{
		bReleasedDuringParry = true;
		return;
	}

	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}

void UAstralGA_Hero_Defend::OnParried(FGameplayEventData EventData)
{
	// 패링 보상 — 표식(주 축적원) + 오의. 서버 권위 가드는 Apply 헬퍼 내부에서
	ApplyMarkGain(ParryMarkGain);
	ApplyUltGain(ParryUltGain);
}

void UAstralGA_Hero_Defend::OnGuarded(FGameplayEventData EventData)
{
	// 막은 양 비례 스태미나 소모 — 음수 주입은 ApplyStaminaDrain 내부.
	// 고갈 시 가드 브레이크는 스태미나 델리게이트가 처리
	ApplyStaminaDrain(EventData.EventMagnitude * GuardHitStaminaRatio);
}

void UAstralGA_Hero_Defend::OnStaminaChanged(const FOnAttributeChangeData& Data)
{
	// 가드 브레이크 — 재발동은 CanActivateAbility의 임계가 막는다
	if (Data.NewValue <= 0.0f)
	{
		EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
	}
}

void UAstralGA_Hero_Defend::SetDefensePhaseTag(const FGameplayTag& Tag, bool bEnabled) const
{
	if (UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo())
	{
		ASC->SetLooseGameplayTagCount(Tag, bEnabled ? 1 : 0);
	}
}

void UAstralGA_Hero_Defend::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	UAbilitySystemComponent* ASC = ActorInfo ? ActorInfo->AbilitySystemComponent.Get() : nullptr;

	// 페이즈 태그 정리
	SetDefensePhaseTag(AstralGameplayTags::State_Defense_Parrying, false);
	SetDefensePhaseTag(AstralGameplayTags::State_Defense_Guarding, false);
	bParryPhase = false;
	bReleasedDuringParry = false;

	if (ASC && StaminaChangedDelegateHandle.IsValid())
	{
		ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetStaminaAttribute()).Remove(StaminaChangedDelegateHandle);
	}
	StaminaChangedDelegateHandle.Reset();

	// 소비 후 회복 지연 — 진입 비용/가드 피격 소모와 일관 (커밋 실패 종료엔 걸지 않음, Sprint 미러)
	if (bDefenseStarted)
	{
		ApplyRegenBlockEffect(Handle, ActorInfo, ActivationInfo);
	}
	bDefenseStarted = false;

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
