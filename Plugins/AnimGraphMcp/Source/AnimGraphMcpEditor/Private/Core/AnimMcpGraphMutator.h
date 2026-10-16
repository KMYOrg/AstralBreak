#pragma once

#include "CoreMinimal.h"

class FJsonValue;
class UAnimationAsset;
class UAnimBlueprint;
class UAnimGraphNode_Base;
class UAnimGraphNode_AssetPlayerBase;
class UAnimationStateMachineGraph;
class UAnimationTransitionGraph;
class UAnimStateAliasNode;
class UAnimStateConduitNode;
class UAnimStateNode;
class UAnimStateTransitionNode;
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
	 * 분리 보관 (2026-10-15 결정) — 링크를 통지 없이 끊고 Graph->RemoveNode 로 Nodes 배열에서만 빼며 객체는 유지한다.
	 * 롤백은 ReattachNode, 배치 성공 확정은 FinalizeRemoval. 서브그래프(StateMachine·State·Transition)는 Finalize 때 DestroyNode 가 제거한다.
	 * 통지 없이 끊는 이유: 전이 노드는 자기 핀 링크가 0 이 되는 통지를 받으면 스스로 DestroyNode 한다 — 보관 중엔 그 연쇄를 막는다
	 */
	void BreakAllLinksQuietly(UEdGraphNode* Node);
	void DetachNode(UEdGraphNode* Node);
	void ReattachNode(UEdGraph* Graph, UEdGraphNode* Node);
	void FinalizeRemoval(UEdGraphNode* Node);
	/** 이 배치가 만든 노드의 롤백 — 링크를 통지 없이 끊고 DestroyNode */
	void DestroyNodeQuietly(UEdGraphNode* Node);

	//~ State Machine (Phase 4)

	/** StateMachine 노드 → 편집용 상태머신 그래프 (UAnimGraphNode_StateMachineBase::EditorStateMachineGraph) */
	UAnimationStateMachineGraph* ResolveStateMachineGraph(UEdGraphNode* StateMachineNode, FAnimMcpError& OutError);
	UAnimationStateMachineGraph* AsStateMachineGraph(UEdGraph* Graph, FAnimMcpError& OutError);

	/** 상태 이름 검증 — 엔진 이름 검증기(중복·빈 이름·금지 문자). 빈 이름은 통과(자동 이름) */
	bool ValidateStateName(UEdGraphNode* StateNode, const FString& Name, FAnimMcpError& OutError);

	/** 상태 추가 — Creator → Finalize(BoundGraph 자동) → 이름 지정(OnRenameNode = BoundGraph 이름). 이름 거부 시 노드를 남기지 않고 null */
	UAnimStateNode* AddState(UAnimationStateMachineGraph* Graph, const FString& Name, const FVector2D& Position, FAnimMcpError& OutError);

	bool ValidateTransitionEndpoints(UEdGraphNode* From, UEdGraphNode* To, FAnimMcpError& OutError);

	/** 전이 추가 — Creator → Finalize(BoundGraph+TransitionResult 자동) → CreateConnections(From, To). 에디터 드래그 연결과 같은 경로 */
	UAnimStateTransitionNode* AddTransition(UEdGraphNode* From, UEdGraphNode* To, FAnimMcpError& OutError);

	/** Entry → State. 스키마가 이전 Entry 연결을 끊는다 */
	bool SetEntryState(UAnimationStateMachineGraph* Graph, UEdGraphNode* StateNode, FAnimMcpError& OutError);

	/** 상태 노드에 연결된 전이 노드 전부 (remove_node 연쇄 — 에디터도 상태를 지우면 전이가 함께 사라진다) */
	void CollectLinkedTransitions(UEdGraphNode* StateNode, TArray<UEdGraphNode*>& OutTransitions);

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

	//~ Phase 5 (2026-10-16 사용자 확정: VariableGet 노드 · LayerSetup 본 필터)

	/** 변수 참조의 소유 클래스 — SkeletonGeneratedClass → GeneratedClass → ParentClass. Transition Rule 생성기와 공유 */
	UClass* VariableClassOf(UAnimBlueprint* Blueprint);

	/** add_node 의 class 가 변수 Get 노드를 뜻하는가: "K2Node_VariableGet" · "VariableGet" · "/Script/BlueprintGraph.K2Node_VariableGet" */
	bool IsVariableGetClassName(const FString& ClassName);

	/**
	 * 변수 Get 노드를 놓을 수 있는 그래프인가 — AnimGraph 와 상태 내부(UAnimationStateGraph) 만.
	 * 전이 규칙 그래프(UAnimationTransitionGraph)는 도구가 AST 로 소유하므로 거부, 상태머신 그래프는 포즈 그래프가 아니라 거부
	 */
	bool ValidateVariableGetGraph(UEdGraph* Graph, FAnimMcpError& OutError);

	/** BlueprintVisible 프로퍼티 해석 — get_anim_blueprint_info.variables 와 같은 집합. 없으면 BAD_REQUEST */
	FProperty* ResolveVariable(UAnimBlueprint* Blueprint, const FString& Name, FAnimMcpError& OutError);

	/**
	 * UK2Node_VariableGet(self 문맥) 생성 — 규칙 생성기와 같은 SetFromProperty 경로 (K2Node_Variable.h:120). Finalize 가 핀을 만든다.
	 * 출력 핀 이름 = 변수 이름. 포즈 그래프의 스키마(UAnimationGraphSchema : UEdGraphSchema_K2)가 float 핀 → BlendSpace X 등 K2 연결을 허용한다
	 */
	UEdGraphNode* AddVariableGetNode(UEdGraph* Graph, FProperty* Property, UClass* VarClass, const FVector2D& Position, FAnimMcpError& OutError);

	/**
	 * LayeredBoneBlend.LayerSetup 값 검증 (set_property 전). 노드가 LayeredBoneBlend · BlendMode == BranchFilter ·
	 * 항목 수 == 블렌드 포즈 수 + ExtraPoses (같은 배치의 앞선 add_blend_pose 를 Preview 가 더해 준다) · 모든 BoneName 이 TargetSkeleton 에 존재.
	 * 값 형태는 JsonToImportText 가 따로 본다
	 */
	bool ValidateLayerSetup(UEdGraphNode* Node, const TSharedPtr<FJsonValue>& Value, FAnimMcpError& OutError, int32 ExtraPoses = 0);

	//~ Phase 6-1 (Alias · Conduit · 이름 변경)

	/** 이름 검증 — 노드의 MakeNameValidator 로 (상태·conduit·alias: FAnimStateNodeNameValidator, 상태머신 노드: FAnimStateMachineNodeNameValidator). 빈 이름은 통과 */
	bool ValidateNodeName(UEdGraphNode* Node, const FString& Name, FAnimMcpError& OutError);

	/** conduit 추가 — Finalize(PostPlacedNewNode) 가 BoundGraph(UAnimationTransitionGraph + TransitionResult, conduit 스키마) 를 만든다 (AnimStateConduitNode.cpp:69-95). 이름 = BoundGraph 이름 */
	UAnimStateConduitNode* AddConduit(UAnimationStateMachineGraph* Graph, const FString& Name, const FVector2D& Position, FAnimMcpError& OutError);

	/** alias 추가 — 서브그래프 없음, 이름은 StateAliasName (AnimStateAliasNode.cpp:97-105). 대상은 SetAliasTargets 로 */
	UAnimStateAliasNode* AddStateAlias(UAnimationStateMachineGraph* Graph, const FString& Name, const FVector2D& Position, FAnimMcpError& OutError);

	/**
	 * alias 대상 검증 — 전부 같은 상태머신의 실제 상태(UAnimStateNode; conduit·alias 불가, 엔진이 GetNodesOfClassEx<UAnimStateNode> 로만 해석) ·
	 * global 이 아니면 1개 이상 · 들어오는 전이가 있으면 정확히 1개이고 global 아님 (AnimStateAliasNode.cpp:52-55 의 컴파일 오류를 선반영)
	 */
	bool ValidateAliasTargets(UAnimStateAliasNode* Alias, const TArray<UEdGraphNode*>& States, bool bGlobal, FAnimMcpError& OutError);
	void SetAliasTargets(UAnimStateAliasNode* Alias, const TArray<UEdGraphNode*>& States, bool bGlobal, TArray<UEdGraphNode*>& OutOldStates, bool& bOutOldGlobal);

	/** 전이의 대상이 될 수 있는 노드인가 — alias 는 단일 대상 & global 아님 (같은 컴파일 규칙) */
	bool ValidateTransitionTarget(UEdGraphNode* To, FAnimMcpError& OutError);

	/** 이름 변경 — 상태·conduit·alias(OnRenameNode) 와 상태머신 노드(UAnimGraphNode_StateMachineBase::OnRenameNode = RenameGraph). OutOld 는 롤백용 */
	bool RenameNode(UEdGraphNode* Node, const FString& Name, FString& OutOld, FAnimMcpError& OutError);

	/** 전이 또는 conduit 의 규칙 그래프. 그 외 null */
	UAnimationTransitionGraph* RuleGraphOf(UEdGraphNode* Node);
}
