#include "AstralGA_Enemy_MeleeAttack.h"

#include "AIController.h"
#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitDelay.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Animation/AnimMontage.h"
#include "Animation/Notifies/AstralAnimNotify_GameplayEvent.h"
#include "AstralLogChannels.h"
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

	HitEventTag = AstralGameplayTags::GameplayEvent_Enemy_AttackHit;
}

void UAstralGA_Enemy_MeleeAttack::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// InstancedPerActor — 앞 발동의 값이 남아 있다
	ActiveDelayTask = nullptr;
	FocusedController.Reset();
	bSweeping = false;
	bStaggered = false;
	bMontageAttack = (AttackMontage != nullptr);
	ActiveTelegraphDuration = TelegraphDuration;

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

	if (bMontageAttack)
	{
		// 몽타주 방식 — 판정 시점은 타이머가 아니라 몽타주의 타격 노티파이다. 예고 길이도 몽타주에서 읽는다(시간의 원천은 몽타주 하나)
		const float FirstHitTime = FindFirstHitTime();
		if (FirstHitTime >= 0.f)
		{
			ActiveTelegraphDuration = FirstHitTime;
		}
		else
		{
			UE_LOG(LogAstral, Warning, TEXT("%s: 몽타주 %s 에 타격 노티파이(%s)가 없다 — 판정 없이 몽타주만 재생된다"), *GetName(), *GetNameSafe(AttackMontage), *HitEventTag.ToString());
		}

		// 타격은 '마다' 받는다 — 노티파이가 여럿이면 연타
		if (UAbilityTask_WaitGameplayEvent* HitTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, HitEventTag, nullptr, false, true))
		{
			HitTask->EventReceived.AddDynamic(this, &ThisClass::OnMontageHit);
			HitTask->ReadyForActivation();
		}

		// 휘두름 시작(선택) — 준비 구간만 느리게 틀고 여기서 속도를 바꾼다. 이 노티파이가 없는 몽타주(C1 · 마네킹)는 처음 속도 그대로다
		if (UAbilityTask_WaitGameplayEvent* SwingTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Enemy_AttackSwing, nullptr, /*OnlyTriggerOnce=*/true, true))
		{
			SwingTask->EventReceived.AddDynamic(this, &ThisClass::OnMontageSwing);
			SwingTask->ReadyForActivation();
		}

		// 서버에서 재생하면 ASC 가 RepAnimMontageInfo 로 복제한다. 어빌리티가 끝나거나 취소되면 Task 가 몽타주를 멈춘다
		if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, AttackMontage, MontagePlayRate, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
		{
			MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageFinished);
			MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageFinished);
			MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
			MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
			MontageTask->ReadyForActivation();
		}

		if (!IsActive())
		{
			// 재생 실패 — OnMontageInterrupted 가 이미 끝냈다
			return;
		}
	}

	// 타깃은 이벤트 데이터로만 받는다 — 이 어빌리티가 아는 컨트롤러 타입은 엔진의 AAIController 뿐이다. 데이터는 이 호출 동안만 유효하다
	AActor* Target = TriggerEventData ? const_cast<AActor*>(TriggerEventData->Target.Get()) : nullptr;
	AAIController* AIController = Cast<AAIController>(GetControllerFromActorInfo());
	const float TrackDuration = FMath::Min(FacingTrackDuration, ActiveTelegraphDuration);

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
		DrawTelegraph(ActiveTelegraphDuration);
		if (!bMontageAttack)
		{
			WaitThen(ActiveTelegraphDuration, GET_FUNCTION_NAME_CHECKED(ThisClass, OnTelegraphElapsed));
		}
	}
}

