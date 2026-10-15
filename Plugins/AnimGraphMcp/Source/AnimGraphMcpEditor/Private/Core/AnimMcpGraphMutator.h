#pragma once

#include "CoreMinimal.h"

class FJsonValue;
class UAnimationAsset;
class UAnimBlueprint;
class UAnimGraphNode_Base;
class UAnimGraphNode_AssetPlayerBase;
class UClass;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;
class UEnum;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 그래프 쓰기 기계 — 노드 생성·분리·핀 연결/해제·속성·애셋·핀 노출. 정책(어느 그래프에 무엇을, 어떤 순서로, 어떻게 되돌리는가)은 AnimMcpOperations 가 가진다.
 * 모든 쓰기 함수는 호출자가 FScopedTransaction 안에서 부른다고 가정하고 Modify() 를 직접 호출한다.
 * 검증 함수(Validate*)는 그래프를 바꾸지 않는다 — Preview 가 그것만 쓴다.
 * 핀 포인터는 ReconstructNode(expose_pin · add_blend_pose · 일부 PostEditChangeProperty) 뒤 무효다 — op 사이에 보관하지 않고 이름으로 재탐색한다.
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

	//~ Phase 3

	/** 두 핀이 연결돼 있는가 (disconnect 검증) */
	bool ValidateLinked(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError);

	/** 스키마 BreakSinglePinLink */
	bool Disconnect(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError);

	/** 스키마 BreakPinLinks — 이 핀의 링크 전부 */
	void DisconnectAll(UEdGraphPin* Pin);

	/** 삭제 가능한 노드인가 — CanUserDeleteNode (Root · StateResult · TransitionResult · Entry 는 false) */
	bool ValidateRemovable(UEdGraphNode* Node, FAnimMcpError& OutError);

	/**
	 * 분리 보관 (2026-10-15 결정) — Graph->RemoveNode(링크 끊기) 로 Nodes 배열에서만 빼고 객체는 유지한다.
	 * 롤백은 ReattachNode, 배치 성공 확정은 FinalizeRemoval. 서브그래프(StateMachine)는 Finalize 때 DestroyNode 가 제거한다
	 */
	void DetachNode(UEdGraphNode* Node);
	void ReattachNode(UEdGraph* Graph, UEdGraphNode* Node);
	void FinalizeRemoval(UEdGraphNode* Node);

	/**
	 * 허용 목록 프로퍼티 설정 — ImportText. OutOldText 는 설정 전 값(ExportText) 으로 롤백에 쓴다.
	 * 적용 뒤 PreEditChange/PostEditChangeProperty 를 불러 노드가 핀 재구성 등 후처리를 하게 한다 (이후 핀 포인터 무효)
	 */
	bool SetPropertyFromJson(UEdGraphNode* Node, FName Property, const TSharedPtr<FJsonValue>& Value, FString& OutOldText, FAnimMcpError& OutError);
	bool SetPropertyFromText(UEdGraphNode* Node, FName Property, const FString& ImportText, FAnimMcpError& OutError);

	/** 클래스만으로 set_property 입력 검증 (Preview · 미생성 ref). 값 변환까지 시도한다 */
	bool ValidatePropertyOnClass(const UClass* NodeClass, FName Property, const TSharedPtr<FJsonValue>& Value, FAnimMcpError& OutError);

	/** 애셋 플레이어의 애셋 교체. OutOld 는 롤백용 (null 가능 — SetAnimationAsset(null) 은 무시되므로 리플렉션으로 되돌린다) */
	bool SetAsset(UAnimGraphNode_Base* Node, UAnimationAsset* Asset, UAnimationAsset*& OutOld, FAnimMcpError& OutError);
	void RestoreAsset(UAnimGraphNode_Base* Node, UAnimationAsset* Old);

	/** ShowPinForProperties 에서 이름으로 인덱스. bCanToggleVisibility 가 아니면 거부 */
	int32 FindOptionalPinIndex(UAnimGraphNode_Base* Node, FName Property, FAnimMcpError& OutError);

	/** SetPinVisibility(ReconstructNode 포함). 이미 같은 상태면 false (no-op) */
	bool SetPinVisible(UAnimGraphNode_Base* Node, FName Property, bool bVisible, FAnimMcpError& OutError, bool* bOutChanged = nullptr);

	/** UseCachedPose → SaveCachedPose 연결 (NodeRef 규칙의 특수 처리). OutOld 롤백용 */
	bool SetCachedPoseSource(UEdGraphNode* UseNode, UEdGraphNode* SaveNode, UEdGraphNode*& OutOld, FAnimMcpError& OutError);
	void RestoreCachedPoseSource(UEdGraphNode* UseNode, UEdGraphNode* Old);

	/** BlendListByEnum 의 enum 바인딩 (add_node 의 'enum'). BoundEnum 설정 + ReconstructNode */
	bool SetBlendListEnum(UEdGraphNode* Node, UEnum* Enum, FAnimMcpError& OutError);

	/**
	 * 포즈 입력 추가 — LayeredBoneBlend(AddPinToBlendByFilter) · BlendListByEnum(ExposeEnumElementAsPin 재현, EnumEntry 필수).
	 * 결과 핀 이름은 재구성 뒤 이름으로 찾는다 (BlendPoses_N / BlendPose_N)
	 */
	bool ValidateAddBlendPose(UEdGraphNode* Node, const FString& EnumEntry, FAnimMcpError& OutError);
	bool AddBlendPose(UEdGraphNode* Node, const FString& EnumEntry, FAnimMcpError& OutError);
	/** 마지막 포즈 제거 — AddBlendPose 롤백 전용 (링크는 호출자가 먼저 복원·해제) */
	void RemoveLastBlendPose(UEdGraphNode* Node);
}
