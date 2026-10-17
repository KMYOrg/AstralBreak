#include "AnimMcpMontage.h"

#include "AnimMcpAssetOps.h"
#include "AnimMcpAssetProtection.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpLog.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "Editor.h"
#include "Engine/SkeletalMesh.h"
#include "Misc/PackageName.h"
#include "Subsystems/EditorAssetSubsystem.h"
#include "UObject/Package.h"

namespace AnimMcpMontage
{
	namespace
	{
		FAnimMcpError FieldError(const FString& Field, const FString& Message, const TCHAR* Reason = nullptr)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			if (Reason) { Details->SetStringField(TEXT("reason"), Reason); }
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		/** 슬롯·그룹·섹션 이름 — 공백 제거, 비어 있거나 "None" 이면 거부 */
		bool ParseName(const FString& Raw, const FString& Field, FName& Out, FAnimMcpError& OutError)
		{
			const FString Trimmed = Raw.TrimStartAndEnd();
			if (Trimmed.IsEmpty() || Trimmed.Equals(TEXT("None"), ESearchCase::IgnoreCase))
			{
				OutError = FieldError(Field, FString::Printf(TEXT("'%s' must be a non-empty name"), *Field), TEXT("EMPTY_NAME"));
				return false;
			}
			Out = FName(*Trimmed);
			return true;
		}

		TSharedRef<FJsonObject> DescribeSegment(const FAnimSegment& Segment)
		{
			TSharedRef<FJsonObject> S = AnimMcpJson::MakeObject();
			S->SetField(TEXT("animation"), AnimMcpJson::ObjectPathOrNull(Segment.GetAnimReference()));
			S->SetNumberField(TEXT("start"), Segment.StartPos);
			S->SetNumberField(TEXT("length"), Segment.GetLength());
			S->SetNumberField(TEXT("anim_start"), Segment.AnimStartTime);
			S->SetNumberField(TEXT("anim_end"), Segment.AnimEndTime);
			S->SetNumberField(TEXT("play_rate"), Segment.AnimPlayRate);
			S->SetNumberField(TEXT("loop_count"), Segment.LoopingCount);
			return S;
		}
	}

	bool SkeletonHasSlot(const USkeleton* Skeleton, FName Slot)
	{
		if (Slot == FAnimSlotGroup::DefaultSlotName)
		{
			return true;
		}
		return Skeleton && Skeleton->ContainsSlotName(Slot);
	}

	TArray<TSharedPtr<FJsonValue>> SlotGroupsArray(const USkeleton* Skeleton)
	{
		TArray<TSharedPtr<FJsonValue>> Groups;
		if (!Skeleton)
		{
			return Groups;
		}
		for (const FAnimSlotGroup& Group : Skeleton->GetSlotGroups())
		{
			TSharedRef<FJsonObject> G = AnimMcpJson::MakeObject();
			G->SetStringField(TEXT("group"), Group.GroupName.ToString());
			TArray<TSharedPtr<FJsonValue>> Slots;
			for (const FName& SlotName : Group.SlotNames)
			{
				Slots.Add(MakeShared<FJsonValueString>(SlotName.ToString()));
			}
			G->SetArrayField(TEXT("slots"), Slots);
			Groups.Add(MakeShared<FJsonValueObject>(G));
		}
		return Groups;
	}

	bool SaveAsset(UObject* Asset, FAnimMcpContext& Context)
	{
		UEditorAssetSubsystem* AssetSubsystem = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
		const bool bSaved = Asset && AssetSubsystem && AssetSubsystem->SaveLoadedAsset(Asset, /*bOnlyIfIsDirty*/ false);
		if (!bSaved)
		{
			Context.AddDiagnostic(TEXT("error"), AnimMcpErrorCodes::SaveFailed, FString::Printf(TEXT("SaveLoadedAsset failed for %s"), *GetPathNameSafe(Asset)));
		}
		return bSaved;
	}

