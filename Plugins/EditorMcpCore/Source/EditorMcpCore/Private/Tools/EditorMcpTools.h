#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class FAnimMcpDispatcher;
class FAnimMcpHttpBridge;

/** 코어가 직접 가진 Tool — 어느 기능 플러그인도 없을 때도 브리지 운용에 필요한 것만 */
namespace EditorMcpTools
{
	/**
	 * get_editor_status (토큰 면제). 브리지는 포트 · 토큰 설정을, DescribeFeatures 는 기능 플러그인이 더하는 필드
	 * (AnimGraphMcp → generation, StateTreeMcp → state_tree_edit_paths) · features[] 를 응답에 싣는다
	 */
	void RegisterStatusTools(FAnimMcpDispatcher& Dispatcher, TWeakPtr<FAnimMcpHttpBridge> Bridge, TFunction<void(const TSharedRef<FJsonObject>&)> DescribeFeatures);

	/** quit_editor — 에디터 종료(더티 패키지 처리 포함) */
	void RegisterEditorTools(FAnimMcpDispatcher& Dispatcher);

	/** run_automation_tests · poll_automation_tests — 에디터 안 Automation 실행(기능 시나리오 Tool 도 같은 잡 · poll 을 쓴다) */
	void RegisterAutomationTools(FAnimMcpDispatcher& Dispatcher);
}
