#pragma once

#include "CoreMinimal.h"
#include "StateTreeTaskBase.h"
#include "AstralStateTreeTask_AcquireTarget.generated.h"

class AAstralEnemyController;

USTRUCT()
struct FAstralStateTreeTask_AcquireTargetInstanceData
{
	GENERATED_BODY()

	/** 타깃을 쥔 컨트롤러 — 스키마의 AIControllerClass 가 AAstralEnemyController 여야 자동으로 묶인다 */
	UPROPERTY(EditAnywhere, Category = Context)
	TObjectPtr<AAstralEnemyController> AIController = nullptr;
};

/**
 * 타깃을 고른다 — 들어올 때 AAstralEnemyController::AcquireTarget 을 한 번 부르고 바로 끝난다 (Docs/Design/m3-enemy-ai.md §8 ②).
 * 타깃이 있으면 성공, 없으면 실패. 고른 값은 컨트롤러의 CurrentTarget 에 있고, 뒤 상태의 Task 가 그 값에 바인딩해 읽는다.
 * 이 Task 가 놓인 상태가 '타깃을 다시 고르는 시점' 이다 — 매 틱 고르지 않는다. 틱 없음.
 */
USTRUCT(meta = (DisplayName = "Astral Acquire Target", Category = "Astral|AI"))
struct ASTRALBREAK_API FAstralStateTreeTask_AcquireTarget : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAstralStateTreeTask_AcquireTargetInstanceData;

	FAstralStateTreeTask_AcquireTarget();

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
};
