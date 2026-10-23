#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpHttpBridge.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetProtection.h"
#include "Core/AnimMcpGeneration.h"
#include "Editor.h"
#include "FileHelpers.h"
#include "HAL/PlatformProcess.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/App.h"
#include "Misc/EngineVersion.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "UObject/Package.h"

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
			TEXT("Editor/plugin health: engine version, project, thread, PIE state, related plugin status, open asset editors, registered tools, protection rules, generation paths (output_paths · import_source_roots · max_retarget_assets_per_call)."),
			[Bridge, &Dispatcher](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
				Result->SetStringField(TEXT("project"), FApp::GetProjectName());
				Result->SetStringField(TEXT("schema_version"), SchemaVersion);
				Result->SetBoolField(TEXT("game_thread"), IsInGameThread());
				Result->SetBoolField(TEXT("is_editor"), GIsEditor);
				Result->SetBoolField(TEXT("is_pie"), GEditor && GEditor->PlayWorld != nullptr);
				// Phase 6-2: quit_editor 뒤 프로세스 소멸 폴링용 · 보호 목록 · 저장 안 된 패키지 수
				Result->SetNumberField(TEXT("process_id"), FPlatformProcess::GetCurrentProcessId());
				Result->SetObjectField(TEXT("protection"), AnimMcpAssetProtection::DescribeRules());
				// AI 애니 생성: 출력·임포트 경로의 유일한 기준(ini) — anim_gen 은 이것을 읽는다
				Result->SetObjectField(TEXT("generation"), AnimMcpGeneration::DescribeSettings());
				{
					TArray<UPackage*> DirtyContent, DirtyWorlds;
					FEditorFileUtils::GetDirtyContentPackages(DirtyContent);
					FEditorFileUtils::GetDirtyWorldPackages(DirtyWorlds);
					Result->SetNumberField(TEXT("dirty_package_count"), DirtyContent.Num() + DirtyWorlds.Num());
				}

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
