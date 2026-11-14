#include "Core/AnimMcpAssetProtection.h"

#include "AnimMcpLog.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/EditorMcpSettings.h"

namespace AnimMcpAssetProtection
{
	namespace
	{

		FString NormalizeAssetEntry(const FString& Raw)
		{
			// "/Game/A/B.B" → "/Game/A/B". 끝의 '/' 도 떼어 낸다
			FString Package = AnimMcpAssetResolver::ToPackagePath(Raw.TrimStartAndEnd());
			Package.RemoveFromEnd(TEXT("/"));
			return Package;
		}

		FString NormalizePathEntry(const FString& Raw)
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

		FRules LoadRules()
		{
			// [EditorMcp] 와 옛 [AnimGraphMcp] 를 합친다 (2026-11-14 플러그인 분리 — 기존 ini 그대로 동작)
			FRules Rules;
			for (const FString& Entry : EditorMcpSettings::GetArray(TEXT("ProtectedAssets")))
			{
				const FString Normalized = NormalizeAssetEntry(Entry);
				if (!Normalized.IsEmpty())
				{
					Rules.Assets.AddUnique(Normalized);
				}
			}
			for (const FString& Entry : EditorMcpSettings::GetArray(TEXT("ProtectedPaths")))
			{
				const FString Normalized = NormalizePathEntry(Entry);
				if (!Normalized.IsEmpty() && Normalized != TEXT("/"))
				{
					Rules.Paths.AddUnique(Normalized);
				}
			}
			UE_LOG(LogAnimGraphMcp, Log, TEXT("Asset protection: %d assets, %d path prefixes ([%s] + [%s] in %s)"), Rules.Assets.Num(), Rules.Paths.Num(),
				EditorMcpSettings::Section, EditorMcpSettings::LegacySection, *GEngineIni);
			return Rules;
		}
	}

	const FRules& GetRules()
	{
		static const FRules Rules = LoadRules();
		return Rules;
	}

	bool IsProtected(const FString& AssetPath, FString* OutMatchedRule)
	{
		const FString Package = NormalizeAssetEntry(AssetPath);
		if (Package.IsEmpty())
		{
			return false;
		}
		const FRules& Rules = GetRules();
		for (const FString& Asset : Rules.Assets)
		{
			if (Package.Equals(Asset, ESearchCase::IgnoreCase))
			{
				if (OutMatchedRule) { *OutMatchedRule = TEXT("ProtectedAssets=") + Asset; }
				return true;
			}
		}
		const FString PackageAsDir = Package + TEXT("/");
		for (const FString& Prefix : Rules.Paths)
		{
			// 접두 아래의 애셋, 또는 접두 디렉터리 그 자체
			if (Package.StartsWith(Prefix, ESearchCase::IgnoreCase) || PackageAsDir.Equals(Prefix, ESearchCase::IgnoreCase))
			{
				if (OutMatchedRule) { *OutMatchedRule = TEXT("ProtectedPaths=") + Prefix; }
				return true;
			}
		}
		return false;
	}

	bool EnsureNotProtected(const FString& AssetPath, const TCHAR* Operation, FAnimMcpError& OutError)
	{
		FString Rule;
		if (!IsProtected(AssetPath, &Rule))
		{
			return true;
		}
		TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
		Details->SetStringField(TEXT("asset_path"), AnimMcpAssetResolver::NormalizeObjectPath(AssetPath));
		Details->SetStringField(TEXT("rule"), Rule);
		Details->SetStringField(TEXT("config"), EditorMcpSettings::Describe(Rule.StartsWith(TEXT("ProtectedPaths")) ? TEXT("ProtectedPaths") : TEXT("ProtectedAssets")));
		OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetProtected,
			FString::Printf(TEXT("Refusing to %s '%s': protected by %s"), Operation, *AnimMcpAssetResolver::ToPackagePath(AssetPath), *Rule), Details);
		return false;
	}

	TSharedRef<FJsonObject> DescribeRules()
	{
		const FRules& Rules = GetRules();
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		TArray<TSharedPtr<FJsonValue>> Assets;
		for (const FString& A : Rules.Assets) { Assets.Add(MakeShared<FJsonValueString>(A)); }
		TArray<TSharedPtr<FJsonValue>> Paths;
		for (const FString& P : Rules.Paths) { Paths.Add(MakeShared<FJsonValueString>(P)); }
		Obj->SetArrayField(TEXT("assets"), Assets);
		Obj->SetArrayField(TEXT("paths"), Paths);
		return Obj;
	}
}
