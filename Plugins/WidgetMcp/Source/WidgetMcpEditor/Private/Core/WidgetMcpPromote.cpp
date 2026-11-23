#include "Core/WidgetMcpPromote.h"

#include "AnimMcpLog.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "AssetToolsModule.h"
#include "Engine/Blueprint.h"
#include "HAL/FileManager.h"
#include "IAssetTools.h"
#include "CoreGlobals.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "UObject/Package.h"
#include "UObject/UObjectHash.h"
#include "UObject/UObjectIterator.h"
#include "WidgetBlueprint.h"

namespace WidgetMcpPromote
{
	namespace PromotePrivate
	{
		TSharedRef<FJsonObject> PathDetail(const TCHAR* Field, const FString& Path, const TArray<FString>& Allowed)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetStringField(TEXT("field"), Field);
			D->SetStringField(TEXT("path"), Path);
			D->SetArrayField(TEXT("allowed"), WidgetMcp::StringArray(Allowed));
			return D;
		}

		/** 폴더(끝 '/' 없음)가 접두(끝 '/') 중 하나 안이거나 그 자체인가 */
		bool IsInsideAny(const FString& Folder, const TArray<FString>& Prefixes)
		{
			const FString AsDir = Folder + TEXT("/");
			return Prefixes.ContainsByPredicate([&AsDir](const FString& P) { return AsDir.StartsWith(P, ESearchCase::IgnoreCase); });
		}

		/** 폴더가 접두 중 하나의 '아래' 하위 폴더인가 — 접두 자체는 아니다 */
		bool IsBelowAny(const FString& Folder, const TArray<FString>& Prefixes)
		{
			const FString AsDir = Folder + TEXT("/");
			return Prefixes.ContainsByPredicate([&AsDir](const FString& P) { return AsDir.StartsWith(P, ESearchCase::IgnoreCase) && AsDir.Len() > P.Len(); });
		}

		/** 메모리에 있는 그 폴더 아래 루트 패키지 (WidgetMcpRunPackages 와 같은 기준) */
		TArray<UPackage*> LoadedPackagesUnder(const FString& Folder)
		{
			TArray<UPackage*> Out;
			const FString Prefix = Folder + TEXT("/");
			for (TObjectIterator<UPackage> It; It; ++It)
			{
				if (It->GetOuter() == nullptr && !It->HasAnyFlags(RF_Transient) && It->GetName().StartsWith(Prefix, ESearchCase::IgnoreCase))
				{
					Out.Add(*It);
				}
			}
			return Out;
		}

		FString DiskDirOf(const FString& Folder)
		{
			return FPaths::ConvertRelativePathToFull(FPackageName::LongPackageNameToFilename(Folder + TEXT("/")));
		}

		FString PackageFileOf(const FString& Package)
		{
			return FPaths::ConvertRelativePathToFull(FPackageName::LongPackageNameToFilename(Package, FPackageName::GetAssetPackageExtension()));
		}

		struct FPlanned
		{
			FString SourcePackage;
			FString DestPackage;
			FString AssetName;
			FString ClassPath;
		};

