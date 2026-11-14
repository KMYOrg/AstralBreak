#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "PropertyBindingPath.h"

class UStateTreeEditorData;

/**
 * 바인딩 사전 검증 (DevelopmentGuide §2-4 · §2-7 · §10 D-6, 시제품 = Phase 0 E4 PreflightBinding).
 * 컴파일 성공은 바인딩이 남았다는 증거가 아니다 — 인스턴스 소스 · 대상 오타는 컴파일이 조용히 지운다. 그래서 넣기 전에 여기서 막는다.
 *
 * 범위는 GetBindableStructs 가 단일 원천이고 실제 데이터를 따라가므로, 같은 배치에서 만드는 노드는 데이터가 생기기 전에 판정할 수 없다.
 * 범위 규칙을 여기서 흉내 내지 않는다: 경로 · 타입 · 메뉴는 CheckPathsAndTypes 가 구조체만으로 보고, 범위는 CheckScope 가 데이터가 있을 때 본다.
 * 판단 순서: 범위 → 소스 경로 → 대상 경로 → 메뉴 노출 → 타입.
 */
namespace AnimMcpStateTreeBindings
{
	struct FCheck
	{
		/** 비어 있으면 통과. BINDING_OUT_OF_SCOPE · BAD_SOURCE_PATH · BAD_TARGET_PATH · NOT_BINDABLE · INCOMPATIBLE_TYPES */
		FString Code;
		FString Detail;

		bool IsOk() const { return Code.IsEmpty(); }
	};

	/** 바인딩 한쪽 끝. PlannedStruct 가 있으면 아직 없는 노드 — 데이터 대신 인스턴스 구조체로 푼다 */
	struct FEndpoint
	{
		FPropertyBindingPath Path;
		const UStruct* PlannedStruct = nullptr;
	};

	/** 범위를 뺀 전부. 데이터를 바꾸지 않는다 */
	FCheck CheckPathsAndTypes(const UStateTreeEditorData& Data, const FEndpoint& Source, const FEndpoint& Target);

	/** 소스가 대상의 GetBindableStructs 에 있는가. 양쪽 다 실제 데이터에 있어야 한다 */
	FCheck CheckScope(const UStateTreeEditorData& Data, const FPropertyBindingPath& Source, const FPropertyBindingPath& Target);

	/** 살아 있는 데이터로 전부 — 범위 → 경로 · 타입 */
	FCheck Preflight(const UStateTreeEditorData& Data, const FPropertyBindingPath& Source, const FPropertyBindingPath& Target);

	/** 구조체의 프로퍼티 표 — name · type · usage · bindable(엔진 메뉴에 나오는가) */
	TArray<TSharedPtr<FJsonValue>> DescribeProperties(const UStruct* Struct);

	/** list_state_tree_bindable_sources — 대상 노드의 GetBindableStructs 결과. 메뉴에 없는 프로퍼티는 빼고 hidden_properties 로 센다(D-6) */
	TSharedRef<FJsonObject> ListSources(const UStateTreeEditorData& Data, const FGuid& TargetId);
}
