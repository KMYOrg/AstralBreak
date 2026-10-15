#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimBlueprint;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 변경 계획(operations 배열) 의 검증·적용. Preview 는 그래프를 바꾸지 않고, Apply 는 트랜잭션 안에서 순차 적용한다.
 * 실패 복구: 에디터 Undo 를 쓰지 않는다 — 결과가 에디터 Undo 버퍼 상태에 의존하지 않도록 이 배치가 한 일만 정확히 되돌린다.
 * 각 op 는 적용 직후 자기 되돌리기(클로저)를 저널에 넣고, 실패 시 역순으로 실행한 뒤 트랜잭션을 Cancel 해 기록을 버리고
 * revision 대조로 **복구를 검증**한다. (FScopedTransaction::Cancel 자체는 객체 상태를 되돌리지 않는다 — EditorTransaction.cpp:1404)
 * 핀은 포인터가 아니라 (노드, 핀 이름) 으로 기억한다 — ReconstructNode 뒤에도 이름으로 다시 찾을 수 있다.
 *
 * 지원 op:
 *   add_node       { ref?, graph?(guid, 생략=루트 AnimGraph), class, pos?[x,y], asset?, enum?(BlendListByEnum), properties?{name:value} }
 *   connect        { from:{node|ref, pin}, to:{node|ref, pin} }
 *   disconnect     { from:{node|ref, pin}, to?:{node|ref, pin} }      to 생략 = from 핀의 링크 전부
 *   remove_node    { node|ref }                                        분리 보관 → 성공 확정 시 DestroyNode
 *   set_property   { node|ref, property, value }                       허용 목록(AnimMcpPropertyRules). NodeRef 규칙은 value 가 노드 참조
 *   set_asset      { node|ref, asset }
 *   expose_pin     { node|ref, property, visible?=true }
 *   add_blend_pose { node|ref, entry?(BlendListByEnum 요소 이름) }
 * ref 는 배치 안에서 앞 op 가 만든 노드를 뒤 op 가 가리키는 임시 이름. 응답 refs 에서 guid 로 확정된다.
 */
namespace AnimMcpOperations
{
	struct FOperation
	{
		int32 Index = INDEX_NONE;
		FString Op;
		FString Ref;
		TSharedPtr<FJsonObject> Json;
	};

	bool ParseOperations(const FJsonObject& Params, TArray<FOperation>& OutOps, FAnimMcpError& OutError);

	/** 검증만. result: valid, revision, planned[{index, op, ref, ok, error?, note?}], would_create, would_connect, would_disconnect, would_remove, would_modify */
	TSharedRef<FJsonObject> Preview(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, FAnimMcpContext& Context);

	/**
	 * 검증 → 트랜잭션 → 적용 → (옵션) 컴파일 → (옵션) 저장.
	 * ExpectedRevision 이 비어 있지 않고 현재와 다르면 REVISION_MISMATCH. 중간 실패는 보상 롤백 + 검증 후 오류 반환.
	 */
	TSharedPtr<FJsonObject> Apply(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, const FString& ExpectedRevision, bool bCompile, bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
