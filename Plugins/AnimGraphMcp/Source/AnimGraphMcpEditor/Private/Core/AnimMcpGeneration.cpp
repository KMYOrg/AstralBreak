#include "AnimMcpGeneration.h"

#include "AnimMcpAssetResolver.h"
#include "AnimMcpLog.h"
#include "AnimMcpMontage.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "HAL/FileManager.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "UObject/Package.h"
#include "UObject/UObjectIterator.h"

namespace AnimMcpGeneration
{
	namespace
	{
		const TCHAR* const ConfigSection = TEXT("AnimGraphMcp");

		/** "/Game/A" · "/Game/A/" → "/Game/A/" */
		FString NormalizePrefix(const FString& Raw)
		{
			FString Path = Raw.TrimStartAndEnd();
			if (Path.IsEmpty())
			{
				return Path;
			}
			if (!Path.StartsWith(TEXT("/")))
			{
				Path = TEXT("/") + Path;
			}
			if (!Path.EndsWith(TEXT("/")))
			{
				Path += TEXT("/");
			}
			return Path;
		}

		/** 프로젝트 기준 상대 또는 절대 → "D:/Proj/Saved/AnimGen/Import/" */
		FString NormalizeDirectory(const FString& Raw)
		{
			FString Dir = Raw.TrimStartAndEnd();
			if (Dir.IsEmpty())
			{
				return Dir;
			}
			// ProjectDir() 자체가 상대 경로("../../../../../UE5Projects/X/")라 두 인자 버전은 상대 경로를 돌려준다 — 이어 붙인 뒤 한 인자 버전으로 푼다
			Dir = FPaths::ConvertRelativePathToFull(FPaths::IsRelative(Dir) ? FPaths::Combine(FPaths::ProjectDir(), Dir) : Dir);
			FPaths::NormalizeDirectoryName(Dir);
			return Dir + TEXT("/");
		}

		FSettings LoadSettings()
		{
			FSettings Settings;
			TArray<FString> Raw;
			GConfig->GetArray(ConfigSection, TEXT("GenerationOutputPaths"), Raw, GEngineIni);
			for (const FString& Entry : Raw)
			{
				const FString Normalized = NormalizePrefix(Entry);
				// 마운트 루트("/Game/") 자체는 허용 목록이 아니라 "전부 허용" 이 된다 — 받지 않는다
				if (!Normalized.IsEmpty() && FPackageName::IsValidLongPackageName(Normalized.LeftChop(1)))
				{
					Settings.OutputPaths.AddUnique(Normalized);
				}
				else
				{
					UE_LOG(LogAnimGraphMcp, Warning, TEXT("Ignoring [%s] GenerationOutputPaths entry '%s' (needs a folder below a mount root, e.g. /Game/Animation/Generated/)"), ConfigSection, *Entry);
				}
			}
			Raw.Reset();
			GConfig->GetArray(ConfigSection, TEXT("ImportSourceRoots"), Raw, GEngineIni);
			for (const FString& Entry : Raw)
			{
				const FString Normalized = NormalizeDirectory(Entry);
				if (!Normalized.IsEmpty())
				{
					Settings.ImportSourceRoots.AddUnique(Normalized);
				}
			}
			Raw.Reset();
			GConfig->GetArray(ConfigSection, TEXT("AnimationTagFiles"), Raw, GEngineIni);
			for (const FString& Entry : Raw)
			{
				FString File = Entry.TrimStartAndEnd();
				if (File.IsEmpty())
				{
					continue;
				}
				File = FPaths::ConvertRelativePathToFull(FPaths::IsRelative(File) ? FPaths::Combine(FPaths::ProjectDir(), File) : File);
				FPaths::NormalizeFilename(File);
				Settings.AnimationTagFiles.AddUnique(File);
			}
			int32 MaxAssets = Settings.MaxRetargetAssetsPerCall;
			if (GConfig->GetInt(ConfigSection, TEXT("MaxRetargetAssetsPerCall"), MaxAssets, GEngineIni))
			{
				Settings.MaxRetargetAssetsPerCall = FMath::Max(1, MaxAssets);
			}
			UE_LOG(LogAnimGraphMcp, Log, TEXT("Generation: %d output paths, %d import roots, max %d assets per retarget, %d animation tag file(s) ([%s] in %s)"),
				Settings.OutputPaths.Num(), Settings.ImportSourceRoots.Num(), Settings.MaxRetargetAssetsPerCall, Settings.AnimationTagFiles.Num(), ConfigSection, *GEngineIni);
			return Settings;
		}

