#include "AstralGA_Enemy_Stagger.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitDelay.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Animation/AnimMontage.h"
#include "GameplayEffect.h"

UAstralGA_Enemy_Stagger::UAstralGA_Enemy_Stagger(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
	ActivationPolicy   = EAstralAbilityActivationPolicy::Manual;

	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Enemy_Stagger);
	SetAssetTags(AssetTags);

	// 켜져 있는 동안 행동 불가 — 피격 반응의 발동을 막고, 컨트롤러가 이 태그의 변화를 트리에 알린다.
	// 발동 차단에는 넣지 않는다: 움찔하는 중(같은 태그)에도 경직은 들어가야 한다. 경직 중의 재발동은 InstancedPerActor 가 막는다
	ActivationOwnedTags.AddTag(AstralGameplayTags::State_Enemy_Staggered);

	if (HasAnyFlags(RF_ClassDefaultObject))
	{
		// 패링당함 (UAstralCombatStatics::ResolveIncomingDamage 가 공격자에게 발송)
		FAbilityTriggerData TriggerData;
		TriggerData.TriggerTag = AstralGameplayTags::GameplayEvent_Staggered;
		TriggerData.TriggerSource = EGameplayAbilityTriggerSource::GameplayEvent;
		AbilityTriggers.Add(TriggerData);
	}
}

void UAstralGA_Enemy_Stagger::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// InstancedPerActor — 앞 발동의 값이 남아 있다
	ExposedEffectHandle.Invalidate();

	UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo();
	if (!ASC)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	// 휘두르던 공격(연타의 남은 타격 포함)과 움찔을 끊는다 — 그 몽타주는 각 어빌리티의 Task 가 멈춘다.
	// 이 발동은 공격 GA 의 스윕 호출 안에서 온다: 공격 GA 는 스윕에서 돌아온 뒤 IsActive() 를 보고 물러난다
	FGameplayTagContainer CancelTags;
	CancelTags.AddTag(AstralGameplayTags::Ability_Attack);
	CancelTags.AddTag(AstralGameplayTags::Ability_Enemy_HitReact);
	ASC->CancelAbilities(&CancelTags, nullptr, this);

	// 약점 노출 — 끝날 때(EndAbility — 시간 종료 · 사망 취소 모두) 뗀다
	if (ExposedEffectClass)
	{
		ExposedEffectHandle = ApplyGameplayEffectToOwner(Handle, ActorInfo, ActivationInfo, ExposedEffectClass.GetDefaultObject(), GetAbilityLevel());
	}

	// 서버에서 재생하면 ASC 가 복제한다. 종료는 몽타주가 아니라 아래 타이머가 정한다 — 몽타주가 먼저 끝나도 경직은 이어진다
	if (StaggerMontage)
	{
		if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, StaggerMontage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
		{
			MontageTask->ReadyForActivation();
		}
	}

	if (UAbilityTask_WaitDelay* WaitTask = UAbilityTask_WaitDelay::WaitDelay(this, StaggerDuration))
	{
		WaitTask->OnFinish.AddDynamic(this, &ThisClass::OnStaggerElapsed);
		WaitTask->ReadyForActivation();
	}
}

void UAstralGA_Enemy_Stagger::OnStaggerElapsed()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}

void UAstralGA_Enemy_Stagger::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	if (ExposedEffectHandle.IsValid())
	{
		if (UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo())
		{
			ASC->RemoveActiveGameplayEffect(ExposedEffectHandle);
		}
		ExposedEffectHandle.Invalidate();
	}

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
