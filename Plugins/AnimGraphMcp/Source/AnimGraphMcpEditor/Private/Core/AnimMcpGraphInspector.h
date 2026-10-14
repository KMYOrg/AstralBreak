#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimBlueprint;
class UEdGraph;
struct FAnimMcpContext;

/**
 * 읽기 전용 — AnimBP 의 그래프 계층을 JSON 으로. 쓰지 않는다 (Preview/Apply 분리의 코드상 표현).
 * Phase 2 범위: 그래프 트리 · 변수 · revision · 요약 카운트. 노드/핀/연결 전체 덤프는 Phase 3.
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
	 * 그래프 트리 전체의 결정적 해시 — 그래프 Guid·클래스·이름, 노드 Guid·클래스·위치, 핀 이름·방향·기본값·연결.
	 * 노드 내부 FAnimNode 프로퍼티 값은 아직 포함하지 않는다 (Phase 3 에서 ExportText 비용 측정 후 결정)
	 */
	FString ComputeRevision(UAnimBlueprint* Blueprint);

	/** get_anim_blueprint_info 응답 본문 */
	TSharedRef<FJsonObject> BuildBlueprintInfo(UAnimBlueprint* Blueprint, FAnimMcpContext& Context);

	TSharedRef<FJsonObject> DescribeGraph(const FGraphRecord& Record);
}
