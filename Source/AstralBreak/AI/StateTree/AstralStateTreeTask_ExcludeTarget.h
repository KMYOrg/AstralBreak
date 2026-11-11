#pragma once

#include "CoreMinimal.h"
#include "StateTreeTaskBase.h"
#include "AstralStateTreeTask_ExcludeTarget.generated.h"

class AAstralEnemyController;

USTRUCT()
struct FAstralStateTreeTask_ExcludeTargetInstanceData
{
	GENERATED_BODY()

	/** 타깃을 쥔 컨트롤러 — 스키마의 AIControllerClass 가 AAstralEnemyController 여야 자동으로 묶인다 */
	UPROPERTY(EditAnywhere, Category = Context)
	TObjectPtr<AAstralEnemyController> AIController = nullptr;
};

/**
 * 현재 타깃을 잠시 후보에서 뺀다 — 들어올 때 UAstralThreatComponent::ExcludeTarget 을 한 번 부르고 바로 성공으로 끝난다 (Docs/Design/m3-enemy-ai.md §9 ⑥).
 * 추격이 실패한 뒤(닿을 수 없는 타깃) 거치는 상태에 둔다. 빼 두는 시간은 컴포넌트의 ExcludeTime 이고, 다음 AcquireTarget 이 나머지 후보에서 고른다.
 * 타깃 값(CurrentTarget)은 건드리지 않는다 — 비우거나 바꾸는 것은 AcquireTarget 의 몫이다. 틱 없음.
 */
USTRUCT(meta = (DisplayName = "Astral Exclude Target", Category = "Astral|AI"))
struct ASTRALBREAK_API FAstralStateTreeTask_ExcludeTarget : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAstralStateTreeTask_ExcludeTargetInstanceData;

	FAstralStateTreeTask_ExcludeTarget();

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
};
