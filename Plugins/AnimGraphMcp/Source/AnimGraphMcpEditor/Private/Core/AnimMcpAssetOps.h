#pragma once

#include "CoreMinimal.h"

class UAnimBlueprint;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 애셋 수명 기계 (Phase 6-2) — 삭제·복제. 보호 목록 검사는 호출자(Tool)가 먼저 한다 (정책과 기계 분리).
 * 전부 UEditorAssetSubsystem 경유 — 내부가 GIsRunningUnattendedScript 를 켜서 FMessageDialog 가 기본값으로 돌아온다
 * (MessageDialog.cpp:172). ObjectTools::ForceDeleteObjects(bShowConfirmation=false) / DuplicateSingleObject(bPromptToOverwrite=false).
 */
namespace AnimMcpAssetOps
{
	/**
	 * 애셋 삭제 — 열린 에디터를 닫고 DeleteAsset. 디스크 파일은 지워져도 메모리 객체가 참조 때문에 남을 수 있어
	 * (create overwrite 에서 실측), 남으면 임시 패키지로 옮겨 이름을 비우고 가비지로 표시한다 (진단 STALE_OBJECT_MOVED).
	 * 호출 전에 존재 여부·보호·참조 검사는 끝나 있어야 한다
	 */
	bool DeleteAssetAtPath(const FString& ObjectPath, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** AssetRegistry 패키지 참조자 — 자기 자신·임시 패키지 제외, 정렬 */
	TArray<FString> FindReferencers(const FString& ObjectPath);

	/**
	 * AnimBP 복제 — UEditorAssetSubsystem::DuplicateLoadedAsset (EditorAssetSubsystem.cpp:930 → IAssetTools::DuplicateAsset).
	 * bPreserveNodeGuids 면 FBlueprintDuplicationScopeFlags(TheSameNodeGuid) 로 감싼다 — 기본 복제는 모든 노드 Guid 를
	 * 재생성한다 (BlueprintEditorUtils.cpp:1682-1688). 그래프 Guid 는 UPROPERTY 라 어느 쪽이든 복사된다.
	 * 대상 경로에 애셋이 있으면 안 된다 (호출자가 ASSET_EXISTS / overwrite 삭제를 처리)
	 */
	UAnimBlueprint* DuplicateAnimBlueprint(UAnimBlueprint* Source, const FString& DestObjectPath, bool bPreserveNodeGuids, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
