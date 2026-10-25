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
			TEXT("Create an IK Rig for a skeletal mesh (retarget chains + pelvis, optional Full Body IK) the way the editor's auto-retarget does. Params: skeletal_mesh (required), asset_path (new asset under GenerationOutputPaths; required unless existing_rig), existing_rig? (reuse: only checks the mesh is compatible — BAD_REQUEST INCOMPATIBLE_MESH otherwise — and warns PREVIEW_MESH_DIFFERS; writes nothing), mode? auto|manual (default auto: skeleton template characterization; a mesh matching no template fails with IKRIG_AUTO_FAILED and details.bones[{name,parent}] BEFORE any asset is made), pelvis? (manual: required; auto: overrides), chains? (manual: [{name, start, end, goal?}] — validated first: BONE_NOT_FOUND, END_NOT_BELOW_START, DUPLICATE_NAME/GOAL → BAD_REQUEST BAD_CHAINS), fbik? (default true: auto = template FBIK; manual = FullBodyIK solver on pelvis connected to the goals you gave), save? (default false). Finger chains are also proposed by geometry, not names (finger_chain_suggestion — also in the IKRIG_AUTO_FAILED details): the hands are the ends of the mirrored arm chain pair of the given chains (manual) or the template (auto), or with no arm chains the farthest mirrored pair of bones with 3+ finger-like child chains (2+ joints, no segment under 0.5 cm × height/170 — weapon/FX leaf bones and zero-length constraint chains drop out); the thumb is the chain deviating most from the others' mean direction; the rest are ordered index → pinky from the thumb side across the knuckles; a first joint closer to the wrist than its own segment is a metacarpal ({Side}{Finger}Metacarpal); joints past 3 phalanges (thumb: 3) at the leaf end are tips and stay out of the chain; Left/Right from the arm chain names, else the feet facing. A manual rig (or template) lacking proposed finger chains gets info diagnostic FINGER_CHAINS_SUGGESTED (+ chains[]: without them the target fingers keep their reference pose — add them to chains after the user confirms); a same-named finger chain on other bones gets warning FINGER_CHAINS_DIFFER (e.g. SOMA77 auto-characterized as Mixamo: LeftIndex = Index1..3 includes the metacarpal). Returns asset_path, reused, mode, preview_mesh, template_match, pelvis, chains[], goals[], solvers[], finger_chain_suggestion{hands_from (arm_chains | topology), side_from, chains_from, hands[{side, hand, fingers, thumb_margin_deg, tips_excluded[], issues[] (TOO_FEW_FINGER_CHAINS, THUMB_AMBIGUOUS, FINGER_COUNT_<n>)}], chains[{name, start, end}], missing[], differs[{name, given{start, end}, suggested{start, end}}], mirrored[[left, right]], not_mirrored[], skipped_reason? (NO_HANDS, SIDE_UNKNOWN)}, saved."),
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
			TEXT("Create an IK Retargeter between two IK Rigs. Params: source_rig, target_rig, source_mesh, target_mesh (all required; each mesh must be compatible with its rig — BAD_REQUEST INCOMPATIBLE_MESH), asset_path (new asset under GenerationOutputPaths; required unless existing_retargeter), existing_retargeter? (reuse: its rigs must be exactly source_rig/target_rig — BAD_REQUEST RIG_MISMATCH; writes nothing), ops? default|match_existing (default: engine default ops + exact-name chain mapping on every op; match_existing: the editor's auto-retarget recipe — exact-name chain mapping on every op (the editor maps only the FK op exactly and auto-align follows the fuzzy map left on the disabled Run IK Rig op), target pose auto-aligned, Run IK Rig off, root motion op set up, Pin Bones op with the template's pinned bones — what the project's RTG_* assets were made with), auto_align? (default false; default ops only — align the target retarget pose to the source), align_mode? engine|per_bone (default engine; only when the target pose is auto-aligned — match_existing or auto_align=true, else BAD_REQUEST ALIGN_MODE_WITHOUT_ALIGN. per_bone keeps the engine alignment, then (0) the axial chains — mapped chains on the target's midline with no left/right mirror (spine, neck, head; found geometrically: mirrored chain pairs in the target reference pose give the lateral axis and the midline plane, a chain is axial when every bone lies within a quarter of the innermost mirror pair's half-width) — and the pelvis are set to the target reference pose's global rotations turned only by the facing alignment, so the target keeps its own spine curve and neck tilt and receives only the source's motion relative to the source reference pose (the engine aligns spine and pelvis, and bone-to-bone alignment would align the neck, to the source's reference-pose shape, which then rides on every frame; both reference poses are assumed to stand upright); every mapped FK chain whose source and target bone counts match copies rotations one-to-one (FK OneToOne instead of Interpolated, which blends neighbouring source rotations when the joints sit at different chain fractions), and the non-axial ones are then aligned bone-to-bone to the matching source segment (arms and legs on the final torso); its end bone is aimed at the starts of the mapped chains right below it (two or more spread landmarks: full frame by least squares, the roll carried by the chain parent); a non-axial mapped single-bone chain with no mapped chain below it has no landmark and gets the same neutral rotation; a chain hanging from a mapped single-bone chain whose parent mapped bone is off the midline (fingers below metacarpals) is aligned relative to it — each segment to the source segment turned by the minimal rotation from the source's single-bone → chain-start segment to the target's, so the target keeps its own palm and copies the source's joint angles (MCP, PIP). The single-bone chains with chains below them (clavicles, metacarpals) and template-excluded bones (feet) stay as the engine set them), facing_yaw_deg? (default 0; the yaw in degrees about UE +Z that turns the SOURCE's facing onto the TARGET's — FK chains copy global rotation deltas, so differently facing skeletons move in the wrong plane: the target root (bone 0) is turned by -yaw in the target retarget pose before auto-align, an Additive Pose op before the Root Motion op turns it back, and a root motion op copying the source root gets +yaw in GlobalOffset; refused when the target root is the pelvis — FACING_NEEDS_ROOT), save? (default false). Returns asset_path, reused, ops_recipe, align_mode, rigs/meshes, ops[{name, type, enabled, parent}], chain_mapping{target: source|null}, unmapped_target_chains[] (+ warning UNMAPPED_TARGET_CHAINS), pin_bones[], root_motion{}, retarget_poses{source, target: {name, rotated_bones, max_rotation_deg, root_offset}}, facing_alignment{yaw_deg, target_root, restore_pose, op, op_index, enabled, consistent}|null (read from the asset; a reused retargeter whose yaw differs from facing_yaw_deg warns FACING_MISMATCH_EXISTING), pose_alignment{mode, one_to_one_chains[], interpolated_chains[], bones[{bone, deg}], relative_chains[{chain, parent_bone, offset_deg}], chain_ends[{bone, landmarks[], fit frame|direction, deg, residual_max_deg, twist_bone?, twist_deg?}], axial{lateral_axis[3], tolerance_cm, mirror_pairs[[a, b]], chains[], pelvis|null} or {skipped_reason NO_MIRROR_CHAINS}, neutral_bones[{bone, deg}] (pelvis, axial and neutral leaf bones), skipped[{bone, reason}]}|null (per_bone only; mode engine + warning ALIGN_PER_BONE_SKIPPED when it could not run), saved."),
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
				const FString AlignMode = Context.Request.GetOptionalString(TEXT("align_mode"), TEXT("engine"));
				if (AlignMode != TEXT("engine") && AlignMode != TEXT("per_bone"))
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("align_mode"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("align_mode must be engine or per_bone (got '%s')"), *AlignMode), Details);
					return nullptr;
				}
				Params.AlignMode = AlignMode == TEXT("per_bone") ? AnimMcpRetargetAssets::EAlignMode::PerBone : AnimMcpRetargetAssets::EAlignMode::Engine;
				Params.FacingYawDeg = Context.Request.GetOptionalNumber(TEXT("facing_yaw_deg"), 0.0);
				Params.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				return AnimMcpRetargetAssets::CreateRetargeter(Params, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("retarget_animations"),
			TEXT("Duplicate animation assets onto another skeleton through an IK Retargeter (the engine's batch 'Duplicate and Retarget' with an explicit output folder). Params: retargeter, assets[] (AnimSequence | AnimMontage | BlendSpace/AimOffset on the source mesh's skeleton — AnimBlueprint refused: it would duplicate and recompile parent blueprints), source_mesh, target_mesh (required; compatible with the retargeter's rigs), output_path (folder under GenerationOutputPaths), name_rule? {prefix, suffix, replace_from, replace_to}, include_referenced? (default true: montage segments, blend space samples come along), dry_run? (planned[] only), validate? (default true: validate_animation of every generated sequence against its source; FAILED → nothing saved, VALIDATION_FAILED), thresholds? (validate thresholds), fingers? (default true: the validation also runs validate_animation fingers with this retargeter — target rig hands, FK op mapping; finger warnings add diagnostic FINGER_WARNINGS), body_clearance? (default off; \"measure\" — validation adds validate_animation body_clearance on the target mesh with the retargeter's target IK Rig chains; \"resolve\" — before validation, every generated sequence's upper-arm tracks are corrected where the hands/forearms go into the target mesh's body: per frame the least-squares rotation about the shoulder that moves the arm points inside the body's radial map (validate_animation body_clearance) out along the axis-outward direction by depth + margin, iterated to 0.05 cm, smoothed in the parent (clavicle) space by a magnitude dilation (±0.13 s) then a Gaussian, re-checked up to 3 times; elbow/wrist/finger local rotations are untouched so the arm keeps its shape, frames without penetration stay as retargeted; or {mode? (default resolve), margin_cm? (default 0.5 × scale), max_deg? (default 30 — beyond it the frame is clamped, warning BODY_CLEARANCE_LIMIT), + the validate_animation body_clearance keys (mesh, ik_rig, upper_arms, body_bones, include_secondary, contact_cm, penetration_cm)}. Result body_clearance[{asset, mesh, margin_cm, max_deg, smooth_frames, arms[{upper_arm, corrected_frames_pct, deg_p50 (corrected frames), deg_p95, deg_max, deg_per_s_max, clamped_frames}], grip_changed_frames (wrists within 20 cm moved 1+ cm relative to each other — warning CLEARANCE_GRIP_CHANGED, the grip is not solved), modified, before{}, after{} (validate_animation body_clearance shape), issues[], seconds}]; warnings also add diagnostic BODY_CLEARANCE_WARNINGS), save? (default false). Never overwrites: every output name is computed first — an existing asset is ASSET_EXISTS, two outputs with one name is BAD_REQUEST NAME_COLLISION_IN_BATCH, more planned assets than [AnimGraphMcp] MaxRetargetAssetsPerCall is BAD_REQUEST LIMIT. Shows the engine's progress dialog. Returns generated[{source, asset, class, referenced}], referred[], seconds, seconds_per_asset, frames, ms_per_frame, body_clearance[]?, validation{status, assets[]}, saved."),
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
				Params.bFingers = Context.Request.GetOptionalBool(TEXT("fingers"), true);
				Params.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				if (!AnimMcpBodyClearance::ParseMode(Context.Request.Params->TryGetField(TEXT("body_clearance")), TEXT("body_clearance"), Params.BodyClearanceMode,
					Params.BodyClearance, Params.BodyClearanceOptions, OutError))
				{
					return nullptr;
				}
				return AnimMcpBatchRetarget::Run(Params, Context, OutError);
			});
	}
}
