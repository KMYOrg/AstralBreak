#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Modules/ModuleInterface.h"
#include "Modules/ModuleManager.h"

class FAnimMcpDispatcher;

/**
 * 에디터 MCP 공용 코어 모듈 — 기능 플러그인이 Tool 을 등록하는 창구.
 *
 * 기능 플러그인(AnimGraphMcp · StateTreeMcp · WidgetMcp)은 StartupModule 에서 RegisterTools 를, ShutdownModule 에서 UnregisterTools 를 부른다.
 * 코어는 브리지를 시작할 때마다(에디터 기동 · EditorMcp.Start) 새 디스패처에 등록 함수를 전부 다시 돌리고,
 * 이미 떠 있으면 그 자리에서 등록하고 라우트를 붙인다. 등록 함수가 만든 Tool 은 그 기능 소유가 되어 UnregisterTools 때 함께 빠진다.
 *
 * 설정은 DefaultEngine.ini 의 [EditorMcp] 와 옛 [AnimGraphMcp] 를 둘 다 읽는다(Core/EditorMcpSettings.h).
 * 콘솔: EditorMcp.Start / Stop / Status (옛 이름 AnimGraphMcp.* 도 같은 동작).
 */
class IEditorMcpCoreModule : public IModuleInterface
{
public:
	/** 기능 이름 → 그 기능의 Tool 을 디스패처에 등록하는 함수 */
	using FRegisterToolsFn = TFunction<void(FAnimMcpDispatcher& Dispatcher)>;

	/** get_editor_status 결과에 기능별 필드를 더하는 함수 (예: AnimGraphMcp → generation, StateTreeMcp → state_tree_edit_paths) */
	using FDescribeStatusFn = TFunction<void(const TSharedRef<FJsonObject>& Result)>;

	static constexpr const TCHAR* ModuleName = TEXT("EditorMcpCore");

	/** 시작 경로용 — 없으면 로드한다 */
	static IEditorMcpCoreModule& Get()
	{
		return FModuleManager::LoadModuleChecked<IEditorMcpCoreModule>(ModuleName);
	}

	/** 종료 경로용 — 이미 내려갔으면 null (종료 중에 다시 로드하지 않는다) */
	static IEditorMcpCoreModule* GetIfLoaded()
	{
		return FModuleManager::GetModulePtr<IEditorMcpCoreModule>(ModuleName);
	}

	/** 같은 Feature 로 다시 부르면 등록 함수를 바꾼다. 브리지가 떠 있으면 바로 등록 · 라우트 바인드 */
	virtual void RegisterTools(FName Feature, FRegisterToolsFn Register) = 0;

	/** 그 기능의 등록 함수 · 상태 필드를 지우고, 브리지가 떠 있으면 Tool · 라우트를 뗀다 */
	virtual void UnregisterTools(FName Feature) = 0;

	/** get_editor_status 에 기능별 필드를 더한다. 같은 Feature 로 다시 부르면 바꾼다 */
	virtual void RegisterStatusSection(FName Feature, FDescribeStatusFn Describe) = 0;

	/** 등록된 기능 이름 (등록 순) */
	virtual TArray<FName> GetFeatures() const = 0;

	virtual bool IsBridgeRunning() const = 0;
};