	// ---- 생성 ----------------------------------------------------------------------------------------------------

	bool ParseCreateParams(const TSharedRef<FJsonObject>& Params, FCreateParams& Out, FAnimMcpError& OutError)
	{
		if (!Params->TryGetStringField(TEXT("asset_path"), Out.AssetPath) || Out.AssetPath.IsEmpty())
		{
			OutError = FieldError(TEXT("asset_path"), TEXT("Missing or empty required string parameter 'asset_path'"));
			return false;
		}
		if (!Params->TryGetStringField(TEXT("animation"), Out.AnimationPath) || Out.AnimationPath.IsEmpty())
		{
			OutError = FieldError(TEXT("animation"), TEXT("Missing or empty required string parameter 'animation' (AnimSequence path)"));
			return false;
		}
		Params->TryGetStringField(TEXT("slot"), Out.SlotName);
		Params->TryGetStringField(TEXT("preview_mesh"), Out.PreviewMeshPath);
		Params->TryGetBoolField(TEXT("overwrite"), Out.bOverwrite);
		double Value = 0.0;
		if (Params->TryGetNumberField(TEXT("blend_in"), Value))
		{
			if (Value < 0.0) { OutError = FieldError(TEXT("blend_in"), TEXT("'blend_in' must be >= 0")); return false; }
			Out.BlendIn = static_cast<float>(Value);
		}
		if (Params->TryGetNumberField(TEXT("blend_out"), Value))
		{
			if (Value < 0.0) { OutError = FieldError(TEXT("blend_out"), TEXT("'blend_out' must be >= 0")); return false; }
			Out.BlendOut = static_cast<float>(Value);
		}
		return true;
	}

	UAnimMontage* CreateMontage(const FCreateParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());

		const FString PackagePath = AnimMcpAssetResolver::ToPackagePath(Params.AssetPath);
		FText PathReason;
		if (!FPackageName::IsValidLongPackageName(PackagePath, /*bIncludeReadOnlyRoots*/ false, &PathReason))
		{
			OutError = FieldError(TEXT("asset_path"), FString::Printf(TEXT("Invalid package path '%s': %s"), *PackagePath, *PathReason.ToString()));
			return nullptr;
		}
		const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
		const FString ObjectPath = PackagePath + TEXT(".") + AssetName;

		UAnimSequence* Sequence = Cast<UAnimSequence>(AnimMcpAssetResolver::LoadAssetOfClass(Params.AnimationPath, UAnimSequence::StaticClass(), OutError));
		if (!Sequence)
		{
			if (OutError.Details.IsValid()) { OutError.Details->SetStringField(TEXT("field"), TEXT("animation")); }
			return nullptr;
		}
		USkeleton* Skeleton = Sequence->GetSkeleton();
		if (!Skeleton)
		{
			OutError = FieldError(TEXT("animation"), FString::Printf(TEXT("'%s' has no skeleton"), *Sequence->GetPathName()), TEXT("NO_SKELETON"));
			return nullptr;
		}

		FName SlotName = FAnimSlotGroup::DefaultSlotName;
		if (!Params.SlotName.IsEmpty())
		{
			if (!ParseName(Params.SlotName, TEXT("slot"), SlotName, OutError)) { return nullptr; }
			if (!SkeletonHasSlot(Skeleton, SlotName))
			{
				OutError = FieldError(TEXT("slot"), FString::Printf(TEXT("Slot '%s' is not registered in skeleton '%s' (register it first with add_skeleton_slot)"), *SlotName.ToString(), *Skeleton->GetPathName()), TEXT("SLOT_NOT_IN_SKELETON"));
				return nullptr;
			}
		}

		USkeletalMesh* PreviewMesh = nullptr;
		if (!Params.PreviewMeshPath.IsEmpty())
		{
			PreviewMesh = Cast<USkeletalMesh>(AnimMcpAssetResolver::LoadAssetOfClass(Params.PreviewMeshPath, USkeletalMesh::StaticClass(), OutError));
			if (!PreviewMesh) { return nullptr; }
		}

