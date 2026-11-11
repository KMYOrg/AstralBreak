#include "AstralGA_Enemy_MeleeAttack.h"

#include "AIController.h"
#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_WaitDelay.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Character/Enemy/AstralCombatCharacter.h"

UAstralGA_Enemy_MeleeAttack::UAstralGA_Enemy_MeleeAttack(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
	ActivationPolicy   = EAstralAbilityActivationPolicy::Manual;

	// Ability.Attack — 사망 시 CancelAbilities(SurvivesDeath 제외)에 걸린다. Ability.Enemy.Attack.Melee — StateTree Task 가 스펙을 찾는 키
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Attack);
	AssetTags.AddTag(AstralGameplayTags::Ability_Enemy_Attack_Melee);
	SetAssetTags(AssetTags);
}

void UAstralGA_Enemy_MeleeAttack::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// InstancedPerActor — 앞 발동의 값이 남아 있다
	ActiveDelayTask = nullptr;
	FocusedController.Reset();
	bSweeping = false;
	bStaggered = false;

	// 패링당함 통지 (ResolveIncomingDamage 가 공격자에게 발송) — 스윕 호출 안에서 동기로 온다
	if (UAbilityTask_WaitGameplayEvent* StaggeredTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Staggered, nullptr, false, true))
	{
		StaggeredTask->EventReceived.AddDynamic(this, &ThisClass::OnStaggered);
		StaggeredTask->ReadyForActivation();
	}

	bTelegraphing = true;
	if (UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo())
	{
		ASC->SetLooseGameplayTagCount(AstralGameplayTags::State_Telegraphing, 1);
	}

	// 타깃은 이벤트 데이터로만 받는다 — 이 어빌리티가 아는 컨트롤러 타입은 엔진의 AAIController 뿐이다. 데이터는 이 호출 동안만 유효하다
	AActor* Target = TriggerEventData ? const_cast<AActor*>(TriggerEventData->Target.Get()) : nullptr;
	AAIController* AIController = Cast<AAIController>(GetControllerFromActorInfo());
	const float TrackDuration = FMath::Min(FacingTrackDuration, TelegraphDuration);

	if (Target && AIController && TrackDuration > 0.f)
	{
		// 예고 앞부분 — 타깃을 따라 돈다. Gameplay 우선순위라 이동 포커스보다 앞선다
		AIController->SetFocus(Target, EAIFocusPriority::Gameplay);
		FocusedController = AIController;

		DrawTelegraph(TrackDuration);
		WaitThen(TrackDuration, GET_FUNCTION_NAME_CHECKED(ThisClass, OnFacingTrackElapsed));
	}
	else
	{
		// 타깃 없이 발동 — 지금 방향 그대로 친다
		DrawTelegraph(TelegraphDuration);
		WaitThen(TelegraphDuration, GET_FUNCTION_NAME_CHECKED(ThisClass, OnTelegraphElapsed));
	}
}

void UAstralGA_Enemy_MeleeAttack::OnFacingTrackElapsed()
{
	ActiveDelayTask = nullptr;

	// 포커스가 없으면 컨트롤 회전이 폰 방향을 따라간다 — 여기서 방향이 고정된다
	ClearFacingFocus();

	const float Remaining = TelegraphDuration - FMath::Min(FacingTrackDuration, TelegraphDuration);
	if (Remaining > 0.f)
	{
		DrawTelegraph(Remaining);
		WaitThen(Remaining, GET_FUNCTION_NAME_CHECKED(ThisClass, OnTelegraphElapsed));
	}
	else
	{
		OnTelegraphElapsed();
	}
}

void UAstralGA_Enemy_MeleeAttack::OnTelegraphElapsed()
{
	ActiveDelayTask = nullptr;
	ClearTelegraph();
	ClearFacingFocus();

	// 서버 권위 판정 — 팀 필터/중복 방지/SetByCaller.Damage/instigator 전부 공용 경로가 처리.
	// 방어 판정(패링/가드)은 타겟 HealthSet의 ResolveIncomingDamage에서 일어나고, 패링이면 이 호출 안에서 OnStaggered 가 불린다
	bSweeping = true;
	UAstralCombatStatics::ApplyDamageSweep(GetAbilitySystemComponentFromActorInfo(), GetAvatarActorFromActorInfo(), BaseDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel());
	bSweeping = false;

	if (!IsActive())
	{
		return;
	}

	if (bStaggered)
	{
		BeginStaggerRecovery();
	}
	else
	{
		FinishAttack();
	}
}

void UAstralGA_Enemy_MeleeAttack::OnStaggered(FGameplayEventData EventData)
{
	if (bStaggered)
	{
		return;
	}
	bStaggered = true;

	if (bSweeping)
	{
		// 판정 안에서 온 통지 — 판정이 끝난 뒤 OnTelegraphElapsed 가 경직으로 넘긴다
		return;
	}

	// 판정 전에 온 경직 — 예고를 끊고 바로 경직으로
	if (ActiveDelayTask)
	{
		ActiveDelayTask->EndTask();
		ActiveDelayTask = nullptr;
	}
	ClearTelegraph();
	ClearFacingFocus();
	BeginStaggerRecovery();
}

void UAstralGA_Enemy_MeleeAttack::BeginStaggerRecovery()
{
	if (StaggerRecovery > 0.f)
	{
		WaitThen(StaggerRecovery, GET_FUNCTION_NAME_CHECKED(ThisClass, OnStaggerRecovered));
	}
	else
	{
		FinishAttack();
	}
}

void UAstralGA_Enemy_MeleeAttack::OnStaggerRecovered()
{
	ActiveDelayTask = nullptr;
	FinishAttack();
}

void UAstralGA_Enemy_MeleeAttack::WaitThen(float DelaySeconds, FName CallbackName)
{
	ActiveDelayTask = UAbilityTask_WaitDelay::WaitDelay(this, DelaySeconds);
	if (ActiveDelayTask)
	{
		FScriptDelegate Callback;
		Callback.BindUFunction(this, CallbackName);
		ActiveDelayTask->OnFinish.Add(Callback);
		ActiveDelayTask->ReadyForActivation();
	}
}

void UAstralGA_Enemy_MeleeAttack::DrawTelegraph(float Duration) const
{
	// 전 머신 표시 — 서버 로컬 DrawDebug는 클라 뷰포트에 안 보이므로 멀티캐스트. 각 머신이 그 시점의 폰 방향으로 그린다
	if (AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(GetAvatarActorFromActorInfo()))
	{
		CombatCharacter->MulticastDrawTelegraphDebug(Duration, TraceStartOffset, TraceDistance, TraceRadius);
	}
}

void UAstralGA_Enemy_MeleeAttack::ClearTelegraph()
{
	if (!bTelegraphing)
	{
		return;
	}
	bTelegraphing = false;

	if (UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo())
	{
		ASC->SetLooseGameplayTagCount(AstralGameplayTags::State_Telegraphing, 0);
	}
}

void UAstralGA_Enemy_MeleeAttack::ClearFacingFocus()
{
	if (AAIController* AIController = FocusedController.Get())
	{
		AIController->ClearFocus(EAIFocusPriority::Gameplay);
	}
	FocusedController.Reset();
}

void UAstralGA_Enemy_MeleeAttack::FinishAttack()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}

void UAstralGA_Enemy_MeleeAttack::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	ClearTelegraph();
	ClearFacingFocus();
	ActiveDelayTask = nullptr;

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
