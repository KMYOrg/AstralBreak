#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimBlueprint;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 변경 계획(operations 배열) 의 검증·적용. Preview 는 그래프를 바꾸지 않고, Apply 는 트랜잭션 안에서 순차 적용한다.
 * 실패 복구: 에디터 Undo 를 쓰지 않는다 — 결과가 에디터 Undo 버퍼 상태에 의존하지 않도록 이 배치가 한 일만 정확히 되돌린다.
 * 이 배치가 만든 노드를 삭제하고 connect 가 바꾼 링크를 스냅샷으로 복원한 뒤 트랜잭션을 Cancel 해 기록을 버리고,
 * revision 대조로 **복구를 검증**한다. (FScopedTransaction::Cancel 자체는 객체 상태를 되돌리지 않는다 — EditorTransaction.cpp:1404)
 *
 * 지원 op (Phase 2.5):
 *   add_node  { ref?, graph?(guid, 생략=루트 AnimGraph), class, pos?[x,y], asset? }
 *   connect   { from:{node|ref, pin}, to:{node|ref, pin} }
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

	/** 검증만. result: valid, revision, planned[{index, op, ref, ok, error?}], would_create, would_connect */
	TSharedRef<FJsonObject> Preview(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, FAnimMcpContext& Context);

	/**
	 * 검증 → 트랜잭션 → 적용 → (옵션) 컴파일 → (옵션) 저장.
	 * ExpectedRevision 이 비어 있지 않고 현재와 다르면 REVISION_MISMATCH. 중간 실패는 Undo + 검증 후 오류 반환.
	 */
	TSharedPtr<FJsonObject> Apply(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, const FString& ExpectedRevision, bool bCompile, bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
