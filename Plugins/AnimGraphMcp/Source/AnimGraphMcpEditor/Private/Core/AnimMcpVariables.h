#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "EdGraph/EdGraphPin.h"

class UAnimBlueprint;
struct FAnimMcpError;

/**
 * Phase 7-1 — Animation Blueprint 의 BP 멤버 변수 추가·삭제.
 *
 * 엔진 경로: FBlueprintEditorUtils::AddMemberVariable(BP, 이름, FEdGraphPinType, 기본값 문자열) → NewVariables + MarkBlueprintAsStructurallyModified
 * (BlueprintEditorUtils.cpp:4645-4703) 가 스켈레톤 클래스를 재생성하므로, 기존 규칙 var · K2Node_VariableGet · bind_pin 은 수정 없이 새 변수를 본다
 * (셋 다 SkeletonGeneratedClass 에서 해석). 삭제는 RemoveMemberVariable(:4706 — 참조하는 변수 노드도 지운다) → force 없이는 IsVariableUsed 면 거부.
 * 이름 검증은 에디터와 같은 FKismetNameValidator.
 *
 * type 문자열: bool · float(=double) · int · int64 · name · string · text · byte · vector · rotator · transform · vector2d · linearcolor
 *   · object:<클래스 경로> · class:<클래스 경로> · struct:<구조체 경로> · enum:<열거형 경로>
 */
namespace AnimMcpVariables
{
	struct FAddParams
	{
		FString Name;
		FString Type;
		/** 핀 기본값 텍스트 (bool "true", 숫자, 이름, 벡터 "(X=0,Y=0,Z=0)" …). 비어 있으면 타입 기본값 */
		FString DefaultValue;
		FString Category;
		/** true 면 인스턴스에서 편집 가능 (CPF_DisableEditOnInstance 해제) */
		bool bInstanceEditable = false;
	};

	/** type 문자열 → 핀 타입. 실패 시 BAD_REQUEST(details.reason=BAD_TYPE) */
	bool ParsePinType(const FString& Text, FEdGraphPinType& OutType, FAnimMcpError& OutError);

	/** 핀 타입 → type 문자열 (ParsePinType 의 역, 조회용) */
	FString PinTypeToText(const FEdGraphPinType& Type);

	/** 변수 추가. 호출자가 FScopedTransaction 안에서 부른다. 거부: BAD_NAME · VARIABLE_EXISTS · BAD_TYPE · BAD_DEFAULT */
	bool AddVariable(UAnimBlueprint* Blueprint, const FAddParams& Params, FAnimMcpError& OutError);

	/**
	 * 변수 삭제 — 이 BP 가 선언한 변수만(NOT_BLUEPRINT_VARIABLE). 그래프가 참조 중이면 bForce 없이는 VARIABLE_IN_USE.
	 * bForce 면 엔진이 참조 노드도 지운다(RemoveVariableNodes) — 핀 바인딩(bind_pin)은 검사하지 않으므로 컴파일 경고로 드러난다
	 */
	bool RemoveVariable(UAnimBlueprint* Blueprint, const FString& Name, bool bForce, bool& bOutWasUsed, FAnimMcpError& OutError);

	/** 이 BP 가 선언한 변수의 선언 정보 {type, default_value, category, instance_editable} — 네이티브 변수면 null */
	TSharedPtr<FJsonObject> DescribeDeclaration(UAnimBlueprint* Blueprint, FName Name);

	/** revision 재료 — "BV|이름|타입|기본값" 줄 (NewVariables 가 있을 때만, 기존 revision 호환) */
	void AppendRevisionLines(UAnimBlueprint* Blueprint, FString& Out);
}
