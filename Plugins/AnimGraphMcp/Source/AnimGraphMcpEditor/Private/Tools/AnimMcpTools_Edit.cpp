#include "AnimMcpTools.h"

#include "Animation/AnimSequence.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAnimEdit.h"
#include "Core/AnimMcpAssetResolver.h"

// AI 애니 생성 Phase 2 — 기존 모션 키 편집 (Core/AnimMcpAnimEdit · AnimMcpAnimEditOps). 원본은 읽기만 하고 결과는 항상 새 애셋.
namespace AnimMcpTools
{
	namespace
	{
		bool ParseRequest(FAnimMcpContext& Context, bool bApply, AnimMcpAnimEdit::FRequest& Out, FAnimMcpError& OutError)
		{
			const TSharedRef<FJsonObject>& Params = Context.Request.Params;
			FString SourcePath;
			if (!Context.Request.GetRequiredString(TEXT("source"), SourcePath, OutError))
			{
				return false;
			}
			UObject* Object = AnimMcpAssetResolver::LoadAssetOfClass(SourcePath, UAnimationAsset::StaticClass(), OutError);
			if (!Object)
			{
				return false;
			}
			Out.Source = Cast<UAnimSequence>(Object);
			if (!Out.Source)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), TEXT("source"));
				Details->SetStringField(TEXT("reason"), TEXT("NOT_A_SEQUENCE"));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest,
					FString::Printf(TEXT("'%s' is a %s — edits work on AnimSequences (edit a montage's or blend space's sequence)"), *SourcePath, *Object->GetClass()->GetName()), Details);
				return false;
			}
			if (bApply)
			{
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), Out.AssetPath, OutError))
				{
					return false;
				}
			}
			else
			{
				Out.AssetPath = Context.Request.GetOptionalString(TEXT("asset_path"));
			}
			const TArray<TSharedPtr<FJsonValue>>* Operations = nullptr;
			if (!Params->TryGetArrayField(TEXT("operations"), Operations))
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), TEXT("operations"));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("operations must be an array of {op, ...}"), Details);
				return false;
			}
			Out.Operations = *Operations;
			bool bValue = false;
			if (Params->TryGetBoolField(TEXT("loop"), bValue)) { Out.bLoop = bValue; }
			if (Params->TryGetBoolField(TEXT("root_motion"), bValue)) { Out.bRootMotion = bValue; }
			Out.bValidate = Context.Request.GetOptionalBool(TEXT("validate"), true);
			Out.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
			const TSharedPtr<FJsonObject>* Thresholds = nullptr;
			if (Params->TryGetObjectField(TEXT("thresholds"), Thresholds))
			{
				Out.Thresholds = *Thresholds;
			}
			return true;
		}
	}

	void RegisterEditTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("preview_animation_edits"),
			FString(TEXT("Compute a batch of key edits on an AnimSequence in memory WITHOUT creating anything. Params: source (AnimSequence — read only), operations[], asset_path? (reports would_create{allowed, exists}), loop?, root_motion?. "
			             "Returns valid, planned[{index, op, ok, error{code, message}?, skipped?, range{start, end, start_key, end_key}, length_before, length_after, note?}] (parse errors are reported for every op; apply stops at the first failing op), "
			             "result{frame_rate, frames, length, bone_tracks, curves[], root_yaw_delta_deg, root_displacement_cm, max_rate, sources[], notifies{kept, truncated, dropped[]}, sync_markers{kept, dropped}}, "
			             "seams[{time, frame, step_ratio, jump}] (where segments meet — step_ratio = pose step at the seam / surrounding frames; jump above 3.0), limitations[]. ")) + AnimMcpAnimEdit::OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpAnimEdit::FRequest Request;
				if (!ParseRequest(Context, /*bApply*/ false, Request, OutError)) { return nullptr; }
				return AnimMcpAnimEdit::Preview(Request, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("apply_animation_edits"),
			FString(TEXT("Create a NEW AnimSequence from key edits of an existing one (the source is never modified). Params: source, asset_path (new asset under [AnimGraphMcp] GenerationOutputPaths — OUTPUT_PATH_NOT_ALLOWED / ASSET_EXISTS otherwise; never overwrites), operations[], loop?, root_motion? (default: the source's), validate? (default true), thresholds? (validate_animation thresholds), save? (default false). "
			             "All operations are computed in memory first — any failure is BAD_REQUEST with details.planned and nothing is created. Then the source is duplicated (keeps root motion, compression, additive settings, curve metadata), "
			             "bone tracks and float curves are rewritten, notifies and sync markers move with the timeline (those in trimmed or reversed parts are dropped — NOTIFIES_DROPPED), transform curves and bone attributes are not carried (TRANSFORM_CURVES_DROPPED · ATTRIBUTES_DROPPED). "
			             "Built-in validation: structure, one-frame rotation (a jump explained by the sources × the max playback rate is ROTATION_JUMP_INHERITED), expect{length, loop, root_yaw_delta} of what was written, seams (SEAM_JUMP warning); FAILED → VALIDATION_FAILED, nothing saved, the asset stays unsaved in memory. "
			             "Then the global dirty-package check (UNEXPECTED_DIRTY) and the save. Returns asset_path, source, the preview fields, validation{status, asset, thresholds, inherited_max_deg_per_frame}, saved, seconds. ")) + AnimMcpAnimEdit::OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpAnimEdit::FRequest Request;
				if (!ParseRequest(Context, /*bApply*/ true, Request, OutError)) { return nullptr; }
				return AnimMcpAnimEdit::Apply(Request, Context, OutError);
			});
	}
}
