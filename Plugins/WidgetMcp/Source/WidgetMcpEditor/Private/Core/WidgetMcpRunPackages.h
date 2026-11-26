#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"

/**
 * run 패키지 — save_widget_run(finalize 통과 때만) · discard_run_packages(저장 안 한 run 패키지 폐기) (설계 §2-2 finalize · §9).
 * 대상은 run 폴더("/Game/_AutoGen/<run_id>") 아래 메모리의 패키지뿐이다. 폴더는 WidgetOutputPaths 아래의 하위 폴더여야 한다(접두 자체는 거부).
 * 폐기는 디스크에 저장된 적 없는 패키지만 — 하나라도 저장된 것이 있으면 아무것도 버리지 않는다(SAVED_PACKAGES).
 */
namespace WidgetMcpRunPackages
{
	TSharedPtr<FJsonObject> Save(const WidgetMcp::FSettings& Settings, const FString& RunFolder, FEditorMcpContext& Context, FEditorMcpError& OutError);
	TSharedPtr<FJsonObject> Discard(const WidgetMcp::FSettings& Settings, const FString& RunFolder, FEditorMcpContext& Context, FEditorMcpError& OutError);
}
