#include "Core/EditorMcpGuard.h"

#include "Core/AnimMcpAssetResolver.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "UObject/Package.h"
#include "UObject/UObjectIterator.h"

namespace EditorMcpGuard
{
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

	bool IsValidPrefix(const FString& NormalizedPrefix)
	{
		// FPackageName::IsValidLongPackageName("/Game") 는 true 다(5.7.4 실측 — EditorMcpCore.Settings 가 잡음). 그 판정만으로는
		// 마운트 루트 자체가 통과해 '전부 허용' 이 되므로, 마운트 루트 아래 폴더가 하나 이상 있어야 한다("/Game/X/" 는 되고 "/Game/" 는 안 된다)
		if (NormalizedPrefix.IsEmpty() || !NormalizedPrefix.EndsWith(TEXT("/")))
		{
			return false;
		}
		const FString Folder = NormalizedPrefix.LeftChop(1);
		int32 LastSlash = INDEX_NONE;
		return Folder.FindLastChar(TEXT('/'), LastSlash) && LastSlash > 0 && FPackageName::IsValidLongPackageName(Folder);
	}

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

	FString NormalizeFolderPath(const FString& Path)
	{
		FString Folder = Path.TrimStartAndEnd();
		while (Folder.Len() > 1 && Folder.EndsWith(TEXT("/")))
		{
			Folder.LeftChopInline(1);
		}
		return Folder;
	}

	bool IsUnderAnyPrefix(const FString& Path, const TArray<FString>& Prefixes)
	{
		// 애셋 경로("/Game/A/B.B")는 패키지로, 폴더는 끝에 '/' 를 붙여 접두 비교 — "/Game/Animation/TestX" 가 "/Game/Animation/Test/" 에 걸리지 않게
		const FString AsDir = NormalizeFolderPath(AnimMcpAssetResolver::ToPackagePath(Path)) + TEXT("/");
		return Prefixes.ContainsByPredicate([&AsDir](const FString& Prefix) { return AsDir.StartsWith(Prefix, ESearchCase::IgnoreCase); });
	}

	bool IsTrackedPackage(const UPackage* Package)
	{
		// FEditorFileUtils::GetDirtyContentPackages 와 같은 제외 규칙 — 단 맵도 포함하고, 그 함수처럼 패키지를 건드리는 부작용이 없다
		if (!Package || Package->GetOuter() != nullptr || Package == GetTransientPackage() || Package->HasAnyFlags(RF_Transient))
		{
			return false;
		}
		if (Package->HasAnyPackageFlags(PKG_CompiledIn | PKG_PlayInEditor))
		{
			return false;
		}
		return FPackageName::IsValidLongPackageName(Package->GetName(), /*bIncludeReadOnlyRoots*/ false);
	}

	void CollectDirtyPackages(TSet<FName>& Out)
	{
		for (TObjectIterator<UPackage> It; It; ++It)
		{
			if (It->IsDirty() && IsTrackedPackage(*It))
			{
				Out.Add(It->GetFName());
			}
		}
	}

	FDirtySnapshot::FDirtySnapshot()
	{
		CollectDirtyPackages(DirtyBefore);
	}

	void FDirtySnapshot::GetNewlyDirty(const TArray<FString>& AllowedPrefixes, TArray<FString>& OutAllowed, TArray<FString>& OutUnexpected, const TSet<FName>* ExtraAllowed) const
	{
		TSet<FName> DirtyNow;
		CollectDirtyPackages(DirtyNow);
		for (const FName& Name : DirtyNow)
		{
			if (DirtyBefore.Contains(Name))
			{
				continue;
			}
			const FString PackageName = Name.ToString();
			const bool bAllowed = IsUnderAnyPrefix(PackageName, AllowedPrefixes) || (ExtraAllowed && ExtraAllowed->Contains(Name));
			(bAllowed ? OutAllowed : OutUnexpected).Add(PackageName);
		}
		OutAllowed.Sort();
		OutUnexpected.Sort();
	}

	TArray<TSharedPtr<FJsonValue>> ToJsonArray(const TArray<FString>& Values)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FString& V : Values) { Out.Add(MakeShared<FJsonValueString>(V)); }
		return Out;
	}
}
