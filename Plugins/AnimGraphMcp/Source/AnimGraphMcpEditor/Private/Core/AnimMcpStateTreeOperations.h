#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UStateTree;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * StateTree 배치 (DevelopmentGuide §4 · §5). 세션 상태 없이 operations 배열 하나로 적용한다.
 *
 * 배치는 한 번만 해석한다: 계획 단계가 기존 트리의 그림자를 op 순서대로 갱신하며 검증하고 실행 단계를 만든다.
 * Preview 는 계획만, Apply 는 같은 계획을 트랜잭션 안에서 실행한다 — 두 경로의 판정이 갈리지 않는다.
 *
 * 바인딩 범위만 예외다. GetBindableStructs 는 실제 데이터를 따라가므로 같은 배치에서 만드는 노드는 넣을 수 없고, 범위 규칙을 흉내 내면 안 된다(§2-7).
 * 양쪽이 기존 노드일 때만 계획에서 보고, 나머지는 Preview 에 deferred:["scope"] 로 표시한 뒤 Apply 가 바인딩을 넣기 직전에 판정한다.
 * 그 실패는 §5 복구로 간다(디스크 불변). 즉 Preview 통과가 범위 통과를 보장하지 않는다.
 */
namespace AnimMcpStateTreeOperations
{
	struct FOperation
	{
		int32 Index = INDEX_NONE;
		FString Op;
		/** 노드 · 상태 · 전환을 만드는 op 의 ref 정의 — 다른 op 의 ref 는 참조다 */
		FString Ref;
		TSharedPtr<FJsonObject> Json;
	};

	bool ParseOperations(const FJsonObject& Params, TArray<FOperation>& OutOps, FAnimMcpError& OutError);

	/** 변경 없음. result: valid · revision · compile_state · planned[{index, op, ref?, ok, error?, deferred?, skipped?}] */
	TSharedRef<FJsonObject> Preview(const UStateTree& Tree, const TArray<FOperation>& Ops);

	/**
	 * §5 순서. 호출 전 경로 · PIE · 활성 트랜잭션 검사는 Tool 이 한다.
	 * 실패 details: stage(preflight · apply · compile · fixups · save) · messages · fixups · rollback{verified, method, undo_history_cleared, editor_reopened, revision} · planned · failed_index.
	 * 실패 뒤 Tree 포인터는 재로드로 무효일 수 있다 — 호출자는 쓰지 말 것
	 */
	TSharedPtr<FJsonObject> Apply(UStateTree& Tree, const TArray<FOperation>& Ops, const FString& ExpectedRevision, bool bCompile, bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
