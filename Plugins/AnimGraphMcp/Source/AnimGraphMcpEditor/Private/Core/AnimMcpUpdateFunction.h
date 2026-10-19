#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

class UAnimBlueprint;
class UEdGraph;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * Phase 7-1 — BlueprintThreadSafeUpdateAnimation 함수 그래프를 스펙에서 통째로 재생성한다 (규칙 그래프와 같은 방식: 원문·해시를 주석에, 멱등, 사람 편집 감지).
 *
 * 스펙: {"assignments": [{"variable": "Speed", "value": <식>}, ...]}
 *   식 = AnimMcpTransitionRule 의 AST (var · access · param · not · and · or · compare · literal · call). {"param": "DeltaTime"} 은 여기서만 유효.
 *   변수는 BlueprintVisible 이고 읽기 전용(BlueprintReadOnly)이 아니어야 한다 — BP 변수(add_blueprint_variable) 또는 네이티브 BlueprintReadWrite.
 *
 * 그래프 모양: FunctionEntry(then) → VariableSet(var1) → VariableSet(var2) → … ; 각 Set 의 값 핀에 식 노드 트리가 왼쪽에서 들어온다.
 *
 * 엔진 경로: BlueprintThreadSafe 메타가 붙은 BlueprintImplementableEvent 는 이벤트가 아니라 **함수 그래프**로 오버라이드된다
 * (SMyBlueprint.cpp:2874-2878 — CreateNewGraph(K2 스키마) + AddFunctionGraph<UClass>(BP, Graph, false, 선언 클래스); 판정 BlueprintEditorUtils.cpp:2242).
 * 컴파일러가 이 함수 안의 호출이 전부 스레드 안전인지 검사하고 아니면 경고 + bUseMultiThreadedAnimationUpdate=false (AnimBlueprintCompiler.cpp:1084-1151).
 */
namespace AnimMcpUpdateFunction
{
	/** 주석 노드 첫 줄 */
	extern const TCHAR* const SourceMarker;

	/** "BlueprintThreadSafeUpdateAnimation" */
	FName FunctionName();

	/** 이 BP 의 오버라이드 함수 그래프. 없으면 null */
	UEdGraph* FindGraph(UAnimBlueprint* Blueprint);

	struct FAssignment
	{
		FString Variable;
		TSharedPtr<FJsonValue> Value;
		FString ValueCanonical;
	};

	/**
	 * 파라미터 파싱 + 검증 (그래프 불변). 거부 reason: NO_ASSIGNMENTS · BAD_ASSIGNMENT · READ_ONLY · DUPLICATE_VARIABLE · TYPE_INCOMPATIBLE (+ 식 오류).
	 * OutCanonical = {"assignments":[{"variable":..,"value":<정규화 식>},..]}
	 */
	bool ParseAndValidate(UAnimBlueprint* Blueprint, const TSharedRef<FJsonObject>& Params, TArray<FAssignment>& OutAssignments, FString& OutCanonical, FAnimMcpError& OutError);

	/**
	 * 적용 — 트랜잭션 안에서 그래프 생성(없으면) → 기존 노드 분리 보관 → 재생성 → 실패 시 복구. 같은 원문 + 사람 편집 없음이면 무변경(unchanged).
	 * OutResult: graph_guid, created_graph, unchanged, node_count, assignment_count
	 */
	bool Apply(UAnimBlueprint* Blueprint, const TArray<FAssignment>& Assignments, const FString& Canonical, FAnimMcpContext& Context, TSharedRef<FJsonObject>& OutResult, FAnimMcpError& OutError);

	/** 함수 그래프 제거 (오버라이드 해제). 없으면 BAD_REQUEST(NO_UPDATE_FUNCTION) */
	bool Remove(UAnimBlueprint* Blueprint, FAnimMcpError& OutError);

	/** get_anim_blueprint_info.update_function — 없으면 null, 있으면 {graph_guid, generated, source, modified, node_count, assignments[]} */
	TSharedPtr<FJsonValue> Describe(UAnimBlueprint* Blueprint);
}
