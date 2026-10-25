#include "AnimMcpTools.h"

#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAnimValidator.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpGeneration.h"

// AI 애니 생성 Phase 1 — 애니메이션 검증 (Core/AnimMcpAnimValidator). 읽기 전용: 호출 중 새로 더티가 된 패키지가 있으면 경고만 붙인다.
namespace AnimMcpTools
{
	namespace
	{
		FAnimMcpError FieldError(const TCHAR* Field, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		/** 문자열 배열 (null 항목은 AllowNull 일 때 빈 문자열) */
		bool ReadStrings(const TSharedRef<FJsonObject>& Params, const TCHAR* Field, bool bAllowNull, TArray<FString>& Out, FAnimMcpError& OutError)
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (!Params->HasField(Field))
			{
				return true;
			}
			if (!Params->TryGetArrayField(Field, Array))
			{
				OutError = FieldError(Field, FString::Printf(TEXT("%s must be an array of strings"), Field));
				return false;
			}
			for (const TSharedPtr<FJsonValue>& V : *Array)
			{
				if (V.IsValid() && V->Type == EJson::String)
				{
					Out.Add(V->AsString());
				}
				else if (bAllowNull && (!V.IsValid() || V->Type == EJson::Null))
				{
					Out.Add(FString());
				}
				else
				{
					OutError = FieldError(Field, FString::Printf(TEXT("%s must be an array of strings%s"), Field, bAllowNull ? TEXT(" or null") : TEXT("")));
					return false;
				}
			}
			return true;
		}

		bool ReadNumbers(const TSharedRef<FJsonObject>& Params, const TCHAR* Field, TArray<double>& Out, FAnimMcpError& OutError)
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (!Params->HasField(Field))
			{
				return true;
			}
			if (!Params->TryGetArrayField(Field, Array))
			{
				OutError = FieldError(Field, FString::Printf(TEXT("%s must be an array of numbers"), Field));
				return false;
			}
			for (const TSharedPtr<FJsonValue>& V : *Array)
			{
				if (!V.IsValid() || V->Type != EJson::Number)
				{
					OutError = FieldError(Field, FString::Printf(TEXT("%s must be an array of numbers"), Field));
					return false;
				}
				Out.Add(V->AsNumber());
			}
			return true;
		}

