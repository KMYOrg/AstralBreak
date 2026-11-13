#include "AstralStateTreeTask_EngageSlot.h"

#include "Character/Enemy/AstralEnemyController.h"
#include "StateTreeExecutionContext.h"

FAstralStateTreeTask_EngageSlot::FAstralStateTreeTask_EngageSlot()
{
	bShouldCallTick = true;
	bShouldCopyBoundPropertiesOnTick = false;
	bShouldCopyBoundPropertiesOnExitState = false;
}

EStateTreeRunStatus FAstralStateTreeTask_EngageSlot::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	return UpdateLocation(Context.GetInstanceData(*this)) ? EStateTreeRunStatus::Running : EStateTreeRunStatus::Failed;
}

EStateTreeRunStatus FAstralStateTreeTask_EngageSlot::Tick(FStateTreeExecutionContext& Context, const float DeltaTime) const
{
	// 타깃을 잃었으면 마지막 좌표를 둔다 — 상태를 떠나는 것은 TargetLost 전환이 한다
	UpdateLocation(Context.GetInstanceData(*this));
	return EStateTreeRunStatus::Running;
}

bool FAstralStateTreeTask_EngageSlot::UpdateLocation(FInstanceDataType& InstanceData)
{
	AAstralEnemyController* Controller = InstanceData.AIController;
	const AActor* Target = Controller ? Controller->GetCurrentTarget() : nullptr;
	if (!Target)
	{
		return false;
	}

	// 타깃과 겹쳐 있으면 방위가 없다 — 쥔 자리(없으면 고른다)로 곧장 간다
	float MyBearing = 0.f;
	const bool bHasMyBearing = Controller->GetBearingFromTarget(MyBearing);

	// 자리가 없거나, 타깃이 나를 지나쳐 자리가 반대편이 됐으면 지금 내 쪽에서 고른다. 그 밖에는 쥔 자리를 쓴다
	const bool bSlotIsBehindTarget = Controller->HasEngageSlot() && bHasMyBearing && InstanceData.RepickAngleDegrees > 0.f
		&& FMath::Abs(FMath::FindDeltaAngleDegrees(MyBearing, Controller->GetEngageBearing())) > InstanceData.RepickAngleDegrees;
	if ((!Controller->HasEngageSlot() || bSlotIsBehindTarget) && !Controller->SelectEngageSlot(InstanceData.MinSeparationDegrees))
	{
		return false;
	}

	// 자리가 멀면 고리 바깥을 돈다 — 내 방위에서 자리 쪽으로 DetourAngle 만큼 앞선 점. 가까워지면 자리로 곧장
	float GoalBearing = Controller->GetEngageBearing();
	float GoalRadius = InstanceData.RingRadius;
	if (bHasMyBearing && InstanceData.DetourAngleDegrees > 0.f)
	{
		const float ToSlot = FMath::FindDeltaAngleDegrees(MyBearing, GoalBearing);
		if (FMath::Abs(ToSlot) > InstanceData.DetourAngleDegrees)
		{
			GoalBearing = MyBearing + FMath::Sign(ToSlot) * InstanceData.DetourAngleDegrees;
			GoalRadius = FMath::Max(InstanceData.DetourRadius, InstanceData.RingRadius);
		}
	}

	const float Radians = FMath::DegreesToRadians(GoalBearing);
	InstanceData.Location = Target->GetActorLocation() + FVector(FMath::Cos(Radians), FMath::Sin(Radians), 0.f) * FMath::Max(GoalRadius, 0.f);
	return true;
}
