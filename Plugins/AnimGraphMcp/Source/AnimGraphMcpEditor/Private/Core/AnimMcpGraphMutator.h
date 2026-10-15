#pragma once

#include "CoreMinimal.h"

class UAnimationAsset;
class UAnimBlueprint;
class UAnimGraphNode_Base;
class UClass;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 그래프 쓰기 기계 — 노드 생성·핀 연결. 정책(어느 그래프에 무엇을, 어떤 순서로)은 AnimMcpOperations 가 가진다.
 * 모든 쓰기 함수는 호출자가 FScopedTransaction 안에서 부른다고 가정하고 Modify() 를 직접 호출한다.
 * 검증 함수(Validate*)는 그래프를 바꾸지 않는다 — Preview 가 그것만 쓴다.
 */
namespace AnimMcpGraphMutator
{
	/** 문자열 → FGuid. 실패 시 BAD_REQUEST */
	bool ParseGuid(const FString& Text, FGuid& OutGuid, FAnimMcpError& OutError, const TCHAR* What);

	UEdGraph* FindGraph(UAnimBlueprint* Blueprint, const FString& GraphGuid, FAnimMcpError& OutError);
	UEdGraphNode* FindNode(UAnimBlueprint* Blueprint, const FString& NodeGuid, FAnimMcpError& OutError);
	UEdGraphPin* FindPin(UEdGraphNode* Node, const FString& PinName, FAnimMcpError& OutError);

	/** UAnimGraphNode_Base 파생·비추상 클래스만. "AnimGraphNode_SequencePlayer" 또는 "/Script/AnimGraph.AnimGraphNode_SequencePlayer" */
	UClass* ResolveNodeClass(const FString& ClassName, FAnimMcpError& OutError);

	/** 애셋 플레이어 노드가 이 애셋을 받을 수 있는가 (SupportsAssetClass) + 스켈레톤 일치 경고 */
	bool ValidateNodeAsset(UClass* NodeClass, UAnimationAsset* Asset, UAnimBlueprint* Blueprint, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** 스키마 CanCreateConnection — MAKE·PROMOTION·BREAK_OTHERS 허용, DISALLOW·CONVERSION_NODE 거부 */
	bool ValidateConnection(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError);

	/** FGraphNodeCreator 경로 — Finalize 가 Guid·PostPlacedNewNode(서브그래프)·기본 핀을 만든다 */
	UAnimGraphNode_Base* AddNode(UEdGraph* Graph, UClass* NodeClass, const FVector2D& Position, UAnimationAsset* Asset, FAnimMcpError& OutError);

	/** 스키마 TryCreateConnection — 기존 단일 링크는 스키마가 끊고 다시 잇는다 */
	bool Connect(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError);
}