		UAnimSequence* LoadSequence(const FString& Path, const TCHAR* Field, FAnimMcpError& OutError)
		{
			UObject* Object = AnimMcpAssetResolver::LoadAssetOfClass(Path, UAnimationAsset::StaticClass(), OutError);
			if (!Object)
			{
				return nullptr;
			}
			UAnimSequence* Sequence = Cast<UAnimSequence>(Object);
			if (!Sequence)
			{
				OutError = FieldError(Field, FString::Printf(TEXT("'%s' is a %s — validate_animation measures AnimSequences (validate a montage's or blend space's sequences)"), *Path, *Object->GetClass()->GetName()));
				OutError.Details->SetStringField(TEXT("reason"), TEXT("NOT_A_SEQUENCE"));
			}
			return Sequence;
		}
	}

	void RegisterValidationTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("validate_animation"),
			TEXT("Measure AnimSequences (read-only). Params: assets[] (AnimSequence paths), sources?[] (same order, null to skip — relative checks), skeleton? (expected skeleton → SKELETON_MISMATCH error), checks? (subset of structural, numeric, relative; default all), thresholds?{max_deg_per_frame, ang_speed_p99_ratio_min/max, foot_planted_ratio_max, root_travel_ratio_min/max, loop_boundary_ratio_max, foot_planted_height, seam_ratio_max}, feet?[] / pelvis? (bones of the assets; default foot_l/foot_r · pelvis), source_feet?[] / source_pelvis?, expect?{length, length_tolerance (default one frame), loop, root_yaw_delta (° first→last, unwrapped, signed), root_yaw_tolerance (default 5)} (applies to every asset; mismatch → EXPECT_LENGTH / EXPECT_LOOP / EXPECT_ROOT_YAW → FAILED), seams?[] (seconds where segments meet; a step over seam_ratio_max × the surrounding frames → SEAM_JUMP warning), profile_bones?[] (numeric.profile{times[], speed_cm_s{bone: []}} — per-frame component-space speed, ≤ 240 samples of the bucket max, to find strike windows), profile_positions? (default false: also numeric.profile.position_cm{bone: [[x,y,z]]} at the same times — e.g. the plane a hand moves in), body_clearance? (true or {mesh? (default: the skeleton's preview mesh; must use the animation's skeleton), ik_rig? (chain source; default: the mesh's auto-characterization), upper_arms?[2] + body_bones?[] (explicit — body_bones are used as given, not widened to descendants), include_secondary? (default false), contact_cm? (default 1), penetration_cm? (default 2; both defaults × target pelvis reference height / 100 cm)} — how deep the hands/forearms go into the body of the target MESH: the LOD0 skinned vertices are linear-blend skinned per frame; arm points = vertices bound mostly to the elbow bone and below (within 7 cm of the arm bones, so weapons on the hand are left out), body points = pelvis, spine (common ancestors of both upper arms) and thighs plus their short helper bones (twist, breast, belt — stopping at bones that start other chains); a hanging branch of 3+ bones (coat tails, hair — often physics-driven) is 'secondary', reported only with include_secondary. Arms and legs are found from chains geometrically, not by name: mirrored chain pairs (2+ bones, reflected across the perpendicular bisector of their starts), the most-rooted pair ending lowest = legs, the other with most descendants = arms. Depth = radial map: per frame, around the torso axis (hip-joint midpoint → spine top) and each thigh axis (hip → knee), the largest radius of the body vertices in each (axis position × 10° angle) cell — depth of an arm point = that radius − its distance from the axis (the outer surface of clothes/belts/pouches counts; deep points get a depth and an outward direction). Result body_clearance{mesh, chains_from, scale, contact_cm, penetration_cm, frames, arms[{upper_arm, elbow, points, frames_over_contact_pct, frames_over_penetration_pct, depth_p50/p95/max, worst{frame, time, arm_bone, body_bone}, body_bones_hit[{bone, frames}]}], body{core_roots[], core_points, secondary_branches[], secondary_points, pelvis}, secondary_arms[]?, issues[], seconds} or {skipped_reason (NO_MESH, MESH_SKELETON_MISMATCH, NO_ARM_CHAINS, NO_PELVIS, NO_IMPORTED_MODEL, …), issues[BODY_CLEARANCE_SKIPPED info]}; a depth over penetration_cm → warning BODY_PENETRATION → PASSED_WITH_WARNINGS), fingers? (true or {ik_rig? (hands/chains source; default: the retargeter's target rig, else the skeleton preview mesh's auto-characterization, else topology), retargeter? (the FK op's chain mapping — without it the unmapped check is skipped), mesh? (the target mesh whose reference pose is compared; default the retargeter's target preview mesh, else the skeleton's reference pose — a skeleton shared by many meshes can differ from the mesh retargeted onto, Vesper fingers by up to 14°)} — hands and fingers are found by geometry, not names (the same finger topology as create_ik_rig finger_chain_suggestion); per frame: every finger bone with no mapped source chain must keep its reference local rotation (> 2° → FINGER_UNMAPPED_NOT_REFERENCE: an unmapped target finger bent by the retarget pose, e.g. auto-align following a fuzzy map on a disabled op), the non-thumb MCP (metacarpal or wrist → first → second joint) and PIP bends, signed + toward the palm by hand chirality (left palm −(x × lat), right +(x × lat), x = wrist → knuckles, lat = index knuckle − pinky knuckle), must stay within MCP −60..110° and PIP −25..130° (FINGER_BEND_REVERSED / FINGER_OVERBENT; Vesper's 57 shipped clips stay within MCP −37..102°, PIP 1.5..113°), and the fingertips must keep the index → pinky lateral order on all but 5% of frames (FINGER_ORDER_BROKEN). Result fingers{topology_from, chains_from, reference_mesh, mapping_from, hands[{side, hand, order_broken_pct, fingers[{finger, chain, metacarpal_chain?, mapped, mcp{min,p50,max}, pip{…}}], issues[]}], unmapped[{bone, chain, max_deg, frame}], thresholds{}, issues[]} or {skipped_reason (NO_HANDS, SIDE_UNKNOWN, NO_POSE), issues[FINGERS_SKIPPED info]}; warnings → PASSED_WITH_WARNINGS). Per asset: status PASSED | PASSED_WITH_WARNINGS | NEEDS_REVIEW | FAILED, structural[{level, code, message}] (NO_SKELETON, SKELETON_MISMATCH, NO_FRAMES, TRACK_BONE_MISSING, NAN, ABNORMAL_SCALE, ROTATION_JUMP > max_deg_per_frame → FAILED — a source that jumps as much makes it ROTATION_JUMP_INHERITED; NOT_SAVED info), numeric{frames, frame_rate, length, loop, ang_speed_p50/p99/max(+bone) °/s, max_deg_per_frame, feet, foot_planted_p50 cm/s, loop_boundary_max_deg, loop_boundary_ratio, root_travel_cm, root_displacement_cm, root_yaw_delta_deg, pelvis_height_cm}, request{length, loop, root_yaw_delta_deg, seams[{time, frame, step_ratio}], issues[]} (with expect/seams), relative (source on another skeleton: ratios with warnings outside thresholds + source_numeric; source on the same skeleton: per_bone_rot_diff_deg{p50,p99,max,worst[]} and per_bone_pos_diff_cm — regression comparison), needs_review[] (always the visual check). Absolute speed limits are not used: normal attacks reach ~2,000°/s p99. Result {status (worst), assets[], thresholds}."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const AnimMcpGeneration::FDirtyGuard Guard;
				const TSharedRef<FJsonObject>& Params = Context.Request.Params;
				TArray<FString> AssetPaths, SourcePaths, Checks, Feet, SourceFeet;
				if (!ReadStrings(Params, TEXT("assets"), false, AssetPaths, OutError)) { return nullptr; }
				if (AssetPaths.Num() == 0)
				{
					OutError = FieldError(TEXT("assets"), TEXT("assets[] needs at least one AnimSequence path"));
					return nullptr;
				}
				if (!ReadStrings(Params, TEXT("sources"), true, SourcePaths, OutError)) { return nullptr; }
				if (SourcePaths.Num() > 0 && SourcePaths.Num() != AssetPaths.Num())
				{
					OutError = FieldError(TEXT("sources"), FString::Printf(TEXT("sources[] must have the same length as assets[] (%d vs %d) — use null to skip one"), SourcePaths.Num(), AssetPaths.Num()));
					return nullptr;
				}
				if (!ReadStrings(Params, TEXT("checks"), false, Checks, OutError)) { return nullptr; }
				if (!ReadStrings(Params, TEXT("feet"), false, Feet, OutError)) { return nullptr; }
				if (!ReadStrings(Params, TEXT("source_feet"), false, SourceFeet, OutError)) { return nullptr; }

				AnimMcpAnimValidator::FOptions Options;
				if (Checks.Num() > 0)
				{
					for (const FString& Check : Checks)
					{
						if (Check != TEXT("structural") && Check != TEXT("numeric") && Check != TEXT("relative"))
						{
							OutError = FieldError(TEXT("checks"), FString::Printf(TEXT("Unknown check '%s' (structural, numeric, relative)"), *Check));
							return nullptr;
						}
					}
					Options.bStructural = Checks.Contains(TEXT("structural"));
					Options.bNumeric = Checks.Contains(TEXT("numeric"));
					Options.bRelative = Checks.Contains(TEXT("relative"));
				}
				const TSharedPtr<FJsonObject>* Thresholds = nullptr;
				Params->TryGetObjectField(TEXT("thresholds"), Thresholds);
				if (!AnimMcpAnimValidator::ParseThresholds(Thresholds ? *Thresholds : nullptr, Options.Thresholds, OutError)) { return nullptr; }
				const TSharedPtr<FJsonObject>* Expect = nullptr;
				if (Params->HasField(TEXT("expect")) && !Params->TryGetObjectField(TEXT("expect"), Expect))
				{
					OutError = FieldError(TEXT("expect"), TEXT("expect must be an object"));
					return nullptr;
				}
				if (!AnimMcpAnimValidator::ParseExpect(Expect ? *Expect : nullptr, Options.Expect, OutError)) { return nullptr; }
				if (!ReadNumbers(Params, TEXT("seams"), Options.Seams, OutError)) { return nullptr; }
				TArray<FString> ProfileBones;
				if (!ReadStrings(Params, TEXT("profile_bones"), false, ProfileBones, OutError)) { return nullptr; }
				for (const FString& Bone : ProfileBones) { Options.ProfileBones.Add(FName(*Bone)); }
				Options.bProfilePositions = Context.Request.GetOptionalBool(TEXT("profile_positions"), false);
				const FString SkeletonPath = Context.Request.GetOptionalString(TEXT("skeleton"));
				if (!SkeletonPath.IsEmpty())
				{
					Options.ExpectedSkeleton = AnimMcpAssetResolver::LoadSkeleton(SkeletonPath, OutError);
					if (!Options.ExpectedSkeleton) { return nullptr; }
				}
				for (const FString& F : Feet) { Options.Feet.Add(FName(*F)); }
				for (const FString& F : SourceFeet) { Options.SourceFeet.Add(FName(*F)); }
				const FString Pelvis = Context.Request.GetOptionalString(TEXT("pelvis"));
				const FString SourcePelvis = Context.Request.GetOptionalString(TEXT("source_pelvis"));
				Options.Pelvis = Pelvis.IsEmpty() ? NAME_None : FName(*Pelvis);
				Options.SourcePelvis = SourcePelvis.IsEmpty() ? NAME_None : FName(*SourcePelvis);
				{
					bool bClearance = false;
					AnimMcpBodyClearance::FSpec Spec;
					if (!AnimMcpBodyClearance::ParseSpec(Params->TryGetField(TEXT("body_clearance")), TEXT("body_clearance"), {}, Spec, bClearance, OutError)) { return nullptr; }
					if (bClearance) { Options.BodyClearance = Spec; }
				}
				{
					bool bFingers = false;
					AnimMcpFingerChains::FCheckSpec Spec;
					if (!AnimMcpFingerChains::ParseSpec(Params->TryGetField(TEXT("fingers")), TEXT("fingers"), Spec, bFingers, OutError)) { return nullptr; }
					if (bFingers) { Options.Fingers = Spec; }
				}

				// 전부 로드한 뒤 측정 — 경로 오류로 중간에 멈추지 않게
				TArray<UAnimSequence*> Assets, Sources;
				for (int32 i = 0; i < AssetPaths.Num(); ++i)
				{
					UAnimSequence* Asset = LoadSequence(AssetPaths[i], TEXT("assets"), OutError);
					if (!Asset) { return nullptr; }
					Assets.Add(Asset);
					UAnimSequence* Source = nullptr;
					if (SourcePaths.IsValidIndex(i) && !SourcePaths[i].IsEmpty())
					{
						Source = LoadSequence(SourcePaths[i], TEXT("sources"), OutError);
						if (!Source) { return nullptr; }
					}
					Sources.Add(Source);
				}

				FString Worst = TEXT("PASSED");
				TArray<TSharedPtr<FJsonValue>> Results;
				for (int32 i = 0; i < Assets.Num(); ++i)
				{
					TSharedRef<FJsonObject> One = AnimMcpAnimValidator::Validate(Assets[i], Sources[i], Options);
					Worst = AnimMcpAnimValidator::WorstStatus(Worst, One->GetStringField(TEXT("status")));
					Results.Add(MakeShared<FJsonValueObject>(One));
				}
				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetStringField(TEXT("status"), Worst);
				Result->SetArrayField(TEXT("assets"), Results);
				Result->SetObjectField(TEXT("thresholds"), AnimMcpAnimValidator::ThresholdsToJson(Options.Thresholds));

				TArray<FString> Allowed, Unexpected;
				Guard.GetNewlyDirty(Allowed, Unexpected);
				Unexpected.Append(Allowed);
				if (Unexpected.Num() > 0)
				{
					Context.AddDiagnostic(TEXT("warning"), AnimMcpErrorCodes::UnexpectedDirty,
						FString::Printf(TEXT("Read-only validation left %d package(s) dirty: %s"), Unexpected.Num(), *FString::Join(Unexpected, TEXT(", "))));
				}
				return Result;
			});
	}
}
