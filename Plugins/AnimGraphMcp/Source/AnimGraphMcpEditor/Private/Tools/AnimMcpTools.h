#pragma once

#include "CoreMinimal.h"

class FAnimMcpDispatcher;
class FAnimMcpHttpBridge;

/** Tool 핸들러 등록 — 파일별로 한 묶음. 새 Tool 은 여기 선언 + Tools/ 아래 .cpp 추가 */
namespace AnimMcpTools
{
	/** 상태 조회 (get_editor_status). 브리지는 포트·토큰 설정을 응답에 싣기 위해 받는다 */
	void RegisterStatusTools(FAnimMcpDispatcher& Dispatcher, TWeakPtr<FAnimMcpHttpBridge> Bridge);

	/** 읽기 전용 조회 (get_anim_blueprint_info) */
	void RegisterInspectTools(FAnimMcpDispatcher& Dispatcher);
}
