#include "AnimMcpTools.h"

#include "Animation/AnimMontage.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpMontage.h"

// Phase 7-3 — 몽타주 슬롯·섹션 · 최소형 몽타주 생성 · 스켈레톤 슬롯 등록. 노티파이는 프로젝트별 Python 파이프라인(Tools/lib/ab_montage.py) 그대로.
namespace AnimMcpTools
{
	namespace
	{
		UAnimMontage* LoadMontage(FAnimMcpContext& Context, FAnimMcpError& OutError)
		{
			FString AssetPath;
			if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
			return Cast<UAnimMontage>(AnimMcpAssetResolver::LoadAssetOfClass(AssetPath, UAnimMontage::StaticClass(), OutError));
		}

		TSharedRef<FJsonObject> MontageResult(UAnimMontage* Montage, FAnimMcpContext& Context, bool bSave, bool bDirty)
		{
			bool bSaved = false;
			if (bSave)
			{
				bSaved = AnimMcpMontage::SaveAsset(Montage, Context);
			}
			TSharedRef<FJsonObject> Result = AnimMcpMontage::DescribeMontage(Montage);
			Result->SetBoolField(TEXT("saved"), bSaved);
			Result->SetBoolField(TEXT("dirty"), bDirty && !bSaved);
			return Result;
		}
	}

	void RegisterMontageTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("create_anim_montage"),
			TEXT("Create an AnimMontage from one AnimSequence (one slot track, one segment, a 'Default' section at 0). Params: asset_path, animation (AnimSequence path; its skeleton becomes the montage skeleton), slot? (default DefaultSlot; must be registered in the skeleton), blend_in?, blend_out? (seconds), preview_mesh?, overwrite? (default false; refused for protected assets), save? (default false). Notifies are out of scope (project pipelines add them)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpMontage::FCreateParams Params;
				if (!AnimMcpMontage::ParseCreateParams(Context.Request.Params, Params, OutError)) { return nullptr; }
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UAnimMontage* Montage = AnimMcpMontage::CreateMontage(Params, Context, OutError);
				if (!Montage) { return nullptr; }

				TSharedRef<FJsonObject> Result = MontageResult(Montage, Context, bSave, /*bDirty*/ true);
				Result->SetBoolField(TEXT("created"), true);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("set_montage_slots"),
			TEXT("Rename slot tracks of an AnimMontage. Params: asset_path, slots [{index?, slot}] (index defaults to the array position; a plain string entry is allowed), save? (default false). Every slot name must already be registered in the montage's skeleton (SLOT_NOT_IN_SKELETON otherwise — use add_skeleton_slot first); duplicate track names are refused. Notifies and sections link by track index, so renaming keeps them. Same names = no-op (changed 0)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UAnimMontage* Montage = LoadMontage(Context, OutError);
				if (!Montage) { return nullptr; }
				TArray<AnimMcpMontage::FSlotSpec> Slots;
				if (!AnimMcpMontage::ParseSlotSpecs(Context.Request.Params, Slots, OutError)) { return nullptr; }
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				int32 Changed = 0;
				if (!AnimMcpMontage::SetSlots(Montage, Slots, Context, OutError, Changed)) { return nullptr; }

				TSharedRef<FJsonObject> Result = MontageResult(Montage, Context, bSave, Changed > 0);
				Result->SetNumberField(TEXT("changed"), Changed);
				Result->SetBoolField(TEXT("unchanged"), Changed == 0);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("set_montage_sections"),
			TEXT("Replace the section list of an AnimMontage. Params: asset_path, sections [{name, start (seconds), next? (section name; omit/null = stop at the section end; its own name = loop)}], save? (default false). The whole list is replaced (sorted by start); names must be unique, starts inside [0, length], next must name a section in the request. Re-applying the same list is a no-op (unchanged=true). Notifies are unaffected."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UAnimMontage* Montage = LoadMontage(Context, OutError);
				if (!Montage) { return nullptr; }
				TArray<AnimMcpMontage::FSectionSpec> Sections;
				if (!AnimMcpMontage::ParseSectionSpecs(Context.Request.Params, Sections, OutError)) { return nullptr; }
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				bool bUnchanged = false;
				if (!AnimMcpMontage::SetSections(Montage, Sections, Context, OutError, bUnchanged)) { return nullptr; }

				TSharedRef<FJsonObject> Result = MontageResult(Montage, Context, bSave, !bUnchanged);
				Result->SetBoolField(TEXT("unchanged"), bUnchanged);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("add_skeleton_slot"),
			TEXT("Register a montage slot name on a Skeleton (optionally in a slot group). Params: skeleton, slot, group? (default DefaultGroup; created if missing), confirm (must be true — this edits a shared asset), save? (default false; saves the skeleton). An existing slot in another group is moved. Slot and group names share one namespace (SLOT_IS_GROUP / GROUP_IS_SLOT). Returns {slot, group, added, moved_from, group_created, unchanged, slot_groups[], saved}."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString SkeletonPath, Slot;
				if (!Context.Request.GetRequiredString(TEXT("skeleton"), SkeletonPath, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("slot"), Slot, OutError)) { return nullptr; }
				if (!Context.Request.GetOptionalBool(TEXT("confirm"), false))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("add_skeleton_slot requires confirm=true (it edits the skeleton asset)"));
					return nullptr;
				}
				const FString Group = Context.Request.GetOptionalString(TEXT("group"));
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				USkeleton* Skeleton = AnimMcpAssetResolver::LoadSkeleton(SkeletonPath, OutError);
				if (!Skeleton) { return nullptr; }

				TSharedPtr<FJsonObject> Result = AnimMcpMontage::AddSkeletonSlot(Skeleton, Slot, Group, Context, OutError);
				if (!Result.IsValid()) { return nullptr; }
				bool bSaved = false;
				if (bSave)
				{
					bSaved = AnimMcpMontage::SaveAsset(Skeleton, Context);
				}
				Result->SetBoolField(TEXT("saved"), bSaved);
				return Result;
			});
	}
}
