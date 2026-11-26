#pragma once

#include "CoreMinimal.h"
#include "StateTreeEvaluatorBase.h"
#include "StateTreeTaskBase.h"
#include "AnimMcpStateTreeTestTypes.generated.h"

/**
 * StateTreeMcp.* 시험 전용 Evaluator (2026-11-14 AnimGraphMcp 에서 이전 — 옛 /Script/AnimGraphMcpEditor 경로는 DefaultEngine.ini [CoreRedirects]).
 * 엔진에는 AI 스키마가 허용하는 구체 Evaluator 가 없다(BP 래퍼 · 테스트 스위트뿐) — M3 의 프로젝트 Evaluator 와 같은 경로를 시험하려고 둔다.
 * USTRUCT 는 #if 로 감쌀 수 없어 항상 빌드되지만 meta=Hidden 이라 에디터 노드 선택기에 나오지 않는다.
 */
USTRUCT()
struct FAnimMcpTestEvaluatorInstanceData
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, Category = Parameter)
	float Scale = 1.0f;

	UPROPERTY(EditAnywhere, Category = Output)
	FVector OutLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, Category = Output)
	bool bOutFlag = false;
};

USTRUCT(meta = (Hidden, DisplayName = "AnimMcp Test Evaluator"))
struct FAnimMcpTestEvaluator : public FStateTreeEvaluatorCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAnimMcpTestEvaluatorInstanceData;

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
};

USTRUCT()
struct FAnimMcpLifecycleProbeInstanceData
{
	GENERATED_BODY()

	/** 기록에 실을 이름 — 어느 상태의 프로브인지 가른다 */
	UPROPERTY(EditAnywhere, Category = Parameter)
	FString Label;

	/** EnterState 에서 실제로 활성화해 볼 GA 클래스 경로. 비면 시도하지 않는다 */
	UPROPERTY(EditAnywhere, Category = Parameter)
	FString AbilityPath;
};

/**
 * 생명주기 프로브 — EnterState · ExitState 호출과 그 시점의 폰 · ASC 상태를 observed.probe 에 남긴다.
 * 타임라인은 상태 이름만 보여 주므로 '첫 상태에서 GA 를 쓸 수 있는가' · '정지 때 ExitState 가 불리는가' 를 여기서 본다 (Docs/Design/m3-enemy-ai.md §1-7).
 * 끝나지 않는 작업이다. 다른 작업과 한 상태에 두면 상태의 완료는 그 작업이 정한다.
 */
USTRUCT(meta = (Hidden, DisplayName = "AnimMcp Lifecycle Probe"))
struct FAnimMcpLifecycleProbeTask : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAnimMcpLifecycleProbeInstanceData;

	FAnimMcpLifecycleProbeTask();

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
	virtual void ExitState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
};
