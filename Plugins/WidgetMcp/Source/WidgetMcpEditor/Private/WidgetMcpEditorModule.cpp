#include "Bridge/AnimMcpDispatcher.h"
#include "EditorMcpCoreModule.h"
#include "Modules/ModuleManager.h"

/**
 * UI 자동 생성 기능 플러그인 모듈 — Phase 0 뼈대 (Docs/Design/ui-autogen-pipeline.md §3-1 · §6).
 * 기능 이름만 코어에 등록해 get_editor_status.features[] 에 보이게 하고, widget 상태 필드를 더한다. Tool 은 Phase 1a 에서 이 등록 함수에 붙는다.
 * A6 · A7 스파이크 코드는 Private/Spike, 실행은 Automation WidgetMcp.Spike.* (Private/Tests).
 */
class FWidgetMcpEditorModule : public IModuleInterface
{
public:
	static constexpr const TCHAR* Feature = TEXT("WidgetMcp");

	virtual void StartupModule() override
	{
		IEditorMcpCoreModule& Core = IEditorMcpCoreModule::Get();
		Core.RegisterTools(Feature, [](FAnimMcpDispatcher& /*Dispatcher*/)
		{
			// Phase 1a: import_ui_textures · create_widget_blueprint · preview/apply_widget_spec · apply_widget_patch ·
			// export_widget_spec · compile_widget_blueprint · save_widget_run · render_widget · list_bind_widgets · discard_run_packages
		});
		Core.RegisterStatusSection(Feature, [](const TSharedRef<FJsonObject>& Result)
		{
			TSharedRef<FJsonObject> Widget = MakeShared<FJsonObject>();
			Widget->SetStringField(TEXT("phase"), TEXT("0-skeleton"));
			Widget->SetStringField(TEXT("note"), TEXT("No tools yet - Phase 1a adds them (Docs/Design/ui-autogen-pipeline.md section 6). Spike: automation WidgetMcp.Spike.*"));
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
