#include "AstralGA_Enemy_HitReact.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "Animation/AnimMontage.h"
#include "Engine/World.h"

UAstralGA_Enemy_HitReact::UAstralGA_Enemy_HitReact(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
	ActivationPolicy   = EAstralAbilityActivationPolicy::Manual;

	// Ability.Attack 이 아니다 — 경직 GA 가 이 태그로 찾아 취소한다. 사망 때는 CancelAbilities(SurvivesDeath 제외)에 걸린다
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Enemy_HitReact);
	SetAssetTags(AssetTags);

	// 켜져 있는 동안 행동 불가 — 컨트롤러가 이 태그의 변화를 트리에 알린다
	ActivationOwnedTags.AddTag(AstralGameplayTags::State_Enemy_Staggered);

	// 버팀 — 공격 중, 경직 중(또는 이미 움찔하는 중). 사망은 베이스가 막는다
	ActivationBlockedTags.AddTag(AstralGameplayTags::State_Enemy_Attacking);
	ActivationBlockedTags.AddTag(AstralGameplayTags::State_Enemy_Staggered);

	if (HasAnyFlags(RF_ClassDefaultObject))
	{
		// 피해를 받을 때마다 (UAstralHealthSet::PostGameplayEffectExecute 가 서버에서 발송)
		FAbilityTriggerData TriggerData;
		TriggerData.TriggerTag = AstralGameplayTags::GameplayEvent_Damaged;
		TriggerData.TriggerSource = EGameplayAbilityTriggerSource::GameplayEvent;
		AbilityTriggers.Add(TriggerData);
	}
}

bool UAstralGA_Enemy_HitReact::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags))
	{
		return false;
	}

	// 간격 — InstancedPerActor 라 엔진이 이 판정을 인스턴스에 묻는다(CDO 에서는 LastReactTime 이 음수라 통과)
	const UWorld* World = ActorInfo->AbilitySystemComponent->GetWorld();
	if (World && LastReactTime >= 0.0 && World->GetTimeSeconds() - LastReactTime < MinInterval)
	{
		return false;
	}

	// 죽는 타격에는 움찔하지 않는다 — Damaged 이벤트는 사망 처리(State.Death)보다 먼저 올 수 있다
	const UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();
	if (ASC->HasAttributeSetForAttribute(UAstralHealthSet::GetHealthAttribute()) && ASC->GetNumericAttribute(UAstralHealthSet::GetHealthAttribute()) <= 0.f)
	{
		return false;
	}

	return true;
}

void UAstralGA_Enemy_HitReact::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	if (const UWorld* World = GetWorld())
	{
		LastReactTime = World->GetTimeSeconds();
	}

	// 가해자 = 이벤트의 Instigator (이펙트 컨텍스트의 Instigator — 프로젝트의 피해 경로는 여기에 폰을 싣는다). 데이터는 이 호출 동안만 유효하다
	UAnimMontage* Montage = SelectReactMontage(TriggerEventData ? TriggerEventData->Instigator.Get() : nullptr);
	if (!Montage)
	{
		// 몽타주가 없는 적 — 간격만 소모하고 끝낸다
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
		return;
	}

	// 서버에서 재생하면 ASC 가 복제한다. 어빌리티가 끝나거나 취소되면(경직 · 사망) Task 가 몽타주를 멈춘다
	if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, Montage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
	{
		MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnReactMontageFinished);
		MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnReactMontageFinished);
		MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnReactMontageInterrupted);
		MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnReactMontageInterrupted);
		MontageTask->ReadyForActivation();
	}
}

void UAstralGA_Enemy_HitReact::OnReactMontageFinished()
{
	if (IsActive())
	{
		EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
	}
}

void UAstralGA_Enemy_HitReact::OnReactMontageInterrupted()
{
	if (IsActive())
	{
		EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
	}
}

UAnimMontage* UAstralGA_Enemy_HitReact::SelectReactMontage(const AActor* Attacker) const
{
	UAnimMontage* Picked = FrontMontage;

	const AActor* Avatar = GetAvatarActorFromActorInfo();
	if (Avatar && Attacker && Attacker != Avatar)
	{
		// 2D — 높이차 무시 (방어 정면 판정과 같은 기준)
		const FVector ToAttacker = (Attacker->GetActorLocation() - Avatar->GetActorLocation()).GetSafeNormal2D();
		if (!ToAttacker.IsNearlyZero())
		{
			const double ForwardDot = FVector::DotProduct(Avatar->GetActorForwardVector(), ToAttacker);
			const double RightDot = FVector::DotProduct(Avatar->GetActorRightVector(), ToAttacker);
			if (FMath::Abs(ForwardDot) >= FMath::Abs(RightDot))
			{
				Picked = ForwardDot >= 0.0 ? FrontMontage : BackMontage;
			}
			else
			{
				Picked = RightDot >= 0.0 ? RightMontage : LeftMontage;
			}
		}
	}

	return Picked ? Picked : FrontMontage.Get();
}
