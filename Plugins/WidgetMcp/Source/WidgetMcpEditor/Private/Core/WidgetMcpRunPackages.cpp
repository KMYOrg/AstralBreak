#include "Core/WidgetMcpRunPackages.h"

#include "AnimMcpLog.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Editor.h"
#include "Misc/PackageName.h"
#include "PackageTools.h"
#include "Subsystems/EditorAssetSubsystem.h"
#include "UObject/Package.h"
#include "UObject/UObjectHash.h"
#include "UObject/UObjectIterator.h"

namespace WidgetMcpRunPackages
{
	namespace RunPackagesPrivate
	{
		TArray<UPackage*> PackagesUnder(const FString& Folder)
		{
			TArray<UPackage*> Out;
			const FString Prefix = EditorMcpGuard::NormalizeFolderPath(Folder) + TEXT("/");
			for (TObjectIterator<UPackage> It; It; ++It)
			{
				if (It->GetOuter() == nullptr && !It->HasAnyFlags(RF_Transient) && It->GetName().StartsWith(Prefix, ESearchCase::IgnoreCase))
				{
					Out.Add(*It);
				}
			}
			Out.Sort([](const UPackage& A, const UPackage& B) { return A.GetName() < B.GetName(); });
			return Out;
		}

		UObject* MainAsset(UPackage* Package)
		{
			UObject* Asset = nullptr;
			ForEachObjectWithPackage(Package, [&Asset](UObject* Obj) { if (Obj->IsAsset()) { Asset = Obj; return false; } return true; }, /*bIncludeNestedObjects*/ false);
			return Asset;
		}

		TArray<FString> Names(const TArray<UPackage*>& Packages)
		{
			TArray<FString> Out;
			for (const UPackage* P : Packages) { Out.Add(P->GetName()); }
			return Out;
		}
	}

	using namespace RunPackagesPrivate;

	TSharedPtr<FJsonObject> Save(const WidgetMcp::FSettings& Settings, const FString& RunFolder, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		if (!WidgetMcp::CheckRunFolder(Settings, RunFolder, TEXT("run_path"), OutError))
		{
			return nullptr;
		}
		const TArray<UPackage*> Packages = PackagesUnder(RunFolder);
		if (Packages.Num() == 0)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("no packages under '%s'"), *RunFolder));
			return nullptr;
		}
		UEditorAssetSubsystem* Assets = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
		TArray<FString> Saved, Failed, Clean;
		for (UPackage* P : Packages)
		{
			if (!P->IsDirty() && FPackageName::DoesPackageExist(P->GetName()))
			{
				Clean.Add(P->GetName());
				continue;
			}
			UObject* Asset = MainAsset(P);
			// SaveLoadedAsset(bOnlyIfIsDirty=false) — quit_editor save_dirty 와 같은 경로(FEditorFileUtils::SaveDirtyPackages 는 실측에서 ABP 를 안 저장)
			if (Asset && Assets && Assets->SaveLoadedAsset(Asset, /*bOnlyIfIsDirty*/ false))
			{
				Saved.Add(P->GetName());
			}
			else
			{
				Failed.Add(P->GetName());
			}
		}
		if (Failed.Num())
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("failed"), WidgetMcp::StringArray(Failed));
			D->SetArrayField(TEXT("saved"), WidgetMcp::StringArray(Saved));
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::SaveFailed, FString::Printf(TEXT("%d package(s) under '%s' could not be saved (see log)"), Failed.Num(), *RunFolder), nullptr, D);
			return nullptr;
		}
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("run_path"), EditorMcpGuard::NormalizeFolderPath(RunFolder));
		Out->SetArrayField(TEXT("saved"), WidgetMcp::StringArray(Saved));
		Out->SetArrayField(TEXT("already_saved"), WidgetMcp::StringArray(Clean));
		UE_LOG(LogAnimGraphMcp, Log, TEXT("save_widget_run: %s — %d saved"), *RunFolder, Saved.Num());
		return Out;
	}

	TSharedPtr<FJsonObject> Discard(const WidgetMcp::FSettings& Settings, const FString& RunFolder, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		if (!WidgetMcp::CheckRunFolder(Settings, RunFolder, TEXT("run_path"), OutError))
		{
			return nullptr;
		}
		const TArray<UPackage*> Packages = PackagesUnder(RunFolder);
		TArray<FString> OnDisk;
		for (const UPackage* P : Packages)
		{
			if (FPackageName::DoesPackageExist(P->GetName()))
			{
				OnDisk.Add(P->GetName());
			}
		}
		if (OnDisk.Num())
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("saved_packages"), WidgetMcp::StringArray(OnDisk));
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest,
				FString::Printf(TEXT("%d package(s) under '%s' are saved on disk — discard only drops never-saved run packages; nothing was discarded"), OnDisk.Num(), *RunFolder), TEXT("SAVED_PACKAGES"), D);
			return nullptr;
		}
		const TArray<FString> Discarded = Names(Packages);
		if (Packages.Num())
		{
			for (UPackage* P : Packages)
			{
				ForEachObjectWithPackage(P, [](UObject* Obj) { if (Obj->IsAsset()) { FAssetRegistryModule::AssetDeleted(Obj); } return true; }, /*bIncludeNestedObjects*/ false);
			}
			FText Error;
			if (!UPackageTools::UnloadPackages(Packages, Error, /*bUnloadDirtyPackages*/ true))
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetArrayField(TEXT("packages"), WidgetMcp::StringArray(Discarded));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::Internal, FString::Printf(TEXT("UnloadPackages failed: %s"), *Error.ToString()), TEXT("UNLOAD_FAILED"), D);
				return nullptr;
			}
		}
		TArray<FString> Remaining;
		for (const FString& Name : Discarded)
		{
			if (UPackage* P = FindPackage(nullptr, *Name); P && P->IsDirty())
			{
				Remaining.Add(Name);
			}
		}
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("run_path"), EditorMcpGuard::NormalizeFolderPath(RunFolder));
		Out->SetArrayField(TEXT("discarded"), WidgetMcp::StringArray(Discarded));
		Out->SetArrayField(TEXT("still_dirty"), WidgetMcp::StringArray(Remaining));
		if (Remaining.Num())
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("STILL_DIRTY"), FString::Printf(TEXT("%d package(s) are still loaded and dirty after unload"), Remaining.Num()));
		}
		UE_LOG(LogAnimGraphMcp, Log, TEXT("discard_run_packages: %s — %d package(s)"), *RunFolder, Discarded.Num());
		return Out;
	}
}
