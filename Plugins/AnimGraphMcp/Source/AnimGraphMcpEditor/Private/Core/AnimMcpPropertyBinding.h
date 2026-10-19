#pragma once

#include "CoreMinimal.h"
#include "AnimGraphNode_Base.h"

struct FAnimMcpError;

/**
 * Property Binding (Phase 6-4a) — 노출 핀을 AnimInstance 의 프로퍼티/순수 함수 경로에 묶는다 (VariableGet 노드 없이).
 *
 * 엔진 경로 (AnimGraphNodeBinding_Base.cpp:428-507 OnAddBinding, :509-521 OnRemoveBinding):
 *   Binding->Modify → 핀 노출 → 핀 링크 해제 → FAnimGraphNodePropertyBinding{PropertyName, PropertyPath, PathAsText, Type, bIsBound}
 *   → PropertyBindings.Add → ReconstructNode(→ OnReconstructNode 가 RecalculateBindingType 으로 PinType/promotion 계산, :80-90)
 *   → MarkBlueprintAsModified. 제거는 PropertyBindings.Remove.
 *
 * 접근 제한: 바인딩 객체 `UAnimGraphNodeBinding_Base` 는 모듈 Private 헤더이고 `PropertyBindings` 는 private UPROPERTY 다.
 * 노드의 `Binding`(private UPROPERTY, AnimGraphNode_Base.h:232-233) 과 그 안의 `PropertyBindings`(TMap<FName, FAnimGraphNodePropertyBinding>)
 * 를 전부 리플렉션(FObjectProperty · FMapProperty + FScriptMapHelper) 으로 다룬다. 값 구조체 FAnimGraphNodePropertyBinding 은 공개 타입.
 * 경로 해석·타입 호환은 엔진과 같은 IPropertyAccessEditor(모듈러 피처 "PropertyAccessEditor") 를 쓴다.
 */
namespace AnimMcpPropertyBinding
{
	struct FBindingInfo
	{
		FName Name;
		TArray<FString> Path;
		FString PathText;
		/** "Property" | "Function" */
		FString Type;
		FName Context;
		bool bPromotion = false;
		bool bBound = false;
	};

	/** IPropertyAccessEditor 모듈러 피처가 등록돼 있는가 (에디터에서는 항상 true 여야 한다) */
	bool IsAvailable();

	/** 노드의 바인딩 전부 (이름순) */
	bool ReadBindings(const UAnimGraphNode_Base* Node, TArray<FBindingInfo>& Out);

	/** 이름으로 원시 항목 복사 — 롤백 보관용. 없으면 false */
	bool FindRaw(const UAnimGraphNode_Base* Node, FName Name, FAnimGraphNodePropertyBinding& Out);

	/**
	 * 검증 (그래프 불변) — 노출 가능 핀(ShowPinForProperties, bCanToggleVisibility) · 경로가 SkeletonGeneratedClass 에서 해석됨 ·
	 * 리프 타입이 핀 프로퍼티와 호환(승격 허용) · 핀에 링크 없음. OutType = Property|Function
	 */
	bool ValidateBind(UAnimGraphNode_Base* Node, FName Property, const TArray<FString>& Path, FString& OutType, FAnimMcpError& OutError);

	/**
	 * 적용 — 핀 노출(숨겨져 있었으면 bOutPinWasHidden) → 항목 추가/교체(기존 항목은 OutOld, bOutHadOld) → ReconstructNode → MarkBlueprintAsModified.
	 * 호출 전 ValidateBind 통과를 전제로 한다
	 */
	bool Bind(UAnimGraphNode_Base* Node, FName Property, const TArray<FString>& Path, bool& bOutHadOld, FAnimGraphNodePropertyBinding& OutOld, bool& bOutPinWasHidden, FAnimMcpError& OutError);

	/** 제거 — 바인딩이 없으면 BAD_REQUEST. OutOld 는 롤백용 */
	bool Unbind(UAnimGraphNode_Base* Node, FName Property, FAnimGraphNodePropertyBinding& OutOld, FAnimMcpError& OutError);

	/** 롤백 전용 원시 쓰기/삭제 (+ReconstructNode) */
	void WriteRaw(UAnimGraphNode_Base* Node, const FAnimGraphNodePropertyBinding& Binding);
	void RemoveRaw(UAnimGraphNode_Base* Node, FName Name);

	/** revision 재료 — "B|이름|경로|타입|컨텍스트" 줄 (이름순). 바인딩이 없으면 아무것도 쓰지 않아 기존 해시와 호환 */
	void AppendRevision(const UAnimGraphNode_Base* Node, FString& Out);
}
