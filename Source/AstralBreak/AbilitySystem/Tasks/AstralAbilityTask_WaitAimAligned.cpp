#include "AstralAbilityTask_WaitAimAligned.h"

#include "GameFramework/Pawn.h"

UAstralAbilityTask_WaitAimAligned::UAstralAbilityTask_WaitAimAligned(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	bTickingTask = true;
}

UAstralAbilityTask_WaitAimAligned* UAstralAbilityTask_WaitAimAligned::WaitAimAligned(UGameplayAbility* OwningAbility, float InToleranceYaw, float InMaxWaitSeconds)
{
	UAstralAbilityTask_WaitAimAligned* Task = NewAbilityTask<UAstralAbilityTask_WaitAimAligned>(OwningAbility);
	Task->ToleranceYaw = FMath::Max(InToleranceYaw, 0.f);
	Task->MaxWaitSeconds = FMath::Max(InMaxWaitSeconds, 0.f);
	return Task;
}

bool UAstralAbilityTask_WaitAimAligned::IsAimAligned(const APawn* Pawn, float ToleranceYaw)
{
	if (!Pawn || !Pawn->GetController())
	{
		return true;
	}

	const float DeltaYaw = FRotator::NormalizeAxis(Pawn->GetControlRotation().Yaw - Pawn->GetActorRotation().Yaw);
	return FMath::Abs(DeltaYaw) <= ToleranceYaw;
}

void UAstralAbilityTask_WaitAimAligned::TickTask(float DeltaTime)
{
	Super::TickTask(DeltaTime);

	// 첫 판정은 생성 다음 틱 — 호출자가 이미 정렬 여부를 보고(정렬이면 태스크 없이 즉시) 이 태스크를 만든다
	Elapsed += DeltaTime;
	const bool bAligned = IsAimAligned(Cast<APawn>(GetAvatarActor()), ToleranceYaw);
	if (bAligned || Elapsed >= MaxWaitSeconds)
	{
		Finish(/*bTimedOut=*/!bAligned);
	}
}

void UAstralAbilityTask_WaitAimAligned::Finish(bool bTimedOut)
{
	if (ShouldBroadcastAbilityTaskDelegates())
	{
		OnFinished.Broadcast(bTimedOut);
	}
	EndTask();
}
