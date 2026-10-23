#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpBatchRetarget.h"
#include "Core/AnimMcpGeneration.h"
#include "Core/AnimMcpRetargetAssets.h"
#include "Engine/SkeletalMesh.h"
#include "Retargeter/IKRetargeter.h"
#include "Rig/IKRigDefinition.h"

// AI 애니 생성 Phase 1 — IK Rig · IK Retargeter (Core/AnimMcpRetargetAssets). 메시는 항상 명시, 재사용은 existing_* 로만.
namespace AnimMcpTools
{
	namespace
	{
		template <typename T>
		T* LoadRequired(const FAnimMcpContext& Context, const TCHAR* Field, FAnimMcpError& OutError)
		{
			FString Path;
			if (!Context.Request.GetRequiredString(Field, Path, OutError)) { return nullptr; }
			return Cast<T>(AnimMcpAssetResolver::LoadAssetOfClass(Path, T::StaticClass(), OutError));
		}

		/** 없으면 nullptr 이고 오류 아님. 있는데 못 읽으면 OutError */
		template <typename T>
		T* LoadOptional(const FAnimMcpContext& Context, const TCHAR* Field, FAnimMcpError& OutError)
		{
			const FString Path = Context.Request.GetOptionalString(Field);
			return Path.IsEmpty() ? nullptr : Cast<T>(AnimMcpAssetResolver::LoadAssetOfClass(Path, T::StaticClass(), OutError));
		}
	}

