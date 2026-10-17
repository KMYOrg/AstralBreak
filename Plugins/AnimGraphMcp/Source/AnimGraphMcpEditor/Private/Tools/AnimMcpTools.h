#pragma once

#include "CoreMinimal.h"

class FAnimMcpDispatcher;
class FAnimMcpHttpBridge;

/** Tool 핸들러 등록 — 파일별로 한 묶음. 새 Tool 은 여기 선언 + Tools/ 아래 .cpp 추가 */
namespace AnimMcpTools
{
	/** 상태 조회 (get_editor_status). 브리지는 포트·토큰 설정을 응답에 싣기 위해 받는다 */
	void RegisterStatusTools(FAnimMcpDispatcher& Dispatcher, TWeakPtr<FAnimMcpHttpBridge> Bridge);

	/** 읽기 전용 조회 (get_anim_blueprint_info, get_anim_graph_structure) */
	void RegisterInspectTools(FAnimMcpDispatcher& Dispatcher);

	/** 애셋 (list_animation_assets, create_animation_blueprint, save_animation_blueprint, duplicate_animation_blueprint, delete_animation_blueprint, create_blendspace) */
	void RegisterAssetTools(FAnimMcpDispatcher& Dispatcher);

	/** 에디터 프로세스 (quit_editor) */
	void RegisterEditorTools(FAnimMcpDispatcher& Dispatcher);

	/** Linked Anim Layer (create_anim_layer_interface, implement_anim_layer_interface) — Phase 6-4b */
	void RegisterLayerTools(FAnimMcpDispatcher& Dispatcher);

	/** Automation 테스트 (run_automation_tests, poll_automation_tests) — Phase 6-5 */
	void RegisterAutomationTools(FAnimMcpDispatcher& Dispatcher);

	/** 그래프 변경 (preview_graph_operations, apply_graph_operations) */
	void RegisterGraphTools(FAnimMcpDispatcher& Dispatcher);

	/** 컴파일 (compile_animation_blueprint) */
	void RegisterCompileTools(FAnimMcpDispatcher& Dispatcher);
}
