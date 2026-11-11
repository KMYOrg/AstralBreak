#include "AstralStateTreeTask_ExcludeTarget.h"

#include "AI/AstralThreatComponent.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "StateTreeExecutionContext.h"

FAstralStateTreeTask_ExcludeTarget::FAstralStateTreeTask_ExcludeTarget()
{
	bShouldCallTick = false;
	bShouldCopyBoundPropertiesOnTick = false;
	bShouldCopyBoundPropertiesOnExitState = false;
}

EStateTreeRunStatus FAstralStateTreeTask_ExcludeTarget::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	const FInstanceDataType& InstanceData = Context.GetInstanceData(*this);
	if (!InstanceData.AIController)
	{
		return EStateTreeRunStatus::Failed;
	}

	// 타깃이 그사이 비었으면(사망 · 파괴) 뺄 것이 없다 — 어느 쪽이든 다음 상태(Acquire)가 다시 고른다
	InstanceData.AIController->GetThreatComponent()->ExcludeTarget(InstanceData.AIController->GetCurrentTarget());
	return EStateTreeRunStatus::Succeeded;
}
