#pragma once

#include "CoreMinimal.h"

class FJsonValue;
class FObjectPropertyBase;
class FProperty;
struct FAnimMcpError;

/**
 * JSON ↔ 리플렉션 프로퍼티 값 변환 — 기능 독립 부분 (2026-11-14 플러그인 분리 때 AnimGraphMcp 의 AnimMcpPropertyRules 에서 떼어 냄).
 * AnimGraph 노드 허용 목록(RulesFor · ResolveOnNode 등)은 AnimGraphMcp 의 Core/AnimMcpPropertyRules.h 에 남고, 그 헤더가 이 헤더를 포함한다.
 * StateTree 노드 값(set_node_values · inspect) 도 같은 변환을 쓴다. 네임스페이스 이름은 기존 호출 코드 호환을 위해 그대로 둔다.
 */
namespace AnimMcpPropertyRules
{
	/**
	 * JSON 값 → FProperty::ImportText 가 받는 텍스트 (재귀).
	 * bool → True/False · 숫자 → 정수/실수 문자열 · 문자열 → 그대로(enum 이름·FName·FString) · 배열 → "(a,b,c)" (요소는 Inner 타입 규칙)
	 * · 구조체(JSON 객체) → "(Field=Value,...)" — 필드 이름은 USTRUCT 멤버 이름 그대로, 없는 필드는 거부, 생략한 필드는 기본값 (Phase 5: LayerSetup).
	 * (7-2) 오브젝트 참조 → 애셋 경로 문자열(로드·클래스 검사 뒤 Class'Path') 또는 null("None"). 스켈레톤 일치 등 의미 검증은 호출자 몫
	 */
	EDITORMCPCORE_API bool JsonToImportText(const FProperty* Property, const TSharedPtr<FJsonValue>& Value, FString& OutText, FAnimMcpError& OutError);

	/** (7-2) 오브젝트 참조 값 해석 — 경로로 찾거나 로드하고 PropertyClass 를 검사. 실패 reason: OBJECT_NOT_FOUND · OBJECT_CLASS_MISMATCH */
	EDITORMCPCORE_API UObject* ResolveObjectValue(const FObjectPropertyBase* Property, const FString& Path, FAnimMcpError& OutError);

	/** 프로퍼티 현재 값 → JSON (bool/number 는 네이티브 타입, 배열·구조체는 재귀, 그 외는 ExportText 문자열). ValuePtr 는 ContainerPtrToValuePtr 결과 */
	EDITORMCPCORE_API TSharedPtr<FJsonValue> PropertyToJson(const FProperty* Property, const void* ValuePtr, UObject* Owner);
}
