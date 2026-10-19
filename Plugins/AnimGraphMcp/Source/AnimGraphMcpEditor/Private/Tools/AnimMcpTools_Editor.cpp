#include "AnimMcpTools.h"

#include "AnimMcpLog.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Containers/Ticker.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "FileHelpers.h"
#include "HAL/PlatformProcess.h"
#include "Subsystems/EditorAssetSubsystem.h"
#include "UObject/Package.h"
#include "UObject/UObjectHash.h"

namespace AnimMcpTools
{
	namespace
	{
		void CollectDirtyPackages(TArray<UPackage*>& OutContent, TArray<UPackage*>& OutWorlds)
		{
			OutContent.Reset();
			OutWorlds.Reset();
			FEditorFileUtils::GetDirtyContentPackages(OutContent);
			FEditorFileUtils::GetDirtyWorldPackages(OutWorlds);
		}

		TArray<TSharedPtr<FJsonValue>> PackageNames(const TArray<UPackage*>& Packages, const TCHAR* Kind)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const UPackage* P : Packages)
			{
				if (!P) { continue; }
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetStringField(TEXT("package"), P->GetName());
				Obj->SetStringField(TEXT("kind"), Kind);
				Out.Add(MakeShared<FJsonValueObject>(Obj));
			}
			return Out;
		}
	}

	void RegisterEditorTools(FAnimMcpDispatcher& Dispatcher)
	{
		/**
		 * quit_editor — 에디터 종료 (Phase 6-2, 사용자 확정: 더티 패키지가 있으면 save_dirty / discard_dirty 없이는 거부).
		 * 경로: 응답을 쓴 뒤 다음 틱에 GEngine->DeferredCommands "QUIT_EDITOR" → UUnrealEdEngine::CloseEditor()(EditorServer.cpp:5775-5779)
		 *   = PIE 종료 + RequestEngineExit (UnrealEdEngine.cpp:935-950). CanCloseEditor 의 저장 프롬프트(MainFrameHandler.h:164)를
		 *   거치지 않으므로 더티 처리는 여기서 명시적으로 한다.
		 * 응답은 OnComplete 안에서 동기로 소켓에 쓰이고(HttpConnection.cpp:229-246), 종료 명령은 FTSTicker 로 한 프레임 미뤄
		 * HTTP 모듈이 최소 한 번 더 틱하게 한다 (LaunchEngineLoop.cpp:6072 코어 티커 → :6078 DeferredCommands).
		 */
		Dispatcher.RegisterTool(TEXT("quit_editor"),
			TEXT("Request the editor to exit (ends PIE first). Params: save_dirty? (default false; saves dirty CONTENT packages, maps are never saved by this tool), discard_dirty? (default false; quit even if unsaved packages remain). With neither, unsaved packages make the call fail with DIRTY_PACKAGES and the editor keeps running. Returns process_id for polling."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const bool bSaveDirty = Context.Request.GetOptionalBool(TEXT("save_dirty"), false);
				const bool bDiscardDirty = Context.Request.GetOptionalBool(TEXT("discard_dirty"), false);

				TArray<UPackage*> DirtyContent, DirtyWorlds;
				CollectDirtyPackages(DirtyContent, DirtyWorlds);

				TArray<TSharedPtr<FJsonValue>> Saved;
				if (bSaveDirty && DirtyContent.Num() > 0)
				{
					// 패키지마다 애셋 객체를 찾아 SaveLoadedAsset — save_animation_blueprint 와 같은 경로 (프롬프트 없음).
					// FEditorFileUtils::SaveDirtyPackages(bFastSave) 는 실측에서 더티 ABP 를 저장하지 않고 false 를 돌려줬다
					UEditorAssetSubsystem* AssetSubsystem = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
					for (UPackage* P : DirtyContent)
					{
						UObject* Asset = nullptr;
						ForEachObjectWithPackage(P, [&Asset](UObject* Obj) { if (Obj->IsAsset()) { Asset = Obj; return false; } return true; }, /*bIncludeNestedObjects*/ false);
						if (Asset && AssetSubsystem && AssetSubsystem->SaveLoadedAsset(Asset, /*bOnlyIfIsDirty*/ false))
						{
							Saved.Add(MakeShared<FJsonValueString>(P->GetName()));
						}
						else
						{
							UE_LOG(LogAnimGraphMcp, Warning, TEXT("quit_editor save_dirty: could not save %s (asset %s)"), *P->GetName(), *GetNameSafe(Asset));
						}
					}
					CollectDirtyPackages(DirtyContent, DirtyWorlds);
					if (DirtyContent.Num() > 0)
					{
						TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
						Details->SetArrayField(TEXT("dirty_packages"), PackageNames(DirtyContent, TEXT("content")));
						Details->SetArrayField(TEXT("saved_packages"), Saved);
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::SaveFailed,
							FString::Printf(TEXT("save_dirty could not save %d content package(s) (read-only file? see log); editor keeps running"), DirtyContent.Num()), Details);
						return nullptr;
					}
				}

				TArray<TSharedPtr<FJsonValue>> Remaining = PackageNames(DirtyContent, TEXT("content"));
				Remaining.Append(PackageNames(DirtyWorlds, TEXT("world")));
				if (Remaining.Num() > 0 && !bDiscardDirty)
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetArrayField(TEXT("dirty_packages"), Remaining);
					Details->SetArrayField(TEXT("saved_packages"), Saved);
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::DirtyPackages,
						FString::Printf(TEXT("%d unsaved package(s); pass save_dirty=true (content packages) or discard_dirty=true. Editor keeps running"), Remaining.Num()), Details);
					return nullptr;
				}
				if (Remaining.Num() > 0)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("DISCARDING_DIRTY"), FString::Printf(TEXT("Quitting with %d unsaved package(s); their changes are lost"), Remaining.Num()));
				}

				const bool bWasPie = GEditor && GEditor->PlayWorld != nullptr;
				if (bWasPie)
				{
					Context.AddDiagnostic(TEXT("info"), TEXT("PIE_ENDED"), TEXT("PIE session is ended by CloseEditor before exit"));
				}

				FTSTicker::GetCoreTicker().AddTicker(TEXT("AnimGraphMcp.QuitEditor"), 0.0f, [](float) -> bool
				{
					if (GEngine)
					{
						UE_LOG(LogAnimGraphMcp, Display, TEXT("quit_editor: issuing QUIT_EDITOR"));
						GEngine->DeferredCommands.AddUnique(TEXT("QUIT_EDITOR"));
					}
					return false;
				});

				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetBoolField(TEXT("quit_requested"), true);
				Result->SetNumberField(TEXT("process_id"), FPlatformProcess::GetCurrentProcessId());
				Result->SetArrayField(TEXT("saved_packages"), Saved);
				Result->SetArrayField(TEXT("discarded_packages"), Remaining);
				Result->SetBoolField(TEXT("was_pie"), bWasPie);
				return Result;
			});
	}
}
