#include "Core/WidgetMcpCommon.h"
#include "EditorMcpCoreModule.h"
#include "Modules/ModuleManager.h"
#include "Tools/WidgetMcpTools.h"

/**
 * UI 자동 생성 기능 플러그인 모듈 (Docs/Design/ui-autogen-pipeline.md §3-1 · §6).
 * 코어 브리지에 Tool 11개를 등록하고 get_editor_status 에 widget 섹션(설정 · Tool 목록)을 더한다.
 * Phase 0 스파이크(A6 · A7)는 Private/Spike + Automation WidgetMcp.Spike.* 로 남겨 둔다.
 */
class FWidgetMcpEditorModule : public IModuleInterface
{
public:
	static constexpr const TCHAR* Feature = TEXT("WidgetMcp");

	virtual void StartupModule() override
	{
		IEditorMcpCoreModule& Core = IEditorMcpCoreModule::Get();
		Core.RegisterTools(Feature, [](FAnimMcpDispatcher& Dispatcher) { WidgetMcpTools::Register(Dispatcher); });
		Core.RegisterStatusSection(Feature, [](const TSharedRef<FJsonObject>& Result)
		{
			TSharedRef<FJsonObject> Widget = WidgetMcp::SettingsToJson(WidgetMcp::LoadSettings());
			Widget->SetStringField(TEXT("phase"), TEXT("1a"));
			Widget->SetArrayField(TEXT("tools"), WidgetMcp::StringArray(WidgetMcpTools::ToolNames()));
			Widget->SetStringField(TEXT("font"), TEXT("engine default (Roboto + Korean fallback) — project font is decided in Phase 1b"));
			Result->SetObjectField(TEXT("widget"), Widget);
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

IMPLEMENT_MODULE(FWidgetMcpEditorModule, WidgetMcpEditor)
