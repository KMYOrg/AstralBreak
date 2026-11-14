#pragma once

#include "CoreMinimal.h"

class FConfigFile;

/**
 * 에디터 MCP 공용 설정 읽기 — DefaultEngine.ini 의 새 [EditorMcp] 와 옛 [AnimGraphMcp] 를 둘 다 본다(2026-11-14 플러그인 분리).
 *
 *   배열(+Key=…)   두 섹션 값을 합친다 — [EditorMcp] 먼저, 그다음 [AnimGraphMcp]. 정규화 · 중복 제거는 호출자(AddUnique).
 *   값(Key=…)      [EditorMcp] 에 있으면 그 값, 없으면 [AnimGraphMcp].
 *
 * 공용 키: Port · bRequireToken · bAutoStart · ProtectedAssets · ProtectedPaths · StateTreeEditPaths.
 * 애니 기능 키(GenerationOutputPaths 등)는 AnimGraphMcp 플러그인 것이라 [AnimGraphMcp] 에 그대로 둔다.
 */
namespace EditorMcpSettings
{
	inline const TCHAR* const Section = TEXT("EditorMcp");
	inline const TCHAR* const LegacySection = TEXT("AnimGraphMcp");

	/** 두 섹션의 배열을 이어 붙인다 ([EditorMcp] 먼저) — GEngineIni */
	EDITORMCPCORE_API TArray<FString> GetArray(const TCHAR* Key);

	/** [EditorMcp] 우선. 어느 쪽에도 없으면 false (Out 은 그대로) — GEngineIni */
	EDITORMCPCORE_API bool GetInt(const TCHAR* Key, int32& Out);
	EDITORMCPCORE_API bool GetBool(const TCHAR* Key, bool& Out);

	/** 오류 메시지 · details.config 용 — "[EditorMcp] (or legacy [AnimGraphMcp]) <Key> in DefaultEngine.ini" */
	EDITORMCPCORE_API FString Describe(const TCHAR* Key);

	/** 같은 규칙을 메모리의 ini 하나로 — 시험용(GConfig 를 건드리지 않는다) */
	EDITORMCPCORE_API TArray<FString> GetArrayFromFile(const FConfigFile& File, const TCHAR* Key);
	EDITORMCPCORE_API bool GetIntFromFile(const FConfigFile& File, const TCHAR* Key, int32& Out);
}
