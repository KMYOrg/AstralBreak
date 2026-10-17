#include "AnimMcpAssetOps.h"

#include "AnimMcpAssetResolver.h"
#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpTypes.h"
#include "Editor.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Misc/PackageName.h"
#include "PackageTools.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Subsystems/EditorAssetSubsystem.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "UObject/UObjectHash.h"

namespace AnimMcpAssetOps
{
	bool DeleteAssetAtPath(const FString& ObjectPath, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());

		if (UObject* Existing = LoadObject<UObject>(nullptr, *ObjectPath))
		{
			if (UAssetEditorSubsystem* AssetEditors = GEditor ? GEditor->GetEditorSubsystem<UAssetEditorSubsystem>() : nullptr)
			{
				AssetEditors->CloseAllEditorsForAsset(Existing);
			}
		}

		UEditorAssetSubsystem* AssetSubsystem = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
		if (!AssetSubsystem)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("EditorAssetSubsystem unavailable"));
			return false;
		}
		if (!AssetSubsystem->DeleteAsset(ObjectPath))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("DeleteAsset failed for '%s' (see LogEditorAssetSubsystem)"), *ObjectPath));
			return false;
		}

		// ForceDeleteObjects 는 객체 참조를 끊고 지우지만, 패키지가 아직 참조되면(컴파일된 클래스·CDO·에디터 등)
		// CleanupAfterSuccessfulDelete 가 그 패키지를 삭제 목록에서 빼 **파일도 남기고 언로드도 안 한다** (ObjectTools.cpp:2535-2550).
		// 실측(phase4·5 회귀): 다음 create 의 FullyLoad 가 남은 파일에서 애셋을 되살려 "still exists" 로 실패했다.
		// → 패키지를 명시적으로 언로드하고, 남은 객체는 임시 패키지로 옮기고, 파일은 직접 지우고, 레지스트리에 알린다
		const FString PackagePath = AnimMcpAssetResolver::ToPackagePath(ObjectPath);
		if (UPackage* Package = FindPackage(nullptr, *PackagePath))
		{
			// 링커가 파일 핸들을 쥐고 있으면 Windows 에서 파일 삭제가 실패한다 (phase4 회귀 실측 "could not be removed") — 먼저 끊는다
			ResetLoaders(Package);
			FText UnloadError;
			UPackageTools::UnloadPackages({ Package }, UnloadError, /*bUnloadDirtyPackages*/ true);
		}
		if (UPackage* Package = FindPackage(nullptr, *PackagePath))
		{
			TArray<UObject*> Survivors;
			ForEachObjectWithPackage(Package, [&Survivors](UObject* Obj) { Survivors.Add(Obj); return true; }, /*bIncludeNestedObjects*/ false);
			for (UObject* Stale : Survivors)
			{
				const FString StaleOriginalName = Stale->GetName();
				const FName StaleName = MakeUniqueObjectName(GetTransientPackage(), Stale->GetClass(), FName(*(StaleOriginalName + TEXT("_MCP_STALE"))));
				Stale->ClearFlags(RF_Public | RF_Standalone);
				if (!Stale->Rename(*StaleName.ToString(), GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("'%s' was deleted but in-memory object '%s' could not be moved aside"), *ObjectPath, *StaleOriginalName));
					return false;
				}
				Stale->MarkAsGarbage();
			}
			Package->SetDirtyFlag(false);
			FAssetRegistryModule::PackageDeleted(Package);
			Context.AddDiagnostic(TEXT("info"), TEXT("STALE_OBJECT_MOVED"), FString::Printf(TEXT("Package '%s' survived DeleteAsset (still referenced); %d object(s) moved to the transient package"), *PackagePath, Survivors.Num()));
		}

		FString Filename;
		if (FPackageName::DoesPackageExist(PackagePath, &Filename) && IFileManager::Get().FileExists(*Filename))
		{
			if (UPackage* Package = FindPackage(nullptr, *PackagePath))
			{
				ResetLoaders(Package);
			}
			// 방금 저장한 파일은 잠깐 잠겨 있을 수 있다 (실측: 회귀에서 간헐적으로 "could not be removed" — 바이러스 검사·레지스트리 스캔 등
			// 외부 핸들). 짧게 재시도한다 — 최대 ~3초, 게임 스레드 블로킹은 이 도구에서 허용
			int32 Attempts = 0;
			for (; Attempts < 10; ++Attempts)
			{
				IFileManager::Get().Delete(*Filename, /*RequireExists*/ false, /*EvenReadOnly*/ true, /*Quiet*/ true);
				if (!IFileManager::Get().FileExists(*Filename))
				{
					break;
				}
				FPlatformProcess::Sleep(0.3f);
			}
			if (IFileManager::Get().FileExists(*Filename))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("DeleteAsset left '%s' on disk and it could not be removed after %d attempts (locked by another process?)"), *Filename, Attempts));
				return false;
			}
			FAssetRegistryModule::GetRegistry().ScanModifiedAssetFiles({ Filename });
			Context.AddDiagnostic(TEXT("info"), TEXT("PACKAGE_FILE_REMOVED"), FString::Printf(TEXT("Removed leftover file %s (%d attempt%s)"), *Filename, Attempts + 1, Attempts == 0 ? TEXT("") : TEXT("s")));
		}

		UE_LOG(LogAnimGraphMcp, Log, TEXT("Deleted asset %s"), *ObjectPath);
		return true;
	}

	TArray<FString> FindReferencers(const FString& ObjectPath)
	{
		const FName PackageName(*AnimMcpAssetResolver::ToPackagePath(ObjectPath));
		TArray<FName> Raw;
		FAssetRegistryModule::GetRegistry().GetReferencers(PackageName, Raw, UE::AssetRegistry::EDependencyCategory::Package);

		TArray<FString> Out;
		for (const FName& Name : Raw)
		{
			const FString S = Name.ToString();
			if (Name == PackageName || S.StartsWith(TEXT("/Temp/")) || S.StartsWith(TEXT("/Engine/Transient")))
			{
				continue;
			}
			Out.AddUnique(S);
		}
		Out.Sort();
		return Out;
	}

	UAnimBlueprint* DuplicateAnimBlueprint(UAnimBlueprint* Source, const FString& DestObjectPath, bool bPreserveNodeGuids, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread() && Source);

		UEditorAssetSubsystem* AssetSubsystem = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
		if (!AssetSubsystem)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("EditorAssetSubsystem unavailable"));
			return nullptr;
		}

		UObject* Duplicated = nullptr;
		{
			// 스코프 플래그는 정적 — 복제 호출 동안만 켠다 (BlueprintEditorUtils.h:1996-2016)
			FBlueprintDuplicationScopeFlags Scope(bPreserveNodeGuids ? FBlueprintDuplicationScopeFlags::TheSameNodeGuid : FBlueprintDuplicationScopeFlags::NoFlags);
			Duplicated = AssetSubsystem->DuplicateLoadedAsset(Source, DestObjectPath);
		}
		if (!Duplicated)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("DuplicateLoadedAsset('%s' -> '%s') returned null (see LogEditorAssetSubsystem / LogAssetTools)"), *Source->GetPathName(), *DestObjectPath));
			return nullptr;
		}

		UAnimBlueprint* Result = Cast<UAnimBlueprint>(Duplicated);
		if (!Result)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Duplicate of '%s' is a %s, not an AnimBlueprint"), *Source->GetPathName(), *Duplicated->GetClass()->GetName()));
			return nullptr;
		}

		// PerformDuplicateAsset 은 RF 플래그가 바뀐 경우에만 AssetCreated 를 보낸다 (AssetTools.cpp:2169) — 레지스트리에 없으면 직접
		if (!AnimMcpAssetResolver::AssetExists(Result->GetPathName()))
		{
			FAssetRegistryModule::AssetCreated(Result);
			Context.AddDiagnostic(TEXT("info"), TEXT("ASSET_REGISTERED"), TEXT("Duplicate was not in the asset registry; registered it"));
		}
		Result->MarkPackageDirty();

		UE_LOG(LogAnimGraphMcp, Log, TEXT("Duplicated %s -> %s (node guids %s)"), *Source->GetPathName(), *Result->GetPathName(), bPreserveNodeGuids ? TEXT("preserved") : TEXT("regenerated"));
		return Result;
	}
}
