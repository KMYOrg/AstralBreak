#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimBlueprint;
class UAnimStateTransitionNode;
class UEdGraph;
class UEdGraphNode;
struct FAnimMcpError;

/**
 * Transition Rule — 선언적 AST → BoundGraph(UAnimationTransitionGraph) 의 K2 노드 (핸드오프 §9, 2026-10-15 사용자 확정 "JSON 트리").
 *
 * AST (각 노드는 키 하나짜리 객체):
 *   {"var": "bIsFalling"}                                   AnimInstance 의 BlueprintVisible 프로퍼티 → UK2Node_VariableGet(self)
 *   {"not": E}                                              UKismetMathLibrary::Not_PreBool
 *   {"and": [E, E, ...]} · {"or": [E, E, ...]}              BooleanAND / BooleanOR 를 왼쪽부터 사슬로 (2개 이상)
 *   {"compare": {"op": ">", "left": E, "right": E}}         (op, 피연산자 타입) → UKismetMathLibrary 함수 표. op ∈ > < >= <= == !=
 *   {"literal": 10.0 | true | "Name"}                       상수 — 상대 핀의 기본값으로 들어간다 (노드 없음). 타입은 상대 피연산자에서 온다
 *   {"call": {"function": "F", "class"?: "/Script/..", "args"?: {"Param": E}}}
 *                                                           BlueprintPure ∧ BlueprintThreadSafe(함수 또는 클래스 메타) ∧ 소유 클래스 ∈ {이 AnimBP 의 AnimInstance 사슬, UKismetMathLibrary}
 *   {"automatic": true, "trigger_time"?: -1.0}              그래프 없이 bAutomaticRuleBasedOnSequencePlayerInState 만 (최상위 전용)
 * 최상위 식은 bool 이어야 한다. 비교 피연산자 타입은 Real(float/double) · Int · Int64 · Bool(==,!=) · Name(==,!=). 한쪽은 literal 이 아니어야 한다.
 *
 * 생성 규칙: BoundGraph 를 Result 노드만 남기고(Operations 가 분리 보관) AST 에서 전체 재생성. 원문(정규화 JSON)과 생성 직후 그래프 해시를
 * UEdGraphNode_Comment 에 기록해 Inspector 가 rule_source 를 복원하고 사람 편집(rule_modified)을 감지한다. 같은 AST 재적용은 no-op (멱등).
 * float 변수 핀 → double 함수 핀: UEdGraphSchema_K2::ArePinTypesCompatible 이 PC_Real 은 서브타입 무관하게 호환 (EdGraphSchema_K2.cpp:4533)
 */
namespace AnimMcpTransitionRule
{
	/** 주석 노드 첫 줄 — 도구 소유 규칙 그래프 표식 */
	extern const TCHAR* const SourceMarker;

	/**
	 * 검증만 (그래프 불변). 변수 존재·타입, 함수 화이트리스트, 구조, 최상위 bool. OutCanonical 은 키 순서가 고정된 압축 JSON.
	 * bOutAutomatic 이면 그래프를 만들지 않는다
	 */
	bool Validate(UAnimBlueprint* Blueprint, const TSharedPtr<FJsonObject>& Rule, FString& OutCanonical, bool& bOutAutomatic, double& OutTriggerTime, FAnimMcpError& OutError);

	/**
	 * BoundGraph 에 AST 를 그린다 (Result 노드와 주석 노드 외에 다른 노드가 없다고 가정). 만든 노드를 OutCreated 에 (주석 포함).
	 * 호출자가 FScopedTransaction 안에서 부른다. automatic 이면 Result 핀 기본값은 건드리지 않고 주석만 남긴다
	 */
	bool Build(UAnimStateTransitionNode* Transition, const TSharedPtr<FJsonObject>& Rule, const FString& Canonical, bool bAutomatic, TArray<UEdGraphNode*>& OutCreated, FAnimMcpError& OutError);

	struct FSource
	{
		bool bHasSource = false;
		/** 주석에 기록된 정규화 JSON (파싱 결과) */
		TSharedPtr<FJsonObject> Source;
		FString Canonical;
		FString StoredHash;
		/** 지금 그래프 해시가 기록과 다르다 = 생성 뒤 사람이 손댔다 */
		bool bModified = false;
	};

	/** BoundGraph 의 도구 주석을 읽는다. 주석이 없으면 bHasSource=false (사람이 만든 규칙 또는 빈 규칙) */
	FSource ReadSource(UEdGraph* BoundGraph);

	/** 규칙 그래프 해시 — 주석 노드 제외, (위치·클래스) 정렬, Guid 미포함 (재생성해도 같은 그래프면 같은 값) */
	FString HashRuleGraph(UEdGraph* BoundGraph);

	/** Result 노드와 주석 노드를 뺀 규칙 노드들 */
	void CollectRuleNodes(UEdGraph* BoundGraph, TArray<UEdGraphNode*>& OutNodes);
}
