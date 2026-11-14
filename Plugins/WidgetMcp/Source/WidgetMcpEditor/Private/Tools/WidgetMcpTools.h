#pragma once

#include "CoreMinimal.h"
#include "EditorMcp.h"

/** WidgetMcp Tool 등록 — 모듈(코어 RegisterTools)과 자동 시험(로컬 디스패처)이 같이 쓴다 */
namespace WidgetMcpTools
{
	void Register(FEditorMcpDispatcher& Dispatcher);
	const TArray<FString>& ToolNames();
}