	void RegisterRetargetTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("create_ik_rig"),
			TEXT("Create an IK Rig for a skeletal mesh (retarget chains + pelvis, optional Full Body IK) the way the editor's auto-retarget does. Params: skeletal_mesh (required), asset_path (new asset under GenerationOutputPaths; required unless existing_rig), existing_rig? (reuse: only checks the mesh is compatible — BAD_REQUEST INCOMPATIBLE_MESH otherwise — and warns PREVIEW_MESH_DIFFERS; writes nothing), mode? auto|manual (default auto: skeleton template characterization; a mesh matching no template fails with IKRIG_AUTO_FAILED and details.bones[{name,parent}] BEFORE any asset is made), pelvis? (manual: required; auto: overrides), chains? (manual: [{name, start, end, goal?}] — validated first: BONE_NOT_FOUND, END_NOT_BELOW_START, DUPLICATE_NAME/GOAL → BAD_REQUEST BAD_CHAINS), fbik? (default true: auto = template FBIK; manual = FullBodyIK solver on pelvis connected to the goals you gave), save? (default false). Returns asset_path, reused, mode, preview_mesh, template_match, pelvis, chains[], goals[], solvers[], saved."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpRetargetAssets::FIKRigParams Params;
				Params.Mesh = LoadRequired<USkeletalMesh>(Context, TEXT("skeletal_mesh"), OutError);
				if (!Params.Mesh) { return nullptr; }
				Params.ExistingRig = LoadOptional<UIKRigDefinition>(Context, TEXT("existing_rig"), OutError);
				if (OutError.IsSet()) { return nullptr; }
				if (!Params.ExistingRig && !Context.Request.GetRequiredString(TEXT("asset_path"), Params.AssetPath, OutError)) { return nullptr; }

				const FString Mode = Context.Request.GetOptionalString(TEXT("mode"), TEXT("auto"));
				if (Mode != TEXT("auto") && Mode != TEXT("manual"))
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("mode"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("mode must be auto or manual (got '%s')"), *Mode), Details);
					return nullptr;
				}
				Params.bManual = Mode == TEXT("manual");
				const FString Pelvis = Context.Request.GetOptionalString(TEXT("pelvis"));
				Params.Pelvis = Pelvis.IsEmpty() ? NAME_None : FName(*Pelvis);
				if (!AnimMcpRetargetAssets::ParseChains(Context.Request.Params, Params.Chains, OutError)) { return nullptr; }
				if (!Params.bManual && Params.Chains.Num() > 0)
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("chains"));
					Details->SetStringField(TEXT("reason"), TEXT("CHAINS_REQUIRE_MANUAL"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("chains are only used with mode=manual"), Details);
					return nullptr;
				}
				Params.bFBIK = Context.Request.GetOptionalBool(TEXT("fbik"), true);
				Params.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				return AnimMcpRetargetAssets::CreateIKRig(Params, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("create_ik_retargeter"),
			TEXT("Create an IK Retargeter between two IK Rigs. Params: source_rig, target_rig, source_mesh, target_mesh (all required; each mesh must be compatible with its rig — BAD_REQUEST INCOMPATIBLE_MESH), asset_path (new asset under GenerationOutputPaths; required unless existing_retargeter), existing_retargeter? (reuse: its rigs must be exactly source_rig/target_rig — BAD_REQUEST RIG_MISMATCH; writes nothing), ops? default|match_existing (default: engine default ops + exact-name chain mapping on every op; match_existing: the editor's auto-retarget recipe — exact FK mapping, target pose auto-aligned, Run IK Rig off, root motion op set up, Pin Bones op with the template's pinned bones — what the project's RTG_* assets were made with), auto_align? (default false; default ops only — align the target retarget pose to the source), save? (default false). Returns asset_path, reused, ops_recipe, rigs/meshes, ops[{name, type, enabled, parent}], chain_mapping{target: source|null}, unmapped_target_chains[] (+ warning UNMAPPED_TARGET_CHAINS), pin_bones[], root_motion{}, retarget_poses{source, target: {name, rotated_bones, max_rotation_deg, root_offset}}, saved."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpRetargetAssets::FRetargeterParams Params;
				Params.SourceRig = LoadRequired<UIKRigDefinition>(Context, TEXT("source_rig"), OutError);
				if (!Params.SourceRig) { return nullptr; }
				Params.TargetRig = LoadRequired<UIKRigDefinition>(Context, TEXT("target_rig"), OutError);
				if (!Params.TargetRig) { return nullptr; }
				Params.SourceMesh = LoadRequired<USkeletalMesh>(Context, TEXT("source_mesh"), OutError);
				if (!Params.SourceMesh) { return nullptr; }
				Params.TargetMesh = LoadRequired<USkeletalMesh>(Context, TEXT("target_mesh"), OutError);
				if (!Params.TargetMesh) { return nullptr; }
				Params.Existing = LoadOptional<UIKRetargeter>(Context, TEXT("existing_retargeter"), OutError);
				if (OutError.IsSet()) { return nullptr; }
				if (!Params.Existing && !Context.Request.GetRequiredString(TEXT("asset_path"), Params.AssetPath, OutError)) { return nullptr; }

				const FString Ops = Context.Request.GetOptionalString(TEXT("ops"), TEXT("default"));
				if (Ops != TEXT("default") && Ops != TEXT("match_existing"))
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("ops"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("ops must be default or match_existing (got '%s')"), *Ops), Details);
					return nullptr;
				}
				Params.Ops = Ops == TEXT("match_existing") ? AnimMcpRetargetAssets::EOpsRecipe::MatchExisting : AnimMcpRetargetAssets::EOpsRecipe::Default;
				Params.bAutoAlign = Context.Request.GetOptionalBool(TEXT("auto_align"), false);
				Params.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				return AnimMcpRetargetAssets::CreateRetargeter(Params, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("retarget_animations"),
			TEXT("Duplicate animation assets onto another skeleton through an IK Retargeter (the engine's batch 'Duplicate and Retarget' with an explicit output folder). Params: retargeter, assets[] (AnimSequence | AnimMontage | BlendSpace/AimOffset on the source mesh's skeleton — AnimBlueprint refused: it would duplicate and recompile parent blueprints), source_mesh, target_mesh (required; compatible with the retargeter's rigs), output_path (folder under GenerationOutputPaths), name_rule? {prefix, suffix, replace_from, replace_to}, include_referenced? (default true: montage segments, blend space samples come along), dry_run? (planned[] only), validate? (default true: validate_animation of every generated sequence against its source; FAILED → nothing saved, VALIDATION_FAILED), thresholds? (validate thresholds), save? (default false). Never overwrites: every output name is computed first — an existing asset is ASSET_EXISTS, two outputs with one name is BAD_REQUEST NAME_COLLISION_IN_BATCH, more planned assets than [AnimGraphMcp] MaxRetargetAssetsPerCall is BAD_REQUEST LIMIT. Shows the engine's progress dialog. Returns generated[{source, asset, class, referenced}], referred[], seconds, seconds_per_asset, frames, ms_per_frame, validation{status, assets[]}, saved."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpBatchRetarget::FParams Params;
				Params.Retargeter = LoadRequired<UIKRetargeter>(Context, TEXT("retargeter"), OutError);
				if (!Params.Retargeter) { return nullptr; }
				Params.SourceMesh = LoadRequired<USkeletalMesh>(Context, TEXT("source_mesh"), OutError);
				if (!Params.SourceMesh) { return nullptr; }
				Params.TargetMesh = LoadRequired<USkeletalMesh>(Context, TEXT("target_mesh"), OutError);
				if (!Params.TargetMesh) { return nullptr; }
				FString OutputPath;
				if (!Context.Request.GetRequiredString(TEXT("output_path"), OutputPath, OutError)) { return nullptr; }
				if (!AnimMcpGeneration::EnsureOutputPathAllowed(OutputPath, TEXT("output_path"), OutError)) { return nullptr; }
				Params.OutputPath = AnimMcpGeneration::NormalizeFolderPath(OutputPath);

				const TArray<TSharedPtr<FJsonValue>>* Assets = nullptr;
				if (!Context.Request.Params->TryGetArrayField(TEXT("assets"), Assets) || Assets->Num() == 0)
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("assets"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("assets[] needs at least one animation asset path"), Details);
					return nullptr;
				}
				for (const TSharedPtr<FJsonValue>& V : *Assets)
				{
					FString Path;
					if (!V.IsValid() || V->Type != EJson::String || !V->TryGetString(Path) || Path.IsEmpty())
					{
						TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
						Details->SetStringField(TEXT("field"), TEXT("assets"));
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("assets must be an array of asset path strings"), Details);
						return nullptr;
					}
					UObject* Object = AnimMcpAssetResolver::LoadAssetOfClass(Path, UObject::StaticClass(), OutError);
					if (!Object) { return nullptr; }
					const bool bAllowed = Object->IsA<UAnimSequence>() || Object->IsA<UAnimMontage>() || Object->IsA<UBlendSpace>();
					if (!bAllowed)
					{
						TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
						Details->SetStringField(TEXT("field"), TEXT("assets"));
						Details->SetStringField(TEXT("asset"), Object->GetPathName());
						Details->SetStringField(TEXT("reason"), Object->IsA<UAnimBlueprint>() ? TEXT("ANIM_BLUEPRINT_NOT_ALLOWED") : TEXT("UNSUPPORTED_CLASS"));
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is a %s — only AnimSequence, AnimMontage and BlendSpace/AimOffset can be retargeted here"), *Object->GetPathName(), *Object->GetClass()->GetName()), Details);
						return nullptr;
					}
					Params.Assets.AddUnique(Cast<UAnimationAsset>(Object));
				}

				const TSharedPtr<FJsonObject>* NameRule = nullptr;
				if (Context.Request.Params->TryGetObjectField(TEXT("name_rule"), NameRule))
				{
					(*NameRule)->TryGetStringField(TEXT("prefix"), Params.NameRule.Prefix);
					(*NameRule)->TryGetStringField(TEXT("suffix"), Params.NameRule.Suffix);
					(*NameRule)->TryGetStringField(TEXT("replace_from"), Params.NameRule.ReplaceFrom);
					(*NameRule)->TryGetStringField(TEXT("replace_to"), Params.NameRule.ReplaceTo);
				}
				const TSharedPtr<FJsonObject>* Thresholds = nullptr;
				if (Context.Request.Params->TryGetObjectField(TEXT("thresholds"), Thresholds))
				{
					Params.Thresholds = *Thresholds;
				}
				Params.bIncludeReferenced = Context.Request.GetOptionalBool(TEXT("include_referenced"), true);
				Params.bDryRun = Context.Request.GetOptionalBool(TEXT("dry_run"), false);
				Params.bValidate = Context.Request.GetOptionalBool(TEXT("validate"), true);
				Params.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				return AnimMcpBatchRetarget::Run(Params, Context, OutError);
			});
	}
}
