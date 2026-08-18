#include "AstralGA_Enemy_TelegraphAttack.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_WaitDelay.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Character/Enemy/AstralCombatCharacter.h"

UAstralGA_Enemy_TelegraphAttack::UAstralGA_Enemy_TelegraphAttack(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
	ActivationPolicy   = EAstralAbilityActivationPolicy::OnSpawn;

	// asset tag — 사망 시 CancelAbilities(SurvivesDeath 제외)에 걸려 루프가 정리된다
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Attack);
	SetAssetTags(AssetTags);
}

void UAstralGA_Enemy_TelegraphAttack::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 패링당함 통지 — 사이클마다 반복 수신 (ResolveIncomingDamage가 공격자에게 발송)
	if (UAbilityTask_WaitGameplayEvent* StaggeredTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Staggered, nullptr, false, true))
	{
		StaggeredTask->EventReceived.AddDynamic(this, &ThisClass::OnStaggered);
		StaggeredTask->ReadyForActivation();
	}

	StartCycle();
}

void UAstralGA_Enemy_TelegraphAttack::StartCycle()
{
	ActiveDelayTask = UAbilityTask_WaitDelay::WaitDelay(this, AttackInterval);
	if (ActiveDelayTask)
	{
		ActiveDelayTask->OnFinish.AddDynamic(this, &ThisClass::OnIntervalElapsed);
		ActiveDelayTask->ReadyForActivation();
	}
}

void UAstralGA_Enemy_TelegraphAttack::OnIntervalElapsed()
{
	ActiveDelayTask = nullptr;

	// 토글 확인 — 꺼져 있으면 이번 사이클은 건너뛰고 다음 주기에 재확인 (레벨에서 런타임 토글 가능)
	AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(GetAvatarActorFromActorInfo());
	if (!CombatCharacter || !CombatCharacter->IsTelegraphAttackEnabled())
	{
		StartCycle();
		return;
	}

	bTelegraphing = true;
	if (UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo())
	{
		ASC->SetLooseGameplayTagCount(AstralGameplayTags::State_Telegraphing, 1);
	}

	// 전 머신 표시 — 서버 로컬 DrawDebug는 클라 뷰포트에 안 보이므로 멀티캐스트 (클라 패링 타이밍 검증용)
	CombatCharacter->MulticastDrawTelegraphDebug(TelegraphDuration, TraceStartOffset, TraceDistance, TraceRadius);

	ActiveDelayTask = UAbilityTask_WaitDelay::WaitDelay(this, TelegraphDuration);
	if (ActiveDelayTask)
	{
		ActiveDelayTask->OnFinish.AddDynamic(this, &ThisClass::OnTelegraphElapsed);
		ActiveDelayTask->ReadyForActivation();
	}
}

void UAstralGA_Enemy_TelegraphAttack::OnTelegraphElapsed()
{
	ActiveDelayTask = nullptr;
	ClearTelegraph();

	// 서버 권위 판정 — 팀 필터/중복 방지/SetByCaller.Damage/instigator 전부 공용 경로가 처리.
	// 방어 판정(패링/가드)은 타겟 HealthSet의 ResolveIncomingDamage에서 일어난다
	UAstralCombatStatics::ApplyDamageSweep(GetAbilitySystemComponentFromActorInfo(), GetAvatarActorFromActorInfo(), BaseDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel());

	StartCycle();
}

void UAstralGA_Enemy_TelegraphAttack::OnStaggered(FGameplayEventData EventData)
{
	// 진행 중이던 대기/텔레그래프 중단 — 패링 성공이 눈에 보이는 반응
	if (ActiveDelayTask)
	{
		ActiveDelayTask->EndTask();
		ActiveDelayTask = nullptr;
	}
	ClearTelegraph();

	ActiveDelayTask = UAbilityTask_WaitDelay::WaitDelay(this, StaggerRecovery);
	if (ActiveDelayTask)
	{
		ActiveDelayTask->OnFinish.AddDynamic(this, &ThisClass::OnStaggerRecovered);
		ActiveDelayTask->ReadyForActivation();
	}
}

void UAstralGA_Enemy_TelegraphAttack::OnStaggerRecovered()
{
	ActiveDelayTask = nullptr;
	StartCycle();
}

void UAstralGA_Enemy_TelegraphAttack::ClearTelegraph()
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

void UAstralGA_Enemy_TelegraphAttack::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	ClearTelegraph();
	ActiveDelayTask = nullptr;

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
