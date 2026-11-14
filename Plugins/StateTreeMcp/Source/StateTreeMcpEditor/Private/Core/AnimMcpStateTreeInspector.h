#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UStateTree;
class UStateTreeSchema;

/** 애셋 → JSON (DevelopmentGuide §4). 읽기 전용 — FindOrAddViewModel 과 ValidateStateTree 를 부르지 않는다 */
namespace AnimMcpStateTreeInspector
{
	/** 스키마 · 컨텍스트 · 파라미터 · 상태 트리 · 노드(값 포함) · 전환 · 바인딩 · revision · compile_state. BP 노드도 읽는다 */
	TSharedRef<FJsonObject> Inspect(const UStateTree& Tree);

	/** 스키마가 허용하는 노드 타입 + 프로퍼티. Kind = task · condition · evaluator · property_function, 비우면 전부 */
	TSharedRef<FJsonObject> ListNodeTypes(const UStateTreeSchema& Schema, const FString& Kind);
}