void UAstralGA_Enemy_MeleeAttack::OnFacingTrackElapsed()
{
	ActiveDelayTask = nullptr;

	// 포커스가 없으면 컨트롤 회전이 폰 방향을 따라간다 — 여기서 방향이 고정된다
	ClearFacingFocus();

	const float Remaining = ActiveTelegraphDuration - FMath::Min(FacingTrackDuration, ActiveTelegraphDuration);
	if (Remaining > 0.f)
	{
		DrawTelegraph(Remaining);
	}

	if (bMontageAttack)
	{
		// 판정은 몽타주의 타격 노티파이가 낸다
		return;
	}

	if (Remaining > 0.f)
	{
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

	SweepOnce();

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

void UAstralGA_Enemy_MeleeAttack::OnMontageHit(FGameplayEventData EventData)
{
	if (bStaggered)
	{
		// 경직 중 — 몽타주는 이미 멈추는 중이다. 남은 타격은 없다
		return;
	}

	// 첫 타격에서 예고가 끝난다. 추적이 타격 시각까지 이어지고 있었으면 여기서 끊는다 (뒤 타격에서는 전부 no-op)
	if (ActiveDelayTask)
	{
		ActiveDelayTask->EndTask();
		ActiveDelayTask = nullptr;
	}
	ClearTelegraph();
	ClearFacingFocus();

	SweepOnce();

	if (IsActive() && bStaggered)
	{
		// 패링당했다 — 휘두르던 동작을 끊고 경직만큼 머문다. 종료는 경직 타이머가 한다
		MontageStop();
		BeginStaggerRecovery();
	}
}

void UAstralGA_Enemy_MeleeAttack::OnMontageSwing(FGameplayEventData EventData)
{
	if (bStaggered || !IsActive())
	{
		return;
	}

	// 서버에서 바꾸면 ASC 가 RepAnimMontageInfo 의 재생 속도로 복제한다 — 클라이언트도 같은 시점부터 빨라진다
	UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo();
	if (ASC && ASC->GetCurrentMontage() == AttackMontage)
	{
		ASC->CurrentMontageSetPlayRate(SwingPlayRate);
	}
}

void UAstralGA_Enemy_MeleeAttack::OnMontageFinished()
{
	if (bStaggered || !IsActive())
	{
		return;
	}
	FinishAttack();
}

void UAstralGA_Enemy_MeleeAttack::OnMontageInterrupted()
{
	if (bStaggered || !IsActive())
	{
		// 경직에 들어가며 스스로 멈춘 것이거나 이미 끝나는 중이다
		return;
	}
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
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
		// 판정 안에서 온 통지 — 판정이 끝난 뒤 스윕을 부른 쪽(OnTelegraphElapsed · OnMontageHit)이 경직으로 넘긴다
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
	if (bMontageAttack)
	{
		MontageStop();
	}
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

void UAstralGA_Enemy_MeleeAttack::SweepOnce()
{
	// 서버 권위 판정 — 팀 필터/중복 방지/SetByCaller.Damage/instigator 전부 공용 경로가 처리.
	// 방어 판정(패링/가드)은 타겟 HealthSet의 ResolveIncomingDamage에서 일어나고, 패링이면 이 호출 안에서 OnStaggered 가 불린다
	bSweeping = true;
	// 패링당하면 경직 GA(있으면)가 이 호출 안에서 이 어빌리티를 취소한다 — 부른 쪽은 돌아온 뒤 IsActive() 를 본다
	UAstralCombatStatics::ApplyDamageSweep(GetAbilitySystemComponentFromActorInfo(), GetAvatarActorFromActorInfo(), BaseDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel(), DamageTags);
	bSweeping = false;
}

float UAstralGA_Enemy_MeleeAttack::FindFirstHitTime() const
{
	const float Earliest = FindEarliestNotifyTime(HitEventTag);
	return Earliest >= 0.f ? GetSecondsAtMontageTime(Earliest) : -1.f;
}

float UAstralGA_Enemy_MeleeAttack::FindEarliestNotifyTime(const FGameplayTag& EventTag) const
{
	if (!AttackMontage)
	{
		return -1.f;
	}

	float Earliest = -1.f;
	for (const FAnimNotifyEvent& NotifyEvent : AttackMontage->Notifies)
	{
		const UAstralAnimNotify_GameplayEvent* EventNotify = Cast<UAstralAnimNotify_GameplayEvent>(NotifyEvent.Notify);
		if (EventNotify && EventNotify->GetEventTag() == EventTag)
		{
			const float Time = NotifyEvent.GetTriggerTime();
			if (Earliest < 0.f || Time < Earliest)
			{
				Earliest = Time;
			}
		}
	}
	return Earliest;
}

float UAstralGA_Enemy_MeleeAttack::GetSecondsAtMontageTime(float MontageTime) const
{
	const float PrepRate = FMath::Max(MontagePlayRate, UE_KINDA_SMALL_NUMBER);
	const float SwingStart = FindEarliestNotifyTime(AstralGameplayTags::GameplayEvent_Enemy_AttackSwing);
	if (SwingStart < 0.f || MontageTime <= SwingStart)
	{
		return MontageTime / PrepRate;
	}
	return SwingStart / PrepRate + (MontageTime - SwingStart) / FMath::Max(SwingPlayRate, UE_KINDA_SMALL_NUMBER);
}

void UAstralGA_Enemy_MeleeAttack::DrawTelegraph(float Duration) const
{
	if (!bDrawTelegraphDebug)
	{
		return;
	}

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
