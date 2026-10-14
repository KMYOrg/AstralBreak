#include "AnimMcpAssetResolver.h"

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimationAsset.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpTypes.h"
#include "UObject/SoftObjectPath.h"

namespace AnimMcpAssetResolver
{
	FString NormalizeObjectPath(const FString& InPath)
	{
		FString Path = InPath.TrimStartAndEnd();
		if (Path.Contains(TEXT(".")))
		{
			return Path;
		}
		FString AssetName;
		int32 SlashIndex = INDEX_NONE;
		if (Path.FindLastChar(TEXT('/'), SlashIndex))
		{
			AssetName = Path.Mid(SlashIndex + 1);
		}
		else
		{
			AssetName = Path;
		}
		return Path + TEXT(".") + AssetName;
	}

	FString ToPackagePath(const FString& InPath)
	{
		FString Path = InPath.TrimStartAndEnd();
		int32 DotIndex = INDEX_NONE;
		if (Path.FindLastChar(TEXT('.'), DotIndex))
		{
			Path.LeftInline(DotIndex);
		}
		return Path;
	}

	bool AssetExists(const FString& ObjectPath)
	{
		IAssetRegistry& Registry = FAssetRegistryModule::GetRegistry();
		const FAssetData Data = Registry.GetAssetByObjectPath(FSoftObjectPath(ObjectPath), /*bIncludeOnlyOnDiskAssets*/ false);
		return Data.IsValid();
	}

	UObject* LoadAssetOfClass(const FString& AssetPath, UClass* ExpectedClass, FAnimMcpError& OutError)
	{
		if (AssetPath.IsEmpty())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("asset_path is empty"));
			return nullptr;
		}

		const FString ObjectPath = NormalizeObjectPath(AssetPath);
		if (!AssetExists(ObjectPath))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("No asset at '%s'"), *ObjectPath));
			return nullptr;
		}

		UObject* Loaded = LoadObject<UObject>(nullptr, *ObjectPath);
		if (!Loaded)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Asset registry lists '%s' but it failed to load"), *ObjectPath));
			return nullptr;
		}

		if (ExpectedClass && !Loaded->IsA(ExpectedClass))
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("actual_class"), Loaded->GetClass()->GetPathName());
			Details->SetStringField(TEXT("expected_class"), ExpectedClass->GetPathName());
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is a %s, expected %s"), *ObjectPath, *Loaded->GetClass()->GetName(), *ExpectedClass->GetName()), Details);
			return nullptr;
		}

		return Loaded;
	}

	UAnimBlueprint* LoadAnimBlueprint(const FString& AssetPath, FAnimMcpError& OutError)
	{
		return Cast<UAnimBlueprint>(LoadAssetOfClass(AssetPath, UAnimBlueprint::StaticClass(), OutError));
	}

	USkeleton* LoadSkeleton(const FString& AssetPath, FAnimMcpError& OutError)
	{
		return Cast<USkeleton>(LoadAssetOfClass(AssetPath, USkeleton::StaticClass(), OutError));
	}

	UAnimationAsset* LoadAnimationAsset(const FString& AssetPath, FAnimMcpError& OutError)
	{
		return Cast<UAnimationAsset>(LoadAssetOfClass(AssetPath, UAnimationAsset::StaticClass(), OutError));
	}
}