		// 기존 애셋 — 보호 → 삭제 (AnimMcpAssetOps, Phase 6-2)
		if (AnimMcpAssetResolver::AssetExists(ObjectPath))
		{
			if (!Params.bOverwrite)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists (pass overwrite=true to replace)"), *ObjectPath));
				return nullptr;
			}
			if (!AnimMcpAssetProtection::EnsureNotProtected(ObjectPath, TEXT("overwrite"), OutError)) { return nullptr; }
			if (!AnimMcpAssetOps::DeleteAssetAtPath(ObjectPath, Context, OutError)) { return nullptr; }
			Context.AddDiagnostic(TEXT("info"), TEXT("ASSET_REPLACED"), FString::Printf(TEXT("Deleted existing '%s' before creating"), *ObjectPath));
		}

		UPackage* Package = CreatePackage(*PackagePath);
		if (!Package)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("CreatePackage failed for '%s'"), *PackagePath));
			return nullptr;
		}
		Package->FullyLoad();
		if (UObject* Stale = FindObject<UObject>(Package, *AssetName))
		{
			const FName StaleName = MakeUniqueObjectName(GetTransientPackage(), Stale->GetClass(), FName(*(AssetName + TEXT("_MCP_STALE"))));
			Stale->ClearFlags(RF_Public | RF_Standalone);
			if (!Stale->Rename(*StaleName.ToString(), GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("An object named '%s' still exists in package '%s' and could not be moved aside"), *AssetName, *PackagePath));
				return nullptr;
			}
			Stale->MarkAsGarbage();
			Context.AddDiagnostic(TEXT("info"), TEXT("STALE_OBJECT_MOVED"), FString::Printf(TEXT("In-memory object '%s' survived deletion; moved to transient package before creating"), *AssetName));
		}

		// 팩토리 재현 (AnimMontageFactory.cpp:72-104)
		UAnimMontage* Montage = NewObject<UAnimMontage>(Package, UAnimMontage::StaticClass(), FName(*AssetName), RF_Public | RF_Standalone | RF_Transactional);
		if (!Montage)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("NewObject<UAnimMontage> returned null"));
			return nullptr;
		}
		if (Montage->SlotAnimTracks.Num() == 0)
		{
			Montage->AddSlot(SlotName);
		}
		else
		{
			Montage->SlotAnimTracks[0].SlotName = SlotName;
		}
		FAnimSegment NewSegment;
		NewSegment.SetAnimReference(Sequence, /*bInitialize*/ true);
		Montage->SlotAnimTracks[0].AnimTrack.AnimSegments.Add(NewSegment);
		Montage->SetCompositeLength(Sequence->GetPlayLength());
		// UAnimMontage 는 이 오버라이드를 private 으로 내렸다(AnimMontage.h:994) — 베이스의 public 가상 함수(AnimCompositeBase.h:344)로 호출.
		// PostEditChangeProperty 도 같은 것을 부르지만(AnimMontage.cpp:802) 팩토리 순서를 그대로 둔다
		static_cast<UAnimCompositeBase*>(Montage)->UpdateCommonTargetFrameRate();
		Montage->SetSkeleton(Skeleton);
		if (PreviewMesh)
		{
			Montage->SetPreviewMesh(PreviewMesh);
		}
		// 시작 섹션 (EnsureStartingSection, AnimMontageFactory.cpp:116-136)
		Montage->AddAnimCompositeSection(FName(TEXT("Default")), 0.0f);
		if (Params.BlendIn.IsSet()) { Montage->BlendIn.SetBlendTime(Params.BlendIn.GetValue()); }
		if (Params.BlendOut.IsSet()) { Montage->BlendOut.SetBlendTime(Params.BlendOut.GetValue()); }
		Montage->PostEditChange();

		FAssetRegistryModule::AssetCreated(Montage);
		Montage->MarkPackageDirty();

		UE_LOG(LogAnimGraphMcp, Log, TEXT("Created AnimMontage %s (animation %s, slot %s, length %.3f)"), *ObjectPath, *Sequence->GetName(), *SlotName.ToString(), Montage->GetPlayLength());
		return Montage;
	}

	// ---- 슬롯 ----------------------------------------------------------------------------------------------------

	bool ParseSlotSpecs(const TSharedRef<FJsonObject>& Params, TArray<FSlotSpec>& Out, FAnimMcpError& OutError)
	{
		const TArray<TSharedPtr<FJsonValue>>* Slots = nullptr;
		if (!Params->TryGetArrayField(TEXT("slots"), Slots) || !Slots || Slots->Num() == 0)
		{
			OutError = FieldError(TEXT("slots"), TEXT("Missing or empty required array parameter 'slots' ([{index?, slot}])"));
			return false;
		}
		for (int32 i = 0; i < Slots->Num(); ++i)
		{
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			FSlotSpec Spec;
			if ((*Slots)[i].IsValid() && (*Slots)[i]->Type == EJson::String)
			{
				// 축약형: 문자열이면 배열 위치가 index
				Spec.Slot = (*Slots)[i]->AsString();
			}
			else if ((*Slots)[i].IsValid() && (*Slots)[i]->TryGetObject(Obj) && Obj)
			{
				(*Obj)->TryGetStringField(TEXT("slot"), Spec.Slot);
				double Index = -1.0;
				if ((*Obj)->TryGetNumberField(TEXT("index"), Index))
				{
					if (Index < 0.0 || !FMath::IsNearlyEqual(Index, FMath::RoundToDouble(Index)))
					{
						OutError = FieldError(FString::Printf(TEXT("slots[%d].index"), i), TEXT("'index' must be a non-negative integer"), TEXT("SLOT_INDEX"));
						return false;
					}
					Spec.Index = static_cast<int32>(Index);
				}
			}
			else
			{
				OutError = FieldError(FString::Printf(TEXT("slots[%d]"), i), TEXT("Each entry must be {index?, slot} or a slot name string"));
				return false;
			}
			if (Spec.Index == INDEX_NONE) { Spec.Index = i; }
			if (Spec.Slot.TrimStartAndEnd().IsEmpty())
			{
				OutError = FieldError(FString::Printf(TEXT("slots[%d].slot"), i), TEXT("'slot' is required"), TEXT("EMPTY_NAME"));
				return false;
			}
			Out.Add(Spec);
		}
		return true;
	}

	bool SetSlots(UAnimMontage* Montage, const TArray<FSlotSpec>& Slots, FAnimMcpContext& Context, FAnimMcpError& OutError, int32& OutChanged)
	{
		check(Montage);
		OutChanged = 0;
		USkeleton* Skeleton = Montage->GetSkeleton();
		if (!Skeleton)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Montage '%s' has no skeleton"), *Montage->GetPathName()));
			return false;
		}

		// 사전 검증 — 전부 통과해야 적용 (하나라도 실패면 무변경)
		TArray<FName> NewNames;
		for (const FSlotAnimationTrack& Track : Montage->SlotAnimTracks) { NewNames.Add(Track.SlotName); }
		TSet<int32> SeenIndex;
		for (int32 i = 0; i < Slots.Num(); ++i)
		{
			const FSlotSpec& Spec = Slots[i];
			const FString Field = FString::Printf(TEXT("slots[%d]"), i);
			if (!Montage->SlotAnimTracks.IsValidIndex(Spec.Index))
			{
				OutError = FieldError(Field + TEXT(".index"), FString::Printf(TEXT("Slot track index %d is out of range (montage has %d track(s))"), Spec.Index, Montage->SlotAnimTracks.Num()), TEXT("SLOT_INDEX"));
				return false;
			}
			if (SeenIndex.Contains(Spec.Index))
			{
				OutError = FieldError(Field + TEXT(".index"), FString::Printf(TEXT("Slot track index %d appears more than once"), Spec.Index), TEXT("DUPLICATE_INDEX"));
				return false;
			}
			SeenIndex.Add(Spec.Index);
			FName SlotName;
			if (!ParseName(Spec.Slot, Field + TEXT(".slot"), SlotName, OutError)) { return false; }
			if (!SkeletonHasSlot(Skeleton, SlotName))
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), Field + TEXT(".slot"));
				Details->SetStringField(TEXT("reason"), TEXT("SLOT_NOT_IN_SKELETON"));
				Details->SetStringField(TEXT("skeleton"), Skeleton->GetPathName());
				Details->SetArrayField(TEXT("slot_groups"), SlotGroupsArray(Skeleton));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Slot '%s' is not registered in skeleton '%s' (register it first with add_skeleton_slot)"), *SlotName.ToString(), *Skeleton->GetPathName()), Details);
				return false;
			}
			NewNames[Spec.Index] = SlotName;
		}
		for (int32 a = 0; a < NewNames.Num(); ++a)
		{
			for (int32 b = a + 1; b < NewNames.Num(); ++b)
			{
				if (NewNames[a] == NewNames[b])
				{
					OutError = FieldError(TEXT("slots"), FString::Printf(TEXT("Slot tracks %d and %d would both be named '%s'"), a, b, *NewNames[a].ToString()), TEXT("DUPLICATE_SLOT"));
					return false;
				}
			}
		}

		for (int32 i = 0; i < NewNames.Num(); ++i)
		{
			if (Montage->SlotAnimTracks[i].SlotName != NewNames[i]) { ++OutChanged; }
		}
		if (OutChanged == 0)
		{
			return true;
		}

		// 적용 — Persona RenameSlotNode 와 같은 순서 (Modify → 대입 → PostEditChange)
		Montage->Modify();
		for (int32 i = 0; i < NewNames.Num(); ++i)
		{
			Montage->SlotAnimTracks[i].SlotName = NewNames[i];
		}
		Montage->PostEditChange();
		Montage->MarkPackageDirty();
		return true;
	}

	// ---- 섹션 ----------------------------------------------------------------------------------------------------

	bool ParseSectionSpecs(const TSharedRef<FJsonObject>& Params, TArray<FSectionSpec>& Out, FAnimMcpError& OutError)
	{
		const TArray<TSharedPtr<FJsonValue>>* Sections = nullptr;
		if (!Params->TryGetArrayField(TEXT("sections"), Sections) || !Sections)
		{
			OutError = FieldError(TEXT("sections"), TEXT("Missing required array parameter 'sections' ([{name, start, next?}])"));
			return false;
		}
		if (Sections->Num() == 0)
		{
			OutError = FieldError(TEXT("sections"), TEXT("'sections' must contain at least one section (a montage cannot play without one)"), TEXT("NO_SECTIONS"));
			return false;
		}
		for (int32 i = 0; i < Sections->Num(); ++i)
		{
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			if (!(*Sections)[i].IsValid() || !(*Sections)[i]->TryGetObject(Obj) || !Obj)
			{
				OutError = FieldError(FString::Printf(TEXT("sections[%d]"), i), TEXT("Each section must be an object {name, start, next?}"));
				return false;
			}
			FSectionSpec Spec;
			(*Obj)->TryGetStringField(TEXT("name"), Spec.Name);
			FName Dummy;
			if (!ParseName(Spec.Name, FString::Printf(TEXT("sections[%d].name"), i), Dummy, OutError)) { return false; }
			Spec.Name = Dummy.ToString();
			double Start = 0.0;
			if (!(*Obj)->TryGetNumberField(TEXT("start"), Start))
			{
				OutError = FieldError(FString::Printf(TEXT("sections[%d].start"), i), TEXT("Section 'start' (seconds) is required"));
				return false;
			}
			Spec.Start = static_cast<float>(Start);
			const TSharedPtr<FJsonValue> NextValue = (*Obj)->TryGetField(TEXT("next"));
			if (NextValue.IsValid() && NextValue->Type == EJson::String)
			{
				Spec.Next = NextValue->AsString().TrimStartAndEnd();
				if (Spec.Next.Equals(TEXT("None"), ESearchCase::IgnoreCase)) { Spec.Next.Reset(); }
			}
			else if (NextValue.IsValid() && NextValue->Type != EJson::Null)
			{
				OutError = FieldError(FString::Printf(TEXT("sections[%d].next"), i), TEXT("Section 'next' must be a section name string or null"));
				return false;
			}
			Out.Add(Spec);
		}
		return true;
	}

	bool SetSections(UAnimMontage* Montage, const TArray<FSectionSpec>& Sections, FAnimMcpContext& Context, FAnimMcpError& OutError, bool& bOutUnchanged)
	{
		check(Montage);
		bOutUnchanged = false;
		const float Length = Montage->GetPlayLength();

		// 사전 검증
		TSet<FString> Names;
		for (int32 i = 0; i < Sections.Num(); ++i)
		{
			const FSectionSpec& S = Sections[i];
			if (Names.Contains(S.Name))
			{
				OutError = FieldError(FString::Printf(TEXT("sections[%d].name"), i), FString::Printf(TEXT("Section name '%s' appears more than once"), *S.Name), TEXT("DUPLICATE_SECTION"));
				return false;
			}
			Names.Add(S.Name);
			if (S.Start < 0.f || S.Start > Length)
			{
				OutError = FieldError(FString::Printf(TEXT("sections[%d].start"), i), FString::Printf(TEXT("Section '%s' start %.4f is outside the montage length [0, %.4f]"), *S.Name, S.Start, Length), TEXT("SECTION_OUT_OF_RANGE"));
				return false;
			}
		}
		for (int32 i = 0; i < Sections.Num(); ++i)
		{
			if (!Sections[i].Next.IsEmpty() && !Names.Contains(Sections[i].Next))
			{
				OutError = FieldError(FString::Printf(TEXT("sections[%d].next"), i), FString::Printf(TEXT("Section '%s' next '%s' is not one of the sections in this request"), *Sections[i].Name, *Sections[i].Next), TEXT("NEXT_NOT_FOUND"));
				return false;
			}
		}

		TArray<FSectionSpec> Sorted = Sections;
		Sorted.StableSort([](const FSectionSpec& A, const FSectionSpec& B) { return A.Start < B.Start; });

		// 현재와 같으면 no-op
		if (Montage->CompositeSections.Num() == Sorted.Num())
		{
			bool bSame = true;
			for (int32 i = 0; i < Sorted.Num() && bSame; ++i)
			{
				const FCompositeSection& Cur = Montage->CompositeSections[i];
				const FName WantNext = Sorted[i].Next.IsEmpty() ? NAME_None : FName(*Sorted[i].Next);
				bSame = Cur.SectionName == FName(*Sorted[i].Name)
					&& FMath::IsNearlyEqual(Cur.GetTime(), Sorted[i].Start, 1e-4f)
					&& Cur.NextSectionName == WantNext;
			}
			if (bSame)
			{
				bOutUnchanged = true;
				return true;
			}
		}

		// 적용 — 전체 교체. AddAnimCompositeSection 은 앞 섹션의 빈 Next 를 자동으로 채우므로(AnimMontage.cpp:353-362) 뒤에서 스펙으로 덮어쓴다
		Montage->Modify();
		const TArray<FCompositeSection> Backup = Montage->CompositeSections;
		Montage->CompositeSections.Empty();
		for (int32 i = 0; i < Sorted.Num(); ++i)
		{
			const int32 Index = Montage->AddAnimCompositeSection(FName(*Sorted[i].Name), Sorted[i].Start);
			if (Index != i)
			{
				Montage->CompositeSections = Backup;
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("AddAnimCompositeSection('%s', %.4f) returned %d (expected %d); sections restored"), *Sorted[i].Name, Sorted[i].Start, Index, i));
				return false;
			}
		}
		for (int32 i = 0; i < Sorted.Num(); ++i)
		{
			Montage->CompositeSections[i].NextSectionName = Sorted[i].Next.IsEmpty() ? NAME_None : FName(*Sorted[i].Next);
		}
		if (Sorted[0].Start > KINDA_SMALL_NUMBER)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("NO_SECTION_AT_ZERO"), FString::Printf(TEXT("First section '%s' starts at %.4f — time before it belongs to no section (the editor would force a section at 0)"), *Sorted[0].Name, Sorted[0].Start));
		}
		Montage->PostEditChange();
		Montage->MarkPackageDirty();
		return true;
	}

	// ---- 스켈레톤 슬롯 --------------------------------------------------------------------------------------------

	TSharedPtr<FJsonObject> AddSkeletonSlot(USkeleton* Skeleton, const FString& Slot, const FString& Group, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(Skeleton);
		FName SlotName;
		if (!ParseName(Slot, TEXT("slot"), SlotName, OutError)) { return nullptr; }
		FName GroupName = FAnimSlotGroup::DefaultGroupName;
		if (!Group.TrimStartAndEnd().IsEmpty())
		{
			if (!ParseName(Group, TEXT("group"), GroupName, OutError)) { return nullptr; }
		}
		// 슬롯·그룹은 같은 이름 공간 (SSkeletonSlotNames.cpp:453)
		if (Skeleton->FindAnimSlotGroup(SlotName) != nullptr)
		{
			OutError = FieldError(TEXT("slot"), FString::Printf(TEXT("'%s' is already a slot GROUP name in skeleton '%s'"), *SlotName.ToString(), *Skeleton->GetPathName()), TEXT("SLOT_IS_GROUP"));
			return nullptr;
		}
		if (Skeleton->ContainsSlotName(GroupName))
		{
			OutError = FieldError(TEXT("group"), FString::Printf(TEXT("'%s' is already a SLOT name in skeleton '%s'"), *GroupName.ToString(), *Skeleton->GetPathName()), TEXT("GROUP_IS_SLOT"));
			return nullptr;
		}

		const bool bExisted = Skeleton->ContainsSlotName(SlotName);
		const FName OldGroup = bExisted ? Skeleton->GetSlotGroupName(SlotName) : NAME_None;
		const bool bGroupExisted = Skeleton->FindAnimSlotGroup(GroupName) != nullptr;
		const bool bUnchanged = bExisted && OldGroup == GroupName;
		if (!bUnchanged)
		{
			Skeleton->Modify();
			if (!bGroupExisted)
			{
				Skeleton->AddSlotGroupName(GroupName);
			}
			Skeleton->SetSlotGroupName(SlotName, GroupName);
			Skeleton->MarkPackageDirty();
			UE_LOG(LogAnimGraphMcp, Log, TEXT("Skeleton %s: slot '%s' -> group '%s'%s"), *Skeleton->GetPathName(), *SlotName.ToString(), *GroupName.ToString(), bExisted ? *FString::Printf(TEXT(" (moved from '%s')"), *OldGroup.ToString()) : TEXT(""));
		}

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("skeleton"), Skeleton->GetPathName());
		Result->SetStringField(TEXT("slot"), SlotName.ToString());
		Result->SetStringField(TEXT("group"), GroupName.ToString());
		Result->SetBoolField(TEXT("added"), !bExisted);
		Result->SetField(TEXT("moved_from"), (bExisted && !bUnchanged) ? AnimMcpJson::StringOrNull(OldGroup.ToString()) : MakeShared<FJsonValueNull>());
		Result->SetBoolField(TEXT("group_created"), !bGroupExisted);
		Result->SetBoolField(TEXT("unchanged"), bUnchanged);
		Result->SetArrayField(TEXT("slot_groups"), SlotGroupsArray(Skeleton));
		return Result;
	}

	// ---- 조회 ----------------------------------------------------------------------------------------------------

	TSharedRef<FJsonObject> DescribeMontage(UAnimMontage* Montage)
	{
		check(Montage);
		const USkeleton* Skeleton = Montage->GetSkeleton();
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("asset_path"), Montage->GetPathName());
		Obj->SetStringField(TEXT("class"), Montage->GetClass()->GetName());
		Obj->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Skeleton));
		Obj->SetNumberField(TEXT("length"), Montage->GetPlayLength());
		Obj->SetNumberField(TEXT("blend_in"), Montage->GetDefaultBlendInTime());
		Obj->SetNumberField(TEXT("blend_out"), Montage->GetDefaultBlendOutTime());
		Obj->SetNumberField(TEXT("blend_out_trigger_time"), Montage->BlendOutTriggerTime);
		Obj->SetField(TEXT("sync_group"), Montage->SyncGroup.IsNone() ? MakeShared<FJsonValueNull>() : AnimMcpJson::StringOrNull(Montage->SyncGroup.ToString()));
		Obj->SetNumberField(TEXT("notify_count"), Montage->Notifies.Num());

		TArray<TSharedPtr<FJsonValue>> Slots;
		for (int32 i = 0; i < Montage->SlotAnimTracks.Num(); ++i)
		{
			const FSlotAnimationTrack& Track = Montage->SlotAnimTracks[i];
			TSharedRef<FJsonObject> T = AnimMcpJson::MakeObject();
			T->SetNumberField(TEXT("index"), i);
			T->SetStringField(TEXT("name"), Track.SlotName.ToString());
			T->SetBoolField(TEXT("in_skeleton"), SkeletonHasSlot(Skeleton, Track.SlotName));
			T->SetStringField(TEXT("group"), Skeleton ? Skeleton->GetSlotGroupName(Track.SlotName).ToString() : FAnimSlotGroup::DefaultGroupName.ToString());
			TArray<TSharedPtr<FJsonValue>> Segments;
			for (const FAnimSegment& Segment : Track.AnimTrack.AnimSegments)
			{
				Segments.Add(MakeShared<FJsonValueObject>(DescribeSegment(Segment)));
			}
			T->SetArrayField(TEXT("segments"), Segments);
			Slots.Add(MakeShared<FJsonValueObject>(T));
		}
		Obj->SetArrayField(TEXT("slots"), Slots);

		TArray<TSharedPtr<FJsonValue>> Sections;
		for (int32 i = 0; i < Montage->CompositeSections.Num(); ++i)
		{
			const FCompositeSection& Section = Montage->CompositeSections[i];
			TSharedRef<FJsonObject> S = AnimMcpJson::MakeObject();
			S->SetNumberField(TEXT("index"), i);
			S->SetStringField(TEXT("name"), Section.SectionName.ToString());
			S->SetNumberField(TEXT("start"), Section.GetTime());
			S->SetNumberField(TEXT("length"), Montage->GetSectionLength(i));
			S->SetField(TEXT("next"), Section.NextSectionName.IsNone() ? MakeShared<FJsonValueNull>() : AnimMcpJson::StringOrNull(Section.NextSectionName.ToString()));
			Sections.Add(MakeShared<FJsonValueObject>(S));
		}
		Obj->SetArrayField(TEXT("sections"), Sections);
		Obj->SetArrayField(TEXT("skeleton_slot_groups"), SlotGroupsArray(Skeleton));
		return Obj;
	}
}
