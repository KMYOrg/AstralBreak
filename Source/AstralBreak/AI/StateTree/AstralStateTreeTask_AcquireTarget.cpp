#include "AstralStateTreeTask_AcquireTarget.h"

#include "Character/Enemy/AstralEnemyController.h"
#include "StateTreeExecutionContext.h"

FAstralStateTreeTask_AcquireTarget::FAstralStateTreeTask_AcquireTarget()
{
	bShouldCallTick = false;
	bShouldCopyBoundPropertiesOnTick = false;
	bShouldCopyBoundPropertiesOnExitState = false;
}

EStateTreeRunStatus FAstralStateTreeTask_AcquireTarget::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	const FInstanceDataType& InstanceData = Context.GetInstanceData(*this);
	if (!InstanceData.AIController)
	{
		return EStateTreeRunStatus::Failed;
	}

	return InstanceData.AIController->AcquireTarget() ? EStateTreeRunStatus::Succeeded : EStateTreeRunStatus::Failed;
}
