#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimBlueprint;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;
struct FAnimMcpContext;

/**
 * 읽기 전용 — AnimBP 의 그래프 계층을 JSON 으로. 쓰지 않는다 (Preview/Apply 분리의 코드상 표현).
 * 그래프 트리 · 변수 · 노드/핀/연결 · 허용 목록 프로퍼티 값 · 바인딩 보유 · revision.
 */
namespace AnimMcpGraphInspector
{
	struct FGraphRecord
	{
		UEdGraph* Graph = nullptr;
		UEdGraph* ParentGraph = nullptr;
	};

	/** 최상위(FunctionGraphs · UbergraphPages · MacroGraphs) + 모든 하위 그래프를 깊이 우선으로. 부모 관계를 함께 돌려준다 */
	void CollectGraphs(UAnimBlueprint* Blueprint, TArray<FGraphRecord>& OutGraphs);

	/** 루트 AnimGraph (UEdGraphSchema_K2::GN_AnimGraph 이름의 UAnimationGraph). 없으면 null */
	UEdGraph* FindRootAnimGraph(UAnimBlueprint* Blueprint);

	/**
	 * 그래프 트리 전체의 결정적 해시 — 그래프 Guid·클래스·이름, 노드 Guid·클래스·위치, 핀 이름·방향·기본값·연결,
	 * 그리고 노드의 편집 가능 프로퍼티 값(Phase 3): EditAnywhere 프로퍼티 전부 + FAnimNode 구조체 멤버. PoseLink·Transient·FText 는 제외
	 * (PoseLink 의 LinkID 는 컴파일러가 바꾸므로 넣으면 컴파일만으로 revision 이 변한다). 노출 핀 상태는 (이름, bShowPin) 으로 넣는다
	 */
	FString ComputeRevision(UAnimBlueprint* Blueprint);

	/** 노드의 편집 가능 프로퍼티를 "V|이름|값" 줄로 덧붙인다 (revision 재료). 순서는 리플렉션 순서 = 결정적 */
	void AppendEditableProperties(UEdGraphNode* Node, FString& Out);

	/** get_anim_blueprint_info 응답 본문 */
	TSharedRef<FJsonObject> BuildBlueprintInfo(UAnimBlueprint* Blueprint, FAnimMcpContext& Context);

	TSharedRef<FJsonObject> DescribeGraph(const FGraphRecord& Record);

	/** 핀: name, dir, type, default, hidden, linked["nodeguid:pin"] */
	TSharedRef<FJsonObject> DescribePin(const UEdGraphPin* Pin);

	/**
	 * 노드: node_guid, graph_guid, class, title, pos, asset, is_sink, pins[], sub_graphs[],
	 *       properties{허용 목록 프로퍼티 → 값}, optional_pins[{property, shown, can_toggle, bound}], has_binding
	 * 바인딩은 보유 여부만 보고한다 — 편집하지 않고 보존한다 (Phase 6)
	 */
	TSharedRef<FJsonObject> DescribeNode(UEdGraphNode* Node);

	/**
	 * get_anim_graph_structure 응답 — Graph 와 하위 그래프(Depth: 0 = 이 그래프만, -1 = 전부)의 노드·연결.
	 * 연결은 출력 핀 쪽에서 한 번만 기록한다
	 */
	TSharedRef<FJsonObject> BuildGraphStructure(UAnimBlueprint* Blueprint, UEdGraph* Graph, int32 Depth, FAnimMcpContext& Context);

	UEdGraph* FindGraphByGuid(UAnimBlueprint* Blueprint, const FGuid& Guid);
	UEdGraphNode* FindNodeByGuid(UAnimBlueprint* Blueprint, const FGuid& Guid);
}
