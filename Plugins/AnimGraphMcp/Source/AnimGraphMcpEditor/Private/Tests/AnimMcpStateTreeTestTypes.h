#pragma once

#include "CoreMinimal.h"
#include "StateTreeEvaluatorBase.h"
#include "AnimMcpStateTreeTestTypes.generated.h"

/**
 * AnimGraphMcp.StateTree.* 시험 전용 Evaluator.
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
