#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FAnimMcpError;

/**
 * 애셋 보호 목록 (Phase 6-2, 사용자 확정 A안) — 삭제·덮어쓰기(create overwrite · duplicate overwrite · delete) 전에 검사한다.
 * 설정은 프로젝트 DefaultEngine.ini 의 [AnimGraphMcp] 섹션:
 *   +ProtectedAssets=/Game/Characters/Hero/ABP_Hero          (패키지 경로 또는 오브젝트 경로, 정확히 일치)
 *   +ProtectedPaths=/Game/Assets/                            (패키지 경로 접두)
 * 보호는 파괴 연산에만 걸린다 — 읽기·편집(apply_graph_operations)·저장은 기존 규칙(운영 애셋은 사용자 승인 배치) 그대로.
 * 목록은 첫 조회 때 1회 로드한다 (에디터 기동 중 ini 변경은 반영하지 않는다).
 */
namespace AnimMcpAssetProtection
{
	struct FRules
	{
		/** 정규화된 패키지 경로 ("/Game/A/B") */
		TArray<FString> Assets;
		/** 정규화된 접두 ("/Game/A/" — 항상 '/' 로 끝난다) */
		TArray<FString> Paths;
	};

	const FRules& GetRules();

	/** 패키지/오브젝트 경로 어느 쪽이든 받는다. 보호 대상이면 true, OutMatchedRule 에 걸린 항목 */
	bool IsProtected(const FString& AssetPath, FString* OutMatchedRule = nullptr);

	/** 보호 대상이면 ASSET_PROTECTED 오류를 채우고 false. Operation 은 메시지용 ("delete" · "overwrite") */
	bool EnsureNotProtected(const FString& AssetPath, const TCHAR* Operation, FAnimMcpError& OutError);

	/** get_editor_status 용 {assets[], paths[]} */
	TSharedRef<FJsonObject> DescribeRules();
}
