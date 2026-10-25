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

	/** Linked Anim Layer (create_anim_layer_interface, implement_anim_layer_interface) — Phase 6-4b · (set_layer_inputs, add_anim_layers, remove_anim_layers) — Phase 7-4 */
	void RegisterLayerTools(FAnimMcpDispatcher& Dispatcher);

	/** Automation 테스트 (run_automation_tests, poll_automation_tests) — Phase 6-5 · (run_anim_scenario) PIE 런타임 시나리오 — Phase 7-5 */
	void RegisterAutomationTools(FAnimMcpDispatcher& Dispatcher);

	/** BP 변수 · 업데이트 함수 (add_blueprint_variable, remove_blueprint_variable, set_update_function) — Phase 7-1 */
	void RegisterVariableTools(FAnimMcpDispatcher& Dispatcher);

	/** 몽타주 콘텐츠 (create_anim_montage, set_montage_slots, set_montage_sections, add_skeleton_slot) — Phase 7-3 */
	void RegisterMontageTools(FAnimMcpDispatcher& Dispatcher);

	/** 스켈레톤 재할당 (reassign_skeleton) — Phase 7-6: 같은 본 이름의 두 스켈레톤으로 갈라진 애니 애셋을 한쪽으로 · (inspect_skeleton) AI 애니 생성 Phase 1 */
	void RegisterSkeletonTools(FAnimMcpDispatcher& Dispatcher);

	/** 시퀀스 additive 설정 (set_sequence_additive) — Phase 7-6: AimOffset 샘플 선행 조건(기준 포즈) */
	void RegisterSequenceTools(FAnimMcpDispatcher& Dispatcher);

	/** FBX 임포트 (import_animation_file) — AI 애니 생성 Phase 1 (Docs/AIAnimation) */
	void RegisterImportTools(FAnimMcpDispatcher& Dispatcher);

	/** IK 리타깃 (create_ik_rig, create_ik_retargeter, retarget_animations) — AI 애니 생성 Phase 1 */
	void RegisterRetargetTools(FAnimMcpDispatcher& Dispatcher);

	/** 애니메이션 검증 (validate_animation) — AI 애니 생성 Phase 1 · 요청 충족(expect · seams · profile_bones) Phase 2 */
	void RegisterValidationTools(FAnimMcpDispatcher& Dispatcher);

	/** 기존 모션 키 편집 (preview_animation_edits, apply_animation_edits) — AI 애니 생성 Phase 2 */
	void RegisterEditTools(FAnimMcpDispatcher& Dispatcher);

	/** 기존 모션 메타데이터 검색 (search_animations) — AI 애니 생성 Phase 2 */
	void RegisterSearchTools(FAnimMcpDispatcher& Dispatcher);

	/** 후보 → 정식 경로 승격 (promote_animation) — AI 애니 생성 Phase 7 */
	void RegisterPromoteTools(FAnimMcpDispatcher& Dispatcher);

	/** 그래프 변경 (preview_graph_operations, apply_graph_operations) */
	void RegisterGraphTools(FAnimMcpDispatcher& Dispatcher);

	/** 컴파일 (compile_animation_blueprint) */
	void RegisterCompileTools(FAnimMcpDispatcher& Dispatcher);
}
