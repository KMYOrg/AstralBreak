#include "Bridge/AnimMcpDispatcher.h"
#include "Core/AnimMcpStateTreeAsset.h"
#include "EditorMcpCoreModule.h"
#include "Modules/ModuleManager.h"
#include "Tools/StateTreeMcpTools.h"

/**
 * StateTree 기능 플러그인 모듈 (2026-11-14 AnimGraphMcp 에서 분리) — StateTree Tool 9개를 EditorMcpCore 에 등록한다.
 * 설정: StateTreeEditPaths 를 DefaultEngine.ini 의 [EditorMcp] 와 옛 [AnimGraphMcp] 에서 읽는다.
 * get_editor_status 의 state_tree_edit_paths 필드는 여기서 더한다(필드 이름 · 모양은 분리 전과 같다).
 * 시험: Automation StateTreeMcp.* (분리 전 AnimGraphMcp.StateTree.*).
 */
class FStateTreeMcpEditorModule : public IModuleInterface
{
public:
	static constexpr const TCHAR* Feature = TEXT("StateTreeMcp");

	virtual void StartupModule() override
	{
		IEditorMcpCoreModule& Core = IEditorMcpCoreModule::Get();
		Core.RegisterTools(Feature, [](FAnimMcpDispatcher& Dispatcher)
		{
			StateTreeMcpTools::RegisterStateTreeTools(Dispatcher);
		});
		Core.RegisterStatusSection(Feature, [](const TSharedRef<FJsonObject>& Result)
		{
			TArray<TSharedPtr<FJsonValue>> EditPaths;
			for (const FString& Path : AnimMcpStateTreeAsset::GetEditPaths())
			{
				EditPaths.Add(MakeShared<FJsonValueString>(Path));
			}
			Result->SetArrayField(TEXT("state_tree_edit_paths"), EditPaths);
		});
	}

	virtual void ShutdownModule() override
	{
		if (IEditorMcpCoreModule* Core = IEditorMcpCoreModule::GetIfLoaded())
		{
			Core->UnregisterTools(Feature);
		}
	}
};

IMPLEMENT_MODULE(FStateTreeMcpEditorModule, StateTreeMcpEditor)
