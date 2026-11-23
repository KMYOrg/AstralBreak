#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"

/**
 * promote_widget — 사람이 고른 run 결과를 프로젝트 UI 폴더로 복사한다 (설계 Docs/Design/ui-autogen-pipeline.md §1 원칙 5 · §6 promote_widget 행).
 * M4 단위 C 가 Phase 4 의 승격 도구를 최소판으로 앞당겼다(Docs/Design/m4-ult-chain.md §6 'C 구현 결과').
 *
 *   복사만 한다   run 폴더의 패키지 전부를 dest 폴더로(하위 경로 유지). 원본 run 은 그대로 둔다.
 *   참조 다시 잇기 엔진 IAssetTools::AdvancedCopyPackages(기본 경로 — 불러 와 복제 → 복사본끼리 참조 교체 → BP 컴파일 → 저장)가 한다.
 *                 끝에서 레지스트리 의존성으로 복사본이 /Game/_AutoGen/ 을 더는 가리키지 않는지 확인한다.
 *   덮어쓰지 않는다 dest 폴더에 애셋 · 파일 · 메모리 패키지가 하나라도 있으면 거절한다(DEST_EXISTS).
 *   사람 요청 때만 dry_run 으로 계획을 보이고 confirm=true 일 때만 복사한다. 무인 파이프라인(Tools/uigen)은 부르지 않는다.
 *
 * 거절(아무것도 복사하지 않음): confirm 없음 · run 폴더가 WidgetOutputPaths 아래가 아님 · dest 가 WidgetPromotionPaths 아래의 하위 폴더가 아님 ·
 * dest 가 run 경로 안 · dest 가 비어 있지 않음 · 레지스트리 로딩 중 · run 에 저장 안 된 / 더티 패키지 · run 이 비었음 · run 이 다른 run 폴더에 기댐.
 * 복사 뒤 검증이 실패하면 오류를 돌려주지만 되돌리지 않는다(엔진이 저장까지 끝낸 뒤다 — details 에 복사된 것).
 */
namespace WidgetMcpPromote
{
	struct FRequest
	{
		FString RunFolder;
		FString DestFolder;
		bool bDryRun = false;
		bool bConfirm = false;
	};

	TSharedPtr<FJsonObject> Run(const WidgetMcp::FSettings& Settings, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError);
}
