#include "AstralStateTreeTask_ActivateAbility.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "Abilities/GameplayAbilityTypes.h"
#include "GameplayAbilitySpec.h"
#include "StateTreeAsyncExecutionContext.h"
#include "StateTreeExecutionContext.h"

FAstralStateTreeTask_ActivateAbility::FAstralStateTreeTask_ActivateAbility()
{
	bShouldCallTick = false;
	bShouldCopyBoundPropertiesOnTick = false;
	bShouldCopyBoundPropertiesOnExitState = false;
}

EStateTreeRunStatus FAstralStateTreeTask_ActivateAbility::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	FInstanceDataType& InstanceData = Context.GetInstanceData(*this);
	InstanceData.AbilitySystem = nullptr;
	InstanceData.AbilityHandle = FGameplayAbilitySpecHandle();
	InstanceData.AbilityEndedHandle.Reset();
	InstanceData.RunState.Reset();

	UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(InstanceData.Actor);
	if (!ASC || !InstanceData.AbilityTag.IsValid())
	{
		return EStateTreeRunStatus::Failed;
	}

	// 태그 요건(차단 태그 등)은 여기서 거르지 않는다 — '스펙 없음' 과 '발동 거부' 는 둘 다 실패지만 거부 판단은 발동 경로 한 곳에 둔다
	TArray<FGameplayAbilitySpec*> MatchingSpecs;
	ASC->GetActivatableGameplayAbilitySpecsByAllMatchingTags(FGameplayTagContainer(InstanceData.AbilityTag), MatchingSpecs, /*bOnlyAbilitiesThatSatisfyTagRequirements=*/false);
	if (MatchingSpecs.IsEmpty() || !MatchingSpecs[0])
	{
		return EStateTreeRunStatus::Failed;
	}
	const FGameplayAbilitySpecHandle Handle = MatchingSpecs[0]->Handle;

	// 발동 호출 안에서 끝나는 경우(즉시 종료 · 발동 직후 취소)를 놓치지 않게 먼저 구독한다.
	// EnterState 안에서는 약한 컨텍스트로 Task 를 끝낼 수 없어, 그 경우는 RunState 에 적어 두고 아래에서 직접 돌려준다
	const TSharedRef<FAstralAbilityRunState> RunState = MakeShared<FAstralAbilityRunState>();
	const FDelegateHandle EndedHandle = ASC->OnAbilityEnded.AddLambda(
		[WeakContext = Context.MakeWeakExecutionContext(), Handle, RunState](const FAbilityEndedData& EndedData)
		{
			if (EndedData.AbilitySpecHandle != Handle || RunState->bEnded)
			{
				return;
			}
			RunState->bEnded = true;
			RunState->bWasCancelled = EndedData.bWasCancelled;

			if (!RunState->bInEnterState)
			{
				WeakContext.FinishTask(EndedData.bWasCancelled ? EStateTreeFinishTaskType::Failed : EStateTreeFinishTaskType::Succeeded);
			}
		});

	FGameplayEventData Payload;
	Payload.EventTag = InstanceData.AbilityTag;
	Payload.Instigator = InstanceData.Actor;
	Payload.Target = InstanceData.TargetActor;

	// 스펙을 직접 지정한다. 엔진은 태그를 EventTag 에 찍기만 하고 라우팅하지 않는다
	const bool bActivated = ASC->TriggerAbilityFromGameplayEvent(Handle, ASC->AbilityActorInfo.Get(), InstanceData.AbilityTag, &Payload, *ASC);
	RunState->bInEnterState = false;

	if (!bActivated || RunState->bEnded)
	{
		ASC->OnAbilityEnded.Remove(EndedHandle);
		return (bActivated && !RunState->bWasCancelled) ? EStateTreeRunStatus::Succeeded : EStateTreeRunStatus::Failed;
	}

	InstanceData.AbilitySystem = ASC;
	InstanceData.AbilityHandle = Handle;
	InstanceData.AbilityEndedHandle = EndedHandle;
	InstanceData.RunState = RunState;
	return EStateTreeRunStatus::Running;
}

void FAstralStateTreeTask_ActivateAbility::ExitState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	FInstanceDataType& InstanceData = Context.GetInstanceData(*this);

	if (UAbilitySystemComponent* ASC = InstanceData.AbilitySystem.Get())
	{
		// 구독을 먼저 푼다 — 아래 취소가 끝낸 것을 다시 이 Task 의 완료로 받지 않는다
		ASC->OnAbilityEnded.Remove(InstanceData.AbilityEndedHandle);

		// 이 발동이 아직 살아 있을 때만 취소한다. 사망 · 정상 종료 뒤에는 이미 끝나 있다
		if (InstanceData.RunState.IsValid() && !InstanceData.RunState->bEnded)
		{
			ASC->CancelAbilityHandle(InstanceData.AbilityHandle);
		}
	}

	InstanceData.AbilitySystem = nullptr;
	InstanceData.AbilityHandle = FGameplayAbilitySpecHandle();
	InstanceData.AbilityEndedHandle.Reset();
	InstanceData.RunState.Reset();
}