		/** FEditorFileUtils::GetDirtyContentPackages 와 같은 제외 규칙 — 단 맵도 포함하고, 그 함수처럼 패키지를 건드리는 부작용이 없다 */
		bool IsTrackedPackage(const UPackage* Package)
		{
			if (Package->GetOuter() != nullptr || Package == GetTransientPackage() || Package->HasAnyFlags(RF_Transient))
			{
				return false;
			}
			if (Package->HasAnyPackageFlags(PKG_CompiledIn | PKG_PlayInEditor))
			{
				return false;
			}
			return FPackageName::IsValidLongPackageName(Package->GetName(), /*bIncludeReadOnlyRoots*/ false);
		}

		void CollectDirty(TSet<FName>& Out)
		{
			for (TObjectIterator<UPackage> It; It; ++It)
			{
				if (It->IsDirty() && IsTrackedPackage(*It))
				{
					Out.Add(It->GetFName());
				}
			}
		}
	}

	const FSettings& GetSettings()
	{
		static const FSettings Settings = LoadSettings();
		return Settings;
	}

	TArray<TSharedPtr<FJsonValue>> ToJsonArray(const TArray<FString>& Values)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FString& V : Values) { Out.Add(MakeShared<FJsonValueString>(V)); }
		return Out;
	}

	TSharedRef<FJsonObject> DescribeSettings()
	{
		const FSettings& Settings = GetSettings();
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetArrayField(TEXT("output_paths"), ToJsonArray(Settings.OutputPaths));
		Obj->SetArrayField(TEXT("import_source_roots"), ToJsonArray(Settings.ImportSourceRoots));
		Obj->SetNumberField(TEXT("max_retarget_assets_per_call"), Settings.MaxRetargetAssetsPerCall);
		Obj->SetArrayField(TEXT("animation_tag_files"), ToJsonArray(Settings.AnimationTagFiles));
		return Obj;
	}

	FString NormalizeFolderPath(const FString& Path)
	{
		FString Folder = Path.TrimStartAndEnd();
		while (Folder.Len() > 1 && Folder.EndsWith(TEXT("/")))
		{
			Folder.LeftChopInline(1);
		}
		return Folder;
	}

	bool IsOutputPathAllowed(const FString& Path)
	{
		// 애셋 경로("/Game/A/B.B")는 패키지로, 폴더는 끝에 '/' 를 붙여 접두 비교 — "/Game/Animation/TestX" 가 "/Game/Animation/Test/" 에 걸리지 않게
		const FString AsDir = NormalizeFolderPath(AnimMcpAssetResolver::ToPackagePath(Path)) + TEXT("/");
		for (const FString& Prefix : GetSettings().OutputPaths)
		{
			if (AsDir.StartsWith(Prefix, ESearchCase::IgnoreCase))
			{
				return true;
			}
		}
		return false;
	}

	bool EnsureOutputPathAllowed(const FString& Path, const TCHAR* Field, FAnimMcpError& OutError)
	{
		const FString Package = NormalizeFolderPath(AnimMcpAssetResolver::ToPackagePath(Path));
		FText Reason;
		if (Package.IsEmpty() || !FPackageName::IsValidLongPackageName(Package, /*bIncludeReadOnlyRoots*/ false, &Reason))
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			Details->SetStringField(TEXT("reason"), TEXT("INVALID_PATH"));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest,
				FString::Printf(TEXT("'%s' is not a valid content path (%s)"), *Path, *Reason.ToString()), Details);
			return false;
		}
		if (IsOutputPathAllowed(Path))
		{
			return true;
		}
		TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
		Details->SetStringField(TEXT("field"), Field);
		Details->SetStringField(TEXT("path"), Package);
		Details->SetArrayField(TEXT("allowed"), ToJsonArray(GetSettings().OutputPaths));
		Details->SetStringField(TEXT("config"), FString::Printf(TEXT("[%s] GenerationOutputPaths in DefaultEngine.ini"), ConfigSection));
		OutError = FAnimMcpError::Make(AnimMcpErrorCodes::OutputPathNotAllowed,
			GetSettings().OutputPaths.Num() == 0
				? FString::Printf(TEXT("No [%s] GenerationOutputPaths configured — generation tools write nowhere"), ConfigSection)
				: FString::Printf(TEXT("'%s' is outside [%s] GenerationOutputPaths"), *Package, ConfigSection),
			Details);
		return false;
	}

	bool ResolveImportSource(const FString& File, FString& OutAbsolute, FAnimMcpError& OutError)
	{
		auto Bad = [&OutError, &File](const TCHAR* Reason, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), TEXT("file"));
			Details->SetStringField(TEXT("reason"), Reason);
			Details->SetStringField(TEXT("file"), File);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
			return false;
		};

		FString Path = File.TrimStartAndEnd();
		if (Path.IsEmpty())
		{
			return Bad(TEXT("MISSING"), TEXT("Missing or empty required string parameter 'file'"));
		}
		if (FPaths::IsRelative(Path))
		{
			return Bad(TEXT("RELATIVE_PATH"), FString::Printf(TEXT("'%s' is relative — pass an absolute path under [%s] ImportSourceRoots"), *Path, ConfigSection));
		}
		// ".." 를 접고 '/' 로 통일한 뒤 루트와 비교한다
		Path = FPaths::ConvertRelativePathToFull(Path);
		FPaths::NormalizeFilename(Path);

		const TArray<FString>& Roots = GetSettings().ImportSourceRoots;
		const bool bUnderRoot = Roots.ContainsByPredicate([&Path](const FString& Root) { return FPaths::IsUnderDirectory(Path, Root); });
		if (!bUnderRoot)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("file"), Path);
			Details->SetArrayField(TEXT("allowed"), ToJsonArray(Roots));
			Details->SetStringField(TEXT("config"), FString::Printf(TEXT("[%s] ImportSourceRoots in DefaultEngine.ini"), ConfigSection));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ImportSourceNotAllowed,
				Roots.Num() == 0
					? FString::Printf(TEXT("No [%s] ImportSourceRoots configured — imports are disabled"), ConfigSection)
					: FString::Printf(TEXT("'%s' is outside [%s] ImportSourceRoots"), *Path, ConfigSection),
				Details);
			return false;
		}
		if (!IFileManager::Get().FileExists(*Path))
		{
			return Bad(TEXT("FILE_NOT_FOUND"), FString::Printf(TEXT("No file at '%s'"), *Path));
		}
		OutAbsolute = Path;
		return true;
	}

	FDirtyGuard::FDirtyGuard()
	{
		CollectDirty(DirtyBefore);
	}

	void FDirtyGuard::GetNewlyDirty(TArray<FString>& OutAllowed, TArray<FString>& OutUnexpected) const
	{
		TSet<FName> DirtyNow;
		CollectDirty(DirtyNow);
		for (const FName& Name : DirtyNow)
		{
			if (DirtyBefore.Contains(Name))
			{
				continue;
			}
			const FString PackageName = Name.ToString();
			(IsOutputPathAllowed(PackageName) ? OutAllowed : OutUnexpected).Add(PackageName);
		}
		OutAllowed.Sort();
		OutUnexpected.Sort();
	}

	bool FDirtyGuard::Check(FAnimMcpError& OutError) const
	{
		TArray<FString> Allowed, Unexpected;
		GetNewlyDirty(Allowed, Unexpected);
		if (Unexpected.Num() == 0)
		{
			return true;
		}
		TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
		Details->SetArrayField(TEXT("unexpected"), ToJsonArray(Unexpected));
		Details->SetArrayField(TEXT("allowed"), ToJsonArray(Allowed));
		OutError = FAnimMcpError::Make(AnimMcpErrorCodes::UnexpectedDirty,
			FString::Printf(TEXT("%d package(s) outside [%s] GenerationOutputPaths became dirty during this call — nothing was saved (first: %s)"),
				Unexpected.Num(), ConfigSection, *Unexpected[0]), Details);
		UE_LOG(LogAnimGraphMcp, Warning, TEXT("UNEXPECTED_DIRTY: %s"), *FString::Join(Unexpected, TEXT(", ")));
		return false;
	}

	namespace
	{
		/** 새 애셋 자리 — 허용 목록 · ASSET_EXISTS(디스크·메모리) 검사 후 패키지를 만든다 */
		UPackage* PrepareNewAsset(const FString& AssetPath, const TCHAR* Field, FString& OutAssetName, FAnimMcpError& OutError)
		{
			if (!EnsureOutputPathAllowed(AssetPath, Field, OutError))
			{
				return nullptr;
			}
			const FString PackagePath = AnimMcpAssetResolver::ToPackagePath(AssetPath);
			const FString ObjectPath = AnimMcpAssetResolver::NormalizeObjectPath(PackagePath);
			OutAssetName = FPackageName::GetLongPackageAssetName(PackagePath);
			auto Exists = [&](const FString& Why)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), Field);
				Details->SetStringField(TEXT("asset_path"), ObjectPath);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' %s — generation tools never overwrite; pick another name"), *ObjectPath, *Why), Details);
				return nullptr;
			};
			if (AnimMcpAssetResolver::AssetExists(ObjectPath))
			{
				return Exists(TEXT("already exists"));
			}
			UPackage* Package = CreatePackage(*PackagePath);
			if (!Package)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("CreatePackage failed for '%s'"), *PackagePath));
				return nullptr;
			}
			Package->FullyLoad();
			if (FindObject<UObject>(Package, *OutAssetName))
			{
				return Exists(TEXT("still exists in memory (deleted but not garbage collected?)"));
			}
			return Package;
		}
	}

	UObject* DuplicateAssetObject(UObject* Source, const FString& AssetPath, const TCHAR* Field, FAnimMcpError& OutError)
	{
		FString AssetName;
		UPackage* Package = PrepareNewAsset(AssetPath, Field, AssetName, OutError);
		if (!Package)
		{
			return nullptr;
		}
		UObject* Asset = StaticDuplicateObject(Source, Package, FName(*AssetName));
		if (!Asset)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("StaticDuplicateObject returned null for '%s'"), *Source->GetPathName()));
			return nullptr;
		}
		Asset->SetFlags(RF_Public | RF_Standalone | RF_Transactional);
		FAssetRegistryModule::AssetCreated(Asset);
		Asset->MarkPackageDirty();
		return Asset;
	}

	UObject* CreateAssetObject(UClass* Class, const FString& AssetPath, const TCHAR* Field, FAnimMcpError& OutError)
	{
		FString AssetName;
		UPackage* Package = PrepareNewAsset(AssetPath, Field, AssetName, OutError);
		if (!Package)
		{
			return nullptr;
		}
		UObject* Asset = NewObject<UObject>(Package, Class, FName(*AssetName), RF_Public | RF_Standalone | RF_Transactional);
		if (!Asset)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("NewObject<%s> returned null"), *Class->GetName()));
			return nullptr;
		}
		FAssetRegistryModule::AssetCreated(Asset);
		Asset->MarkPackageDirty();
		return Asset;
	}

	bool FinishWrite(const FDirtyGuard& Guard, const TArray<UObject*>& Assets, bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError, bool& bOutSaved)
	{
		bOutSaved = false;
		if (!Guard.Check(OutError))
		{
			return false;
		}
		if (!bSave)
		{
			return true;
		}
		for (UObject* Asset : Assets)
		{
			if (Asset && !EnsureOutputPathAllowed(Asset->GetPathName(), TEXT("save"), OutError))
			{
				return false;
			}
		}
		TArray<FString> Failed;
		for (UObject* Asset : Assets)
		{
			if (Asset && !AnimMcpMontage::SaveAsset(Asset, Context))
			{
				Failed.Add(Asset->GetPathName());
			}
		}
		if (Failed.Num() > 0)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetArrayField(TEXT("failed"), ToJsonArray(Failed));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::SaveFailed, FString::Printf(TEXT("%d of %d asset(s) failed to save"), Failed.Num(), Assets.Num()), Details);
			return false;
		}
		bOutSaved = true;
		return true;
	}
}
