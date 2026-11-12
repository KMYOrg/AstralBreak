#include "AstralStateTreeTask_WaitTagRemoved.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "StateTreeAsyncExecutionContext.h"
#include "StateTreeExecutionContext.h"

FAstralStateTreeTask_WaitTagRemoved::FAstralStateTreeTask_WaitTagRemoved()
{
	bShouldCallTick = false;
	bShouldCopyBoundPropertiesOnTick = false;
	bShouldCopyBoundPropertiesOnExitState = false;
}

EStateTreeRunStatus FAstralStateTreeTask_WaitTagRemoved::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	FInstanceDataType& InstanceData = Context.GetInstanceData(*this);
	InstanceData.AbilitySystem = nullptr;
	InstanceData.TagChangedHandle.Reset();

	UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(InstanceData.Actor);
	if (!ASC || !InstanceData.Tag.IsValid())
	{
		return EStateTreeRunStatus::Failed;
	}

	// 이미 떨어져 있다 — 태그가 붙었다 떨어진 뒤에 이 상태에 들어온 경우(몽타주 없는 피격 반응 등)
	if (!ASC->HasMatchingGameplayTag(InstanceData.Tag))
	{
		return EStateTreeRunStatus::Succeeded;
	}

	// 통지는 트리 틱 밖(어빌리티 종료)에서 온다 — 약한 컨텍스트로 끝낸다
	InstanceData.TagChangedHandle = ASC->RegisterGameplayTagEvent(InstanceData.Tag, EGameplayTagEventType::NewOrRemoved).AddLambda(
		[WeakContext = Context.MakeWeakExecutionContext()](const FGameplayTag, int32 NewCount)
		{
			if (NewCount == 0)
			{
				WeakContext.FinishTask(EStateTreeFinishTaskType::Succeeded);
			}
		});
	InstanceData.AbilitySystem = ASC;
	return EStateTreeRunStatus::Running;
}

void FAstralStateTreeTask_WaitTagRemoved::ExitState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	FInstanceDataType& InstanceData = Context.GetInstanceData(*this);

	if (UAbilitySystemComponent* ASC = InstanceData.AbilitySystem.Get())
	{
		ASC->UnregisterGameplayTagEvent(InstanceData.TagChangedHandle, InstanceData.Tag, EGameplayTagEventType::NewOrRemoved);
	}

	InstanceData.AbilitySystem = nullptr;
	InstanceData.TagChangedHandle.Reset();
}
