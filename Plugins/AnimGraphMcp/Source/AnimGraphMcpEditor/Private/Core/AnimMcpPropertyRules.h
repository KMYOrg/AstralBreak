#pragma once

#include "CoreMinimal.h"

class FJsonValue;
class FObjectPropertyBase;
class FProperty;
class FStructProperty;
class UClass;
class UEdGraphNode;
struct FAnimMcpError;

/**
 * set_property 허용 목록 — Inspector(값 조회·revision) 와 Mutator(값 설정) 가 같은 표를 본다.
 * 원칙(핸드오프 §8): ① 노드별 공식 Setter ② 허용 목록 기반 리플렉션 ③ 노드별 특수 처리. 임의 프로퍼티 범용 명령은 없다.
 * 표는 클래스 이름으로 매칭하고 상위 클래스를 거슬러 올라간다 (BlendListByBool/ByEnum 은 BlendListBase 규칙을 상속).
 * 2026-10-15 사용자 확정: "확장 목록". 2026-10-16 Phase 5: LayeredBoneBlend 의 LayerSetup(본 필터)·BlendMode 추가 — 구조체 배열은 JSON 객체 배열로 받는다.
 */
namespace AnimMcpPropertyRules
{
	enum class EScope : uint8
	{
		/** UEdGraphNode 파생 객체 자신의 UPROPERTY (CacheName, CrossfadeDuration …) */
		Node,
		/** UAnimGraphNode_Base::GetFNodeProperty() 가 가리키는 FAnimNode 구조체의 멤버 (PlayRate, SlotName …) */
		FNode,
		/** 다른 노드를 가리키는 참조 — 값은 node guid / ref. 특수 처리 (UseCachedPose.SaveCachedPoseNode) */
		NodeRef,
	};

	struct FRule
	{
		FName Property;
		EScope Scope = EScope::FNode;
		/** 조회만 — set_property 거부 (BlendListByEnum.BoundEnum 등) */
		bool bReadOnly = false;
	};

	/** 이 노드 클래스(상속 포함)에 적용되는 규칙 전부. 없으면 빈 배열 */
	TArray<FRule> RulesFor(const UClass* NodeClass);

	/** 규칙 하나. 없으면 null */
	const FRule* Find(const UClass* NodeClass, FName Property);

	/** 오류 details 용 — 허용 프로퍼티 이름 목록 */
	FString DescribeAllowed(const UClass* NodeClass);

	/** 규칙 → 실제 FProperty. NodeRef 규칙은 FProperty 를 돌려주지 않는다(OutProperty=null, 성공) */
	struct FResolved
	{
		const FRule* Rule = nullptr;
		FProperty* Property = nullptr;
		/** FNode 스코프일 때 FAnimNode 구조체 프로퍼티 (PostEditChangeProperty 의 MemberProperty) */
		FStructProperty* MemberProperty = nullptr;
		/** Property 의 컨테이너 (Node 객체 또는 FNode 구조체 시작 주소). 클래스만으로 해석했으면 null */
		void* Container = nullptr;
	};

	/** 클래스만으로 해석 (Preview 에서 아직 만들어지지 않은 ref 의 타입 검증용). Container 는 null */
	bool ResolveOnClass(const UClass* NodeClass, FName Property, FResolved& Out, FAnimMcpError& OutError);

	/** 인스턴스에서 해석 — Container 까지 채운다 */
	bool ResolveOnNode(UEdGraphNode* Node, FName Property, FResolved& Out, FAnimMcpError& OutError);

	/**
	 * JSON 값 → FProperty::ImportText 가 받는 텍스트 (재귀).
	 * bool → True/False · 숫자 → 정수/실수 문자열 · 문자열 → 그대로(enum 이름·FName·FString) · 배열 → "(a,b,c)" (요소는 Inner 타입 규칙)
	 * · 구조체(JSON 객체) → "(Field=Value,...)" — 필드 이름은 USTRUCT 멤버 이름 그대로, 없는 필드는 거부, 생략한 필드는 기본값 (Phase 5: LayerSetup).
	 * (7-2) 오브젝트 참조 → 애셋 경로 문자열(로드·클래스 검사 뒤 Class'Path') 또는 null("None"). 스켈레톤 일치 등 의미 검증은 Mutator 의 ValidatePropertyValueOnNode
	 */
	bool JsonToImportText(const FProperty* Property, const TSharedPtr<FJsonValue>& Value, FString& OutText, FAnimMcpError& OutError);

	/** (7-2) 오브젝트 참조 값 해석 — 경로로 찾거나 로드하고 PropertyClass 를 검사. 실패 reason: OBJECT_NOT_FOUND · OBJECT_CLASS_MISMATCH */
	UObject* ResolveObjectValue(const FObjectPropertyBase* Property, const FString& Path, FAnimMcpError& OutError);

	/** 프로퍼티 현재 값 → JSON (bool/number 는 네이티브 타입, 배열·구조체는 재귀, 그 외는 ExportText 문자열). ValuePtr 는 ContainerPtrToValuePtr 결과 */
	TSharedPtr<FJsonValue> PropertyToJson(const FProperty* Property, const void* ValuePtr, UObject* Owner);
}
