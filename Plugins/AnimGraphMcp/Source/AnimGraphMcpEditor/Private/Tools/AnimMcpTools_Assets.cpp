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
#include "Core/AnimMcpAssetOps.h"
#include "Core/AnimMcpAssetProtection.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpBlendSpaceFactory.h"
#include "Core/AnimMcpBlueprintFactory.h"
#include "Core/AnimMcpCompiler.h"
#include "Core/AnimMcpGraphInspector.h"
#include "Core/AnimMcpMontage.h"
#include "Editor.h"
#include "Misc/PackageName.h"
#include "Subsystems/EditorAssetSubsystem.h"

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
			TEXT("List animation assets from the asset registry. Params: skeleton? (path; only assets for this skeleton), class? (AnimSequence|BlendSpace|AnimMontage|AnimComposite|all), path_prefix? (default /Game), limit? (default 200), details? (default false; loads each returned asset: BlendSpace → axes/samples under 'blendspace', AnimMontage → slots/sections under 'montage', AnimSequence → 'additive_type')."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const FString SkeletonPath = Context.Request.GetOptionalString(TEXT("skeleton"));
				const FString ClassName = Context.Request.GetOptionalString(TEXT("class"), TEXT("all"));
				const FString PathPrefix = Context.Request.GetOptionalString(TEXT("path_prefix"), TEXT("/Game"));
				const int32 Limit = FMath::Clamp(static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("limit"), 200.0)), 1, 5000);
				const bool bDetails = Context.Request.GetOptionalBool(TEXT("details"), false);

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
					// Phase 6-3: BlendSpace 축·샘플 요약 — 레지스트리 태그에 없어 로드가 필요하므로 details 요청 시에만
					if (bDetails && Data.IsInstanceOf(UBlendSpace::StaticClass()))
					{
						if (UBlendSpace* BlendSpace = Cast<UBlendSpace>(Data.GetAsset()))
						{
							Item->SetObjectField(TEXT("blendspace"), AnimMcpBlendSpaceFactory::DescribeBlendSpace(BlendSpace));
						}
					}
					// Phase 7-3: 몽타주 슬롯·섹션 요약 · 시퀀스 additive 타입(AimOffset 샘플 선별용 — 레지스트리 태그에 없다)
					else if (bDetails && Data.IsInstanceOf(UAnimMontage::StaticClass()))
					{
						if (UAnimMontage* Montage = Cast<UAnimMontage>(Data.GetAsset()))
						{
							Item->SetObjectField(TEXT("montage"), AnimMcpMontage::DescribeMontage(Montage));
						}
					}
					else if (bDetails && Data.IsInstanceOf(UAnimSequence::StaticClass()))
					{
						if (UAnimSequence* Sequence = Cast<UAnimSequence>(Data.GetAsset()))
						{
							Item->SetStringField(TEXT("additive_type"), StaticEnum<EAdditiveAnimationType>()->GetNameStringByValue(static_cast<int64>(Sequence->AdditiveAnimType)));
							// additive 로 표시돼도 기준 포즈가 없으면 BlendSpace/AimOffset 샘플로 못 쓴다 (ADDITIVE_INVALID)
							Item->SetBoolField(TEXT("additive_valid"), Sequence->AdditiveAnimType == AAT_None || Sequence->IsValidAdditive());
							Item->SetStringField(TEXT("ref_pose_type"), StaticEnum<EAdditiveBasePoseType>()->GetNameStringByValue(static_cast<int64>(Sequence->RefPoseType)));
							Item->SetField(TEXT("ref_pose_sequence"), AnimMcpJson::ObjectPathOrNull(Sequence->RefPoseSeq));
							Item->SetNumberField(TEXT("length"), Sequence->GetPlayLength());
						}
					}
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

		// ---- Phase 6-3 BlendSpace ----------------------------------------------------------------------------------

		Dispatcher.RegisterTool(TEXT("create_blendspace"),
			TEXT("Create a BlendSpace (dimensions=2) or BlendSpace1D (dimensions=1) asset — or an AimOffset (aim_offset=true → AimOffsetBlendSpace/1D; samples must be Mesh Space additive, ADDITIVE_TYPE otherwise). Params: asset_path, skeleton, dimensions (1|2), axes [{name, min, max, grid?=4, snap?=false, wrap?=false}] (one per dimension), samples? [{animation (AnimSequence path), value [x] | [x, y]}], aim_offset? (default false), preview_mesh?, overwrite? (default false; refused for protected assets), save? (default false). Samples outside the axis range, at duplicate positions, on an incompatible skeleton or with mixed additive types are refused before anything is created."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpBlendSpaceFactory::FCreateParams Params;
				if (!AnimMcpBlendSpaceFactory::ParseCreateParams(Context.Request.Params, Params, OutError)) { return nullptr; }
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UBlendSpace* BlendSpace = AnimMcpBlendSpaceFactory::CreateBlendSpace(Params, Context, OutError);
				if (!BlendSpace) { return nullptr; }

				bool bSaved = false;
				if (bSave)
				{
					UEditorAssetSubsystem* AssetSubsystem = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
					bSaved = AssetSubsystem && AssetSubsystem->SaveLoadedAsset(BlendSpace, /*bOnlyIfIsDirty*/ false);
					if (!bSaved)
					{
						Context.AddDiagnostic(TEXT("error"), AnimMcpErrorCodes::SaveFailed, FString::Printf(TEXT("SaveLoadedAsset failed for %s"), *BlendSpace->GetPathName()));
					}
				}

				TSharedRef<FJsonObject> Result = AnimMcpBlendSpaceFactory::DescribeBlendSpace(BlendSpace);
				Result->SetBoolField(TEXT("created"), true);
				Result->SetBoolField(TEXT("saved"), bSaved);
				return Result;
			});

		// ---- Phase 6-2 애셋 수명 ----------------------------------------------------------------------------------

		Dispatcher.RegisterTool(TEXT("duplicate_animation_blueprint"),
			TEXT("Duplicate an Animation Blueprint to a new path. Params: source_path, dest_path, overwrite? (default false; true deletes an existing dest — refused for protected assets), preserve_node_guids? (default true: node guids stay identical to the source so revisions/guids line up), save? (default false)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString SourcePath, DestPath;
				if (!Context.Request.GetRequiredString(TEXT("source_path"), SourcePath, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("dest_path"), DestPath, OutError)) { return nullptr; }
				const bool bOverwrite = Context.Request.GetOptionalBool(TEXT("overwrite"), false);
				const bool bPreserveGuids = Context.Request.GetOptionalBool(TEXT("preserve_node_guids"), true);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UAnimBlueprint* Source = AnimMcpAssetResolver::LoadAnimBlueprint(SourcePath, OutError);
				if (!Source) { return nullptr; }

				const FString DestPackage = AnimMcpAssetResolver::ToPackagePath(DestPath);
				FText PathReason;
				if (!FPackageName::IsValidLongPackageName(DestPackage, /*bIncludeReadOnlyRoots*/ false, &PathReason))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Invalid dest_path '%s': %s"), *DestPackage, *PathReason.ToString()));
					return nullptr;
				}
				const FString DestObjectPath = DestPackage + TEXT(".") + FPackageName::GetLongPackageAssetName(DestPackage);
				if (DestObjectPath.Equals(Source->GetPathName(), ESearchCase::IgnoreCase))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("dest_path must differ from source_path"));
					return nullptr;
				}

				if (AnimMcpAssetResolver::AssetExists(DestObjectPath))
				{
					if (!bOverwrite)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists (pass overwrite=true to replace)"), *DestObjectPath));
						return nullptr;
					}
					if (!AnimMcpAssetProtection::EnsureNotProtected(DestObjectPath, TEXT("overwrite"), OutError)) { return nullptr; }
					if (!AnimMcpAssetOps::DeleteAssetAtPath(DestObjectPath, Context, OutError)) { return nullptr; }
					Context.AddDiagnostic(TEXT("info"), TEXT("ASSET_REPLACED"), FString::Printf(TEXT("Deleted existing '%s' before duplicating"), *DestObjectPath));
				}

				const FString SourceRevision = AnimMcpGraphInspector::ComputeRevision(Source);
				UAnimBlueprint* Duplicate = AnimMcpAssetOps::DuplicateAnimBlueprint(Source, DestObjectPath, bPreserveGuids, Context, OutError);
				if (!Duplicate) { return nullptr; }

				bool bSaved = false;
				if (bSave)
				{
					FAnimMcpError SaveError;
					bSaved = AnimMcpCompiler::Save(Duplicate, SaveError);
					if (!bSaved)
					{
						Context.AddDiagnostic(TEXT("error"), *SaveError.Code, SaveError.Message);
					}
				}

				TSharedRef<FJsonObject> Result = AnimMcpGraphInspector::BuildBlueprintInfo(Duplicate, Context);
				Result->SetBoolField(TEXT("duplicated"), true);
				Result->SetStringField(TEXT("source_path"), Source->GetPathName());
				Result->SetStringField(TEXT("source_revision"), SourceRevision);
				Result->SetBoolField(TEXT("node_guids_preserved"), bPreserveGuids);
				Result->SetBoolField(TEXT("saved"), bSaved);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("delete_animation_blueprint"),
			TEXT("Delete an Animation Blueprint asset (file + in-memory). Params: asset_path, confirm (must be true), force? (default false; required when other assets reference it — their references become null). Refused with ASSET_PROTECTED for assets in [AnimGraphMcp] ProtectedAssets/ProtectedPaths."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				if (!Context.Request.GetOptionalBool(TEXT("confirm"), false))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("delete_animation_blueprint requires confirm=true"));
					return nullptr;
				}
				const bool bForce = Context.Request.GetOptionalBool(TEXT("force"), false);

				// AnimBP 만 지운다 — 다른 클래스는 BAD_REQUEST (LoadAssetOfClass)
				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				const FString ObjectPath = Blueprint->GetPathName();

				if (!AnimMcpAssetProtection::EnsureNotProtected(ObjectPath, TEXT("delete"), OutError)) { return nullptr; }

				// (7-5) 레지스트리 + 메모리 참조자 — 저장 직후 레지스트리가 늦는 타이밍에도 자식 ABP 를 놓치지 않는다
				const TArray<FString> Referencers = AnimMcpAssetOps::FindReferencersIncludingMemory(ObjectPath);
				TArray<TSharedPtr<FJsonValue>> ReferencerValues;
				for (const FString& R : Referencers) { ReferencerValues.Add(MakeShared<FJsonValueString>(R)); }
				if (Referencers.Num() > 0)
				{
					if (!bForce)
					{
						TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
						Details->SetStringField(TEXT("asset_path"), ObjectPath);
						Details->SetArrayField(TEXT("referencers"), ReferencerValues);
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetReferenced,
							FString::Printf(TEXT("'%s' is referenced by %d asset(s); pass force=true to delete anyway (references become null)"), *ObjectPath, Referencers.Num()), Details);
						return nullptr;
					}
					Context.AddDiagnostic(TEXT("warning"), TEXT("REFERENCES_BROKEN"), FString::Printf(TEXT("Force-deleting '%s' referenced by: %s"), *ObjectPath, *FString::Join(Referencers, TEXT(", "))));
				}

				if (!AnimMcpAssetOps::DeleteAssetAtPath(ObjectPath, Context, OutError)) { return nullptr; }
				if (AnimMcpAssetResolver::AssetExists(ObjectPath))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("'%s' is still in the asset registry after DeleteAsset"), *ObjectPath));
					return nullptr;
				}

				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetStringField(TEXT("asset_path"), ObjectPath);
				Result->SetBoolField(TEXT("deleted"), true);
				Result->SetBoolField(TEXT("forced"), bForce);
				Result->SetArrayField(TEXT("referencers"), ReferencerValues);
				return Result;
			});
	}
}
