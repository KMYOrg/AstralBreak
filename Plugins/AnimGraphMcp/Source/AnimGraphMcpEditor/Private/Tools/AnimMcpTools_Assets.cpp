#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimComposite.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpBlueprintFactory.h"
#include "Core/AnimMcpCompiler.h"
#include "Core/AnimMcpGraphInspector.h"
#include "Misc/PackageName.h"

namespace AnimMcpTools
{
	namespace
	{
		/** AssetRegistry "Skeleton" 태그는 export text ("/Script/Engine.Skeleton'/Game/X.X'") — 오브젝트 경로로 정규화 */
		FString SkeletonTagToObjectPath(const FString& TagValue)
		{
			return FPackageName::ExportTextPathToObjectPath(TagValue);
		}

		bool AddClassFilter(FARFilter& Filter, const FString& ClassName, FAnimMcpError& OutError)
		{
			const FString Lower = ClassName.ToLower();
			if (Lower.IsEmpty() || Lower == TEXT("all") || Lower == TEXT("animationasset"))
			{
				Filter.ClassPaths.Add(UAnimSequence::StaticClass()->GetClassPathName());
				Filter.ClassPaths.Add(UBlendSpace::StaticClass()->GetClassPathName());
				Filter.ClassPaths.Add(UAnimMontage::StaticClass()->GetClassPathName());
				Filter.ClassPaths.Add(UAnimComposite::StaticClass()->GetClassPathName());
				return true;
			}
			if (Lower == TEXT("animsequence")) { Filter.ClassPaths.Add(UAnimSequence::StaticClass()->GetClassPathName()); return true; }
			if (Lower == TEXT("blendspace"))   { Filter.ClassPaths.Add(UBlendSpace::StaticClass()->GetClassPathName()); return true; }
			if (Lower == TEXT("animmontage"))  { Filter.ClassPaths.Add(UAnimMontage::StaticClass()->GetClassPathName()); return true; }
			if (Lower == TEXT("animcomposite")){ Filter.ClassPaths.Add(UAnimComposite::StaticClass()->GetClassPathName()); return true; }
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Unknown class filter '%s' (AnimSequence, BlendSpace, AnimMontage, AnimComposite, all)"), *ClassName));
			return false;
		}
	}

	void RegisterAssetTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("list_animation_assets"),
			TEXT("List animation assets from the asset registry. Params: skeleton? (path; only assets for this skeleton), class? (AnimSequence|BlendSpace|AnimMontage|AnimComposite|all), path_prefix? (default /Game), limit? (default 200)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const FString SkeletonPath = Context.Request.GetOptionalString(TEXT("skeleton"));
				const FString ClassName = Context.Request.GetOptionalString(TEXT("class"), TEXT("all"));
				const FString PathPrefix = Context.Request.GetOptionalString(TEXT("path_prefix"), TEXT("/Game"));
				const int32 Limit = FMath::Clamp(static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("limit"), 200.0)), 1, 5000);

				FString WantedSkeleton;
				if (!SkeletonPath.IsEmpty())
				{
					WantedSkeleton = AnimMcpAssetResolver::NormalizeObjectPath(SkeletonPath);
					if (!AnimMcpAssetResolver::AssetExists(WantedSkeleton))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("Skeleton '%s' not found"), *WantedSkeleton));
						return nullptr;
					}
				}

				FARFilter Filter;
				if (!AddClassFilter(Filter, ClassName, OutError))
				{
					return nullptr;
				}
				Filter.bRecursiveClasses = true;
				Filter.PackagePaths.Add(FName(*PathPrefix));
				Filter.bRecursivePaths = true;

				TArray<FAssetData> Assets;
				FAssetRegistryModule::GetRegistry().GetAssets(Filter, Assets);
				Assets.Sort([](const FAssetData& A, const FAssetData& B) { return A.GetObjectPathString() < B.GetObjectPathString(); });

				TArray<TSharedPtr<FJsonValue>> Items;
				int32 Total = 0;
				static const FName SkeletonTag(TEXT("Skeleton"));
				for (const FAssetData& Data : Assets)
				{
					FString SkeletonTagValue;
					Data.GetTagValue(SkeletonTag, SkeletonTagValue);
					const FString AssetSkeleton = SkeletonTagValue.IsEmpty() ? FString() : SkeletonTagToObjectPath(SkeletonTagValue);
					if (!WantedSkeleton.IsEmpty() && AssetSkeleton != WantedSkeleton)
					{
						continue;
					}
					++Total;
					if (Items.Num() >= Limit)
					{
						continue;
					}
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetStringField(TEXT("asset_path"), Data.GetObjectPathString());
					Item->SetStringField(TEXT("name"), Data.AssetName.ToString());
					Item->SetStringField(TEXT("class"), Data.AssetClassPath.GetAssetName().ToString());
					Item->SetField(TEXT("skeleton"), AnimMcpJson::StringOrNull(AssetSkeleton));
					Items.Add(MakeShared<FJsonValueObject>(Item));
				}

				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetNumberField(TEXT("total"), Total);
				Result->SetNumberField(TEXT("returned"), Items.Num());
				Result->SetBoolField(TEXT("truncated"), Total > Items.Num());
				Result->SetArrayField(TEXT("assets"), Items);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("create_animation_blueprint"),
			TEXT("Create a new Animation Blueprint with an empty AnimGraph (Output Pose only). Params: asset_path, skeleton, parent_class? (default /Script/Engine.AnimInstance), preview_mesh?, overwrite? (default false; true deletes an existing asset at that path)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpBlueprintFactory::FCreateParams Params;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), Params.AssetPath, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("skeleton"), Params.SkeletonPath, OutError)) { return nullptr; }
				Params.ParentClassPath = Context.Request.GetOptionalString(TEXT("parent_class"), TEXT("/Script/Engine.AnimInstance"));
				Params.PreviewMeshPath = Context.Request.GetOptionalString(TEXT("preview_mesh"));
				Params.bOverwrite = Context.Request.GetOptionalBool(TEXT("overwrite"), false);

				UAnimBlueprint* Blueprint = AnimMcpBlueprintFactory::CreateAnimBlueprint(Params, Context, OutError);
				if (!Blueprint)
				{
					return nullptr;
				}
				TSharedRef<FJsonObject> Result = AnimMcpGraphInspector::BuildBlueprintInfo(Blueprint, Context);
				Result->SetBoolField(TEXT("created"), true);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("save_animation_blueprint"),
			TEXT("Save an Animation Blueprint package to disk (forced, even if not dirty). Params: asset_path."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				if (!AnimMcpCompiler::Save(Blueprint, OutError)) { return nullptr; }

				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetStringField(TEXT("asset_path"), Blueprint->GetPathName());
				Result->SetBoolField(TEXT("saved"), true);
				Result->SetStringField(TEXT("revision"), AnimMcpGraphInspector::ComputeRevision(Blueprint));
				return Result;
			});
	}
}
