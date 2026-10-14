#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpHttpBridge.h"
#include "Bridge/AnimMcpTypes.h"
#include "Editor.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/App.h"
#include "Misc/EngineVersion.h"
#include "Subsystems/AssetEditorSubsystem.h"

namespace AnimMcpTools
{
	namespace
	{
		const TCHAR* const SchemaVersion = TEXT("1.0");

		TSharedRef<FJsonObject> DescribePlugin(const TCHAR* Name)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(Name);
			Obj->SetBoolField(TEXT("found"), Plugin.IsValid());
			Obj->SetBoolField(TEXT("enabled"), Plugin.IsValid() && Plugin->IsEnabled());
			if (Plugin.IsValid())
			{
				Obj->SetStringField(TEXT("version"), Plugin->GetDescriptor().VersionName);
			}
			return Obj;
		}
	}

	void RegisterStatusTools(FAnimMcpDispatcher& Dispatcher, TWeakPtr<FAnimMcpHttpBridge> Bridge)
	{
		Dispatcher.RegisterTool(TEXT("get_editor_status"),
			TEXT("Editor/plugin health: engine version, project, thread, PIE state, related plugin status, open asset editors, registered tools."),
			[Bridge, &Dispatcher](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
				Result->SetStringField(TEXT("project"), FApp::GetProjectName());
				Result->SetStringField(TEXT("schema_version"), SchemaVersion);
				Result->SetBoolField(TEXT("game_thread"), IsInGameThread());
				Result->SetBoolField(TEXT("is_editor"), GIsEditor);
				Result->SetBoolField(TEXT("is_pie"), GEditor && GEditor->PlayWorld != nullptr);

				if (TSharedPtr<IPlugin> Self = IPluginManager::Get().FindPlugin(TEXT("AnimGraphMcp")))
				{
					Result->SetStringField(TEXT("plugin_version"), Self->GetDescriptor().VersionName);
				}

				TSharedRef<FJsonObject> Plugins = AnimMcpJson::MakeObject();
				Plugins->SetObjectField(TEXT("PythonScriptPlugin"), DescribePlugin(TEXT("PythonScriptPlugin")));
				Plugins->SetObjectField(TEXT("EditorScriptingUtilities"), DescribePlugin(TEXT("EditorScriptingUtilities")));
				Plugins->SetObjectField(TEXT("RemoteControl"), DescribePlugin(TEXT("RemoteControl")));
				Result->SetObjectField(TEXT("plugins"), Plugins);

				TArray<TSharedPtr<FJsonValue>> OpenAssets;
				if (GEditor)
				{
					if (UAssetEditorSubsystem* AssetEditors = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>())
					{
						for (UObject* Asset : AssetEditors->GetAllEditedAssets())
						{
							if (Asset)
							{
								OpenAssets.Add(MakeShared<FJsonValueString>(Asset->GetPathName()));
							}
						}
					}
				}
				Result->SetArrayField(TEXT("open_asset_editors"), OpenAssets);

				if (TSharedPtr<FAnimMcpHttpBridge> PinnedBridge = Bridge.Pin())
				{
					Result->SetNumberField(TEXT("port"), PinnedBridge->GetPort());
					Result->SetBoolField(TEXT("token_required"), PinnedBridge->IsTokenRequired());
					Result->SetStringField(TEXT("token_file"), PinnedBridge->GetTokenFilePath());
				}

				TArray<TSharedPtr<FJsonValue>> Tools;
				for (const FName ToolName : Dispatcher.GetToolNames())
				{
					TSharedRef<FJsonObject> ToolObj = AnimMcpJson::MakeObject();
					ToolObj->SetStringField(TEXT("name"), ToolName.ToString());
					if (const FString* Desc = Dispatcher.GetToolDescription(ToolName))
					{
						ToolObj->SetStringField(TEXT("description"), *Desc);
					}
					Tools.Add(MakeShared<FJsonValueObject>(ToolObj));
				}
				Result->SetArrayField(TEXT("tools"), Tools);

				return Result;
			});
	}
}
