#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UStateTree;
class UStateTreeEditorData;
struct FAnimMcpError;

/**
 * StateTree 애셋 수명 — 경로 규칙 · 생성 · 컴파일 측정 · 복구 · 편집기 알림 (Docs/StateTree/DevelopmentGuide.md §2 · §5).
 * 복구 절차의 근거는 Feasibility.md §2 E5 · §4. 핵심 규칙: 큐 확인 없이 Undo 하지 않는다, 재로드 뒤 옛 포인터를 쓰지 않는다,
 * 트랜잭션을 연 채 재로드하지 않는다, FindOrAddViewModel 을 부르지 않는다.
 */
namespace AnimMcpStateTreeAsset
{
	/** create_state_tree 의 schema_class 기본값 */
	inline const TCHAR* const DefaultSchemaClass = TEXT("/Script/GameplayStateTreeModule.StateTreeAIComponentSchema");

	/** StateTreeEditPaths — [EditorMcp] 와 옛 [AnimGraphMcp] 를 합친 '/' 로 끝나는 패키지 경로 접두. 첫 조회 때 1회 로드 */
	const TArray<FString>& GetEditPaths();

	/** 허용 경로 안이고 보호 대상이 아니어야 한다. OUTPUT_PATH_NOT_ALLOWED · ASSET_PROTECTED */
	bool EnsureWritable(const FString& AssetPath, FAnimMcpError& OutError);

	/** PIE_ACTIVE */
	bool EnsureNotInPie(FAnimMcpError& OutError);

	/** TRANSACTION_ACTIVE — 열린 트랜잭션에 합쳐지면 Undo 도 재로드도 쓸 수 없다 */
	bool EnsureNoActiveTransaction(FAnimMcpError& OutError);

	UStateTree* Load(const FString& AssetPath, FAnimMcpError& OutError);

	UStateTreeEditorData* GetEditorData(const UStateTree* Tree);

	/** EditorData CRC32 (%08x) */
	FString GetRevision(const UStateTree& Tree);

	/** up_to_date · stale · failed (Feasibility §4) */
	FString GetCompileState(const UStateTree& Tree);

	/**
	 * 순서: 경로 · 이름 형식 → 허용 경로 → 존재 → 스키마 클래스 → schema_properties 값 → CreateAsset → 값 설정 + 알림 → 재컴파일 → 저장.
	 * 사전 검사를 CreateAsset 앞에 두는 이유: 같은 이름은 창 · Error 로그, 스키마 없음은 빈 패키지를 남긴다(§2-2).
	 * SchemaProperties 는 ContextActorClass · AIControllerClass 만 받는다
	 */
	UStateTree* Create(const FString& AssetPath, const FString& SchemaClassPath, const TSharedPtr<FJsonObject>& SchemaProperties, bool bSave, FAnimMcpError& OutError);

	struct FCompileResult
	{
		bool bOk = false;
		/** §2-5 형식 */
		TArray<TSharedPtr<FJsonValue>> Messages;
		/** 컴파일 전후로 사라진 바인딩 · 노드 — { kind: binding_removed | node_removed, ... } */
		TArray<TSharedPtr<FJsonValue>> Fixups;

		TSharedRef<FJsonObject> ToJson() const;
	};

	/** 트랜잭션 밖에서 부른다. 실패는 ResetCompiled 로 기존 컴파일 결과까지 지운다(§2-4) */
	FCompileResult Compile(UStateTree& Tree);

	/** 적용 전 기록 — 복구 판정의 기준 */
	struct FBaseline
	{
		FString ObjectPath;
		uint32 Hash = 0;
		uint32 CompiledHash = 0;
		bool bReady = false;
		bool bDirty = false;
		/** GetQueueLength - GetUndoCount. Undo 해 둔 상태에서 새 트랜잭션이 들어오면 Redo 항목이 잘리므로 실효 길이로 비교한다 */
		int32 EffectiveQueue = 0;
	};

	FBaseline CaptureBaseline(const UStateTree& Tree);

	struct FRollback
	{
		bool bVerified = false;
		/** none · undo · reload */
		FString Method;
		bool bUndoHistoryCleared = false;
		bool bEditorReopened = false;
		FString Revision;

		TSharedRef<FJsonObject> ToJson() const;
	};

	/**
	 * §5 6단계. Undo(실효 큐 = 기준 + 1 일 때만) → 변경 없음 → 재로드. 트랜잭션을 닫은 뒤에 부른다.
	 * 재로드 경로는 GC 가 돌아 UStateTree · EditorData · 상태 포인터가 전부 무효가 된다 — 호출자는 이후 포인터를 쓰지 말 것
	 */
	FRollback Recover(const FBaseline& Baseline);

	/** 디스크 상태로 재로드 — revert_state_tree 와 Recover 2단. Undo 기록 전체가 사라지고 열린 편집기가 닫혔다 열린다 */
	FRollback ReloadFromDisk(const FString& ObjectPath, uint32 ExpectedHash, bool bCheckHash);

	bool Save(UStateTree& Tree, FAnimMcpError& OutError);

	/** 열린 편집기에만 알린다 — FindViewModel 은 없을 때 만들지 않는다 */
	void NotifyEditors(UStateTree& Tree);
}