		TArray<TSharedPtr<FJsonValue>> PlannedJson(const TArray<FPlanned>& Planned)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FPlanned& P : Planned)
			{
				TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
				O->SetStringField(TEXT("source"), P.SourcePackage + TEXT(".") + P.AssetName);
				O->SetStringField(TEXT("dest"), P.DestPackage + TEXT(".") + P.AssetName);
				O->SetStringField(TEXT("class"), P.ClassPath);
				Out.Add(MakeShared<FJsonValueObject>(O));
			}
			return Out;
		}
	}

	using namespace PromotePrivate;

	TSharedPtr<FJsonObject> Run(const WidgetMcp::FSettings& Settings, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		check(IsInGameThread());

		if (!Request.bDryRun && !Request.bConfirm)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest,
				TEXT("promote_widget copies and saves new packages — pass confirm=true after a person asked for this promotion (dry_run=true shows the plan)"), TEXT("MISSING_CONFIRM"));
			return nullptr;
		}

		// ---- 1) 경로 — run 은 WidgetOutputPaths 아래, dest 는 WidgetPromotionPaths 아래의 새 하위 폴더 ----
		if (!WidgetMcp::CheckRunFolder(Settings, Request.RunFolder, TEXT("run_path"), OutError))
		{
			return nullptr;
		}
		const FString Run = EditorMcpGuard::NormalizeFolderPath(Request.RunFolder);
		const FString Dest = EditorMcpGuard::NormalizeFolderPath(Request.DestFolder);
		if (!FPackageName::IsValidLongPackageName(Dest, /*bIncludeReadOnlyRoots*/ false) || Dest.Contains(TEXT(".")))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a valid folder path"), *Dest), TEXT("BAD_PATH"),
				PathDetail(TEXT("dest_path"), Dest, Settings.PromotionPaths));
			return nullptr;
		}
		if (IsInsideAny(Dest, Settings.OutputPaths))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::OutputPathNotAllowed,
				FString::Printf(TEXT("dest '%s' is inside [WidgetMcp] WidgetOutputPaths — promotion copies run output out of the run paths"), *Dest), TEXT("DEST_IS_RUN_PATH"),
				PathDetail(TEXT("dest_path"), Dest, Settings.PromotionPaths));
			return nullptr;
		}
		if (!IsBelowAny(Dest, Settings.PromotionPaths))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::OutputPathNotAllowed,
				Settings.PromotionPaths.Num() == 0
					? FString(TEXT("No [WidgetMcp] WidgetPromotionPaths configured — promote_widget copies nothing"))
					: FString::Printf(TEXT("dest '%s' must be a folder below [WidgetMcp] WidgetPromotionPaths (%s) — one folder per screen, never the prefix itself"), *Dest, *FString::Join(Settings.PromotionPaths, TEXT(", "))),
				TEXT("OUTSIDE_PROMOTION_PATHS"), PathDetail(TEXT("dest_path"), Dest, Settings.PromotionPaths));
			return nullptr;
		}

		// ---- 2) dest 는 비어 있어야 한다 — 애셋(레지스트리) · 메모리 패키지 · 디스크 파일 무엇이든 있으면 거절 ----
		IAssetRegistry& Registry = FAssetRegistryModule::GetRegistry();
		{
			TArray<FString> Existing;
			TArray<FAssetData> DestAssets;
			Registry.GetAssetsByPath(FName(*Dest), DestAssets, /*bRecursive*/ true, /*bIncludeOnlyOnDiskAssets*/ false);
			for (const FAssetData& A : DestAssets) { Existing.AddUnique(A.PackageName.ToString()); }
			for (const UPackage* P : LoadedPackagesUnder(Dest)) { Existing.AddUnique(P->GetName()); }
			TArray<FString> Files;
			IFileManager::Get().FindFilesRecursive(Files, *DiskDirOf(Dest), TEXT("*.*"), /*Files*/ true, /*Directories*/ false);
			for (const FString& F : Files) { Existing.AddUnique(F); }
			if (Existing.Num() > 0)
			{
				Existing.Sort();
				TSharedRef<FJsonObject> D = PathDetail(TEXT("dest_path"), Dest, Settings.PromotionPaths);
				D->SetArrayField(TEXT("existing"), WidgetMcp::StringArray(Existing));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetExists,
					FString::Printf(TEXT("dest '%s' is not empty (%d item(s), first: %s) — promotion never overwrites"), *Dest, Existing.Num(), *Existing[0]), TEXT("DEST_EXISTS"), D);
				return nullptr;
			}
		}

		// ---- 3) run — 디스크에 저장돼 있고 더티가 없어야 한다(엔진 복사는 디스크의 패키지를 읽는다) ----
		if (Registry.IsLoadingAssets())
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::PromoteFailed, TEXT("The asset registry is still discovering assets — dependencies cannot be checked yet; retry shortly"), TEXT("REGISTRY_LOADING"));
			return nullptr;
		}
		{
			TArray<FString> Unsaved, Dirty;
			for (const UPackage* P : LoadedPackagesUnder(Run))
			{
				if (!FPackageName::DoesPackageExist(P->GetName()))
				{
					Unsaved.Add(P->GetName());
				}
				else if (P->IsDirty())
				{
					Dirty.Add(P->GetName());
				}
			}
			if (Unsaved.Num() > 0 || Dirty.Num() > 0)
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetStringField(TEXT("run_path"), Run);
				D->SetArrayField(TEXT("unsaved"), WidgetMcp::StringArray(Unsaved));
				D->SetArrayField(TEXT("dirty"), WidgetMcp::StringArray(Dirty));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetDirty,
					Unsaved.Num() > 0
						? FString::Printf(TEXT("%d package(s) under '%s' were never saved — only a finalized run (save_widget_run) is promoted"), Unsaved.Num(), *Run)
						: FString::Printf(TEXT("%d package(s) under '%s' have unsaved changes — save or discard them first"), Dirty.Num(), *Run),
					Unsaved.Num() > 0 ? TEXT("RUN_NOT_SAVED") : TEXT("RUN_DIRTY"), D);
				return nullptr;
			}
		}
		TArray<FAssetData> RunAssets;
		Registry.GetAssetsByPath(FName(*Run), RunAssets, /*bRecursive*/ true, /*bIncludeOnlyOnDiskAssets*/ true);
		RunAssets.Sort([](const FAssetData& A, const FAssetData& B) { return A.PackageName.LexicalLess(B.PackageName); });
		TArray<FPlanned> Planned;
		TSet<FName> SourceSet;
		for (const FAssetData& A : RunAssets)
		{
			if (SourceSet.Contains(A.PackageName))
			{
				continue;
			}
			SourceSet.Add(A.PackageName);
			FPlanned P;
			P.SourcePackage = A.PackageName.ToString();
			P.DestPackage = Dest + P.SourcePackage.Mid(Run.Len());
			P.AssetName = A.AssetName.ToString();
			P.ClassPath = A.AssetClassPath.ToString();
			Planned.Add(MoveTemp(P));
		}
		if (Planned.Num() == 0)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("no saved assets under '%s'"), *Run), TEXT("RUN_EMPTY"));
			return nullptr;
		}

		// ---- 4) 의존성 — run 밖이면서 /Game/_AutoGen/ 안(다른 run)이면 거절, 나머지(폰트 · 엔진)는 그대로 가리킨다 ----
		TArray<FString> External, OtherRuns;
		for (const FPlanned& P : Planned)
		{
			TArray<FName> Deps;
			Registry.GetDependencies(FName(*P.SourcePackage), Deps);
			for (const FName& Dep : Deps)
			{
				const FString Name = Dep.ToString();
				if (SourceSet.Contains(Dep) || Name.StartsWith(TEXT("/Script/")))
				{
					continue;
				}
				if (IsInsideAny(FPackageName::GetLongPackagePath(Name), Settings.OutputPaths))
				{
					OtherRuns.AddUnique(P.SourcePackage + TEXT(" -> ") + Name);
				}
				else
				{
					External.AddUnique(Name);
				}
			}
		}
		External.Sort();
		if (OtherRuns.Num() > 0)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("references"), WidgetMcp::StringArray(OtherRuns));
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetReferenced,
				FString::Printf(TEXT("the run references packages in another run folder (%s) — the copy would still point into /Game/_AutoGen/"), *OtherRuns[0]), TEXT("DEPENDS_ON_OTHER_RUN"), D);
			return nullptr;
		}

		TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
		Result->SetBoolField(TEXT("dry_run"), Request.bDryRun);
		Result->SetStringField(TEXT("run_path"), Run);
		Result->SetStringField(TEXT("dest_path"), Dest);
		Result->SetArrayField(TEXT("planned"), PlannedJson(Planned));
		Result->SetArrayField(TEXT("external_dependencies"), WidgetMcp::StringArray(External));
		if (Request.bDryRun)
		{
			return Result;
		}

		// ---- 5) 복사 — 엔진 Advanced Copy 의 대화상자 없는 경로. 대상 충돌은 위에서 막았고, 그래도 생기면 덮어쓰지 않게 '묻기'(무인 = 기본값 거절)로 둔다 ----
		const EditorMcpGuard::FDirtySnapshot Snapshot;
		TMap<FString, FString> SourceAndDest;
		for (const FPlanned& P : Planned) { SourceAndDest.Add(P.SourcePackage, P.DestPackage); }
		bool bCopied = false;
		{
			TGuardValue<bool> Unattended(GIsRunningUnattendedScript, true);
			bCopied = FAssetToolsModule::GetModule().Get().AdvancedCopyPackages(SourceAndDest, /*bForceAutosave*/ true, /*bCopyOverAllDestinationOverlaps*/ false,
				/*OutDuplicatedObjects*/ nullptr, EMessageSeverity::Error);
		}

		// ---- 6) 사후 검증 — 되돌리지 않는다(엔진이 저장까지 끝냈다). 실패는 오류로 알리고 details 에 무엇이 있는지 남긴다 ----
		TArray<FString> Copied, Missing;
		for (const FPlanned& P : Planned)
		{
			(FPackageName::DoesPackageExist(P.DestPackage) ? Copied : Missing).Add(P.DestPackage);
		}
		auto Fail = [&](const TCHAR* Code, const TCHAR* Reason, const FString& Message, TSharedPtr<FJsonObject> Extra = nullptr)
		{
			TSharedRef<FJsonObject> D = Extra.IsValid() ? Extra.ToSharedRef() : MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("copied"), WidgetMcp::StringArray(Copied));
			D->SetArrayField(TEXT("missing"), WidgetMcp::StringArray(Missing));
			OutError = WidgetMcp::MakeMcpError(Code, Message + TEXT(" — the copy was not reverted"), Reason, D);
		};
		if (!bCopied || Missing.Num() > 0)
		{
			Fail(EditorMcpErrorCodes::PromoteFailed, TEXT("COPY_FAILED"),
				FString::Printf(TEXT("the engine copied %d of %d package(s) (AdvancedCopyPackages returned %s; see LogAssetTools)"), Copied.Num(), Planned.Num(), bCopied ? TEXT("true") : TEXT("false")));
			return nullptr;
		}

		// 저장된 새 파일을 레지스트리에 다시 읽혀 디스크 기준 의존성으로 본다 — 복사본이 run 을 가리키면 참조가 다시 이어지지 않은 것
		{
			TArray<FString> Files;
			for (const FPlanned& P : Planned) { Files.Add(PackageFileOf(P.DestPackage)); }
			Registry.ScanFilesSynchronous(Files, /*bForceRescan*/ true);
		}
		TArray<FString> StillPointing;
		for (const FPlanned& P : Planned)
		{
			TArray<FName> Deps;
			Registry.GetDependencies(FName(*P.DestPackage), Deps);
			for (const FName& Dep : Deps)
			{
				const FString Name = Dep.ToString();
				if (!Name.StartsWith(TEXT("/Script/")) && IsInsideAny(FPackageName::GetLongPackagePath(Name), Settings.OutputPaths))
				{
					StillPointing.AddUnique(P.DestPackage + TEXT(" -> ") + Name);
				}
			}
		}
		if (StillPointing.Num() > 0)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("references"), WidgetMcp::StringArray(StillPointing));
			Fail(EditorMcpErrorCodes::PromoteFailed, TEXT("REFERENCES_NOT_REMAPPED"),
				FString::Printf(TEXT("%d copied package reference(s) still point into the run paths (first: %s)"), StillPointing.Num(), *StillPointing[0]), D);
			return nullptr;
		}

		// 클래스 · 블루프린트 상태 — 복사본이 같은 클래스이고, 블루프린트는 컴파일 오류가 없고 부모가 같다
		TArray<FString> Mismatch;
		TArray<TSharedPtr<FJsonValue>> Blueprints;
		for (const FPlanned& P : Planned)
		{
			const UObject* Source = LoadObject<UObject>(nullptr, *(P.SourcePackage + TEXT(".") + P.AssetName));
			const UObject* Copy = LoadObject<UObject>(nullptr, *(P.DestPackage + TEXT(".") + P.AssetName));
			if (!Source || !Copy || Source->GetClass() != Copy->GetClass())
			{
				Mismatch.Add(FString::Printf(TEXT("%s (%s → %s)"), *P.DestPackage, *GetNameSafe(Source ? Source->GetClass() : nullptr), *GetNameSafe(Copy ? Copy->GetClass() : nullptr)));
				continue;
			}
			if (const UBlueprint* CopyBP = Cast<UBlueprint>(Copy))
			{
				const UBlueprint* SourceBP = CastChecked<UBlueprint>(Source);
				const bool bOk = CopyBP->Status != BS_Error && CopyBP->ParentClass == SourceBP->ParentClass && CopyBP->GeneratedClass != nullptr;
				if (!bOk)
				{
					Mismatch.Add(FString::Printf(TEXT("%s (status %d, parent %s → %s)"), *P.DestPackage, static_cast<int32>(CopyBP->Status), *GetNameSafe(SourceBP->ParentClass), *GetNameSafe(CopyBP->ParentClass)));
				}
				TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
				O->SetStringField(TEXT("asset"), Copy->GetPathName());
				O->SetStringField(TEXT("parent_class"), GetPathNameSafe(CopyBP->ParentClass));
				O->SetStringField(TEXT("generated_class"), GetPathNameSafe(CopyBP->GeneratedClass));
				O->SetNumberField(TEXT("status"), static_cast<int32>(CopyBP->Status));
				Blueprints.Add(MakeShared<FJsonValueObject>(O));
			}
		}
		if (Mismatch.Num() > 0)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("mismatch"), WidgetMcp::StringArray(Mismatch));
			Fail(EditorMcpErrorCodes::PromoteFailed, TEXT("COPY_MISMATCH"), FString::Printf(TEXT("%d copied asset(s) differ from the source (first: %s)"), Mismatch.Num(), *Mismatch[0]), D);
			return nullptr;
		}

		// 전역 더티 — dest 밖(원본 run 포함)이 새로 더티가 됐거나, dest 가 저장 안 된 채 남았으면 알린다
		TArray<FString> NewlyDirty, Unexpected;
		Snapshot.GetNewlyDirty({ Dest + TEXT("/") }, NewlyDirty, Unexpected);
		TArray<FString> UnsavedDest;
		for (const UPackage* P : LoadedPackagesUnder(Dest))
		{
			if (P->IsDirty()) { UnsavedDest.Add(P->GetName()); }
		}
		if (Unexpected.Num() > 0 || UnsavedDest.Num() > 0)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("unexpected_dirty"), WidgetMcp::StringArray(Unexpected));
			D->SetArrayField(TEXT("unsaved_dest"), WidgetMcp::StringArray(UnsavedDest));
			Fail(EditorMcpErrorCodes::UnexpectedDirty, TEXT("DIRTY_AFTER_COPY"),
				Unexpected.Num() > 0
					? FString::Printf(TEXT("%d package(s) outside dest became dirty (first: %s)"), Unexpected.Num(), *Unexpected[0])
					: FString::Printf(TEXT("%d copied package(s) are still unsaved (first: %s)"), UnsavedDest.Num(), *UnsavedDest[0]), D);
			return nullptr;
		}

		Result->SetArrayField(TEXT("copied"), PlannedJson(Planned));
		Result->SetArrayField(TEXT("blueprints"), Blueprints);
		UE_LOG(LogAnimGraphMcp, Log, TEXT("promote_widget: %s -> %s — %d package(s) copied and saved"), *Run, *Dest, Planned.Num());
		return Result;
	}
}
