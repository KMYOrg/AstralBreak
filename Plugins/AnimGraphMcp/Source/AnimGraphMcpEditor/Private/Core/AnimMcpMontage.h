#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Misc/Optional.h"

class UAnimMontage;
class USkeleton;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 몽타주 콘텐츠 보정 (Phase 7-3) — 기존 Python 파이프라인(Tools/lib/ab_montage.py, 노티파이)이 못 하는 두 가지(슬롯 이름 · 다중 섹션)와
 * 최소형 몽타주 생성, 스켈레톤 슬롯 등록을 C++ 로 메운다.
 *
 * 엔진 경로 (5.7.4 소스):
 *   생성   — UAnimMontageFactory::FactoryCreateNew 재현 (AnimMontageFactory.cpp:72-104): NewObject<UAnimMontage>(ctor 가 DefaultSlot 트랙 1개를
 *            만든다, AnimMontage.cpp:77) → FAnimSegment::SetAnimReference(Seq, true) → SlotAnimTracks[0] 에 추가 → SetCompositeLength → UpdateCommonTargetFrameRate
 *            → SetSkeleton → 시작 섹션 "Default"@0 (EnsureStartingSection, :116-136). 팩토리 자체는 ConfigureProperties 가 피커 창을 띄우므로 쓰지 않는다.
 *   슬롯   — SlotAnimTracks[i].SlotName 직접 대입 + PostEditChange (Persona SAnimMontagePanel::RenameSlotNode, SAnimMontagePanel.cpp:470-486).
 *            Persona 는 스켈레톤에 없는 이름을 RegisterSlotNode 로 자동 등록하지만, 여기서는 **거부**한다(SLOT_NOT_IN_SKELETON) — 몽타주 편집이 공유
 *            애셋(스켈레톤)을 몰래 더티로 만들지 않도록. 등록은 add_skeleton_slot 으로만. 노티파이·섹션은 슬롯 **인덱스**로 링크되므로 이름 변경에 영향 없음.
 *   섹션   — 전체 교체: CompositeSections 비우고 AddAnimCompositeSection(이름, 시작) (AnimMontage.cpp:325-365; 앞 섹션의 빈 Next 를 자동으로 채우므로
 *            뒤에서 스펙의 next 로 덮어쓴다) → NextSectionName 직접 대입 (SAnimMontageSectionsPanel.cpp:548-560) → PostEditChange. 같은 스펙 재적용은 no-op.
 *   스켈레톤 — USkeleton::AddSlotGroupName · SetSlotGroupName · ContainsSlotName (Skeleton.cpp:1575-1638). SetSlotGroupName 은 그룹이 없으면 만들고
 *            다른 그룹에 있던 슬롯은 옮긴다. 슬롯 이름과 그룹 이름은 같은 이름 공간이라 교차 충돌을 거부한다(Persona SSkeletonSlotNames.cpp:453).
 */
namespace AnimMcpMontage
{
	struct FCreateParams
	{
		/** "/Game/A/AM_X" 또는 "/Game/A/AM_X.AM_X" */
		FString AssetPath;
		/** UAnimSequence 경로 — 몽타주의 스켈레톤은 이 시퀀스의 스켈레톤 */
		FString AnimationPath;
		/** 첫 트랙의 슬롯 이름 (기본 DefaultSlot). 스켈레톤에 등록돼 있어야 한다 */
		FString SlotName;
		FString PreviewMeshPath;
		TOptional<float> BlendIn;
		TOptional<float> BlendOut;
		bool bOverwrite = false;
	};

	/** 요청 JSON → 파라미터. 형식 오류는 BAD_REQUEST (details.field) */
	bool ParseCreateParams(const TSharedRef<FJsonObject>& Params, FCreateParams& Out, FAnimMcpError& OutError);

	UAnimMontage* CreateMontage(const FCreateParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);

	struct FSlotSpec
	{
		/** 생략(-1) 이면 배열 위치 */
		int32 Index = INDEX_NONE;
		FString Slot;
	};

	bool ParseSlotSpecs(const TSharedRef<FJsonObject>& Params, TArray<FSlotSpec>& Out, FAnimMcpError& OutError);

	/** 전부 검증 뒤 한 번에 적용. OutChanged = 실제로 바뀐 트랙 수 (0 이면 no-op, 더티 아님) */
	bool SetSlots(UAnimMontage* Montage, const TArray<FSlotSpec>& Slots, FAnimMcpContext& Context, FAnimMcpError& OutError, int32& OutChanged);

	struct FSectionSpec
	{
		FString Name;
		float Start = 0.f;
		/** 비어 있으면 NAME_None (섹션 끝에서 정지). 자기 이름이면 루프 */
		FString Next;
	};

	bool ParseSectionSpecs(const TSharedRef<FJsonObject>& Params, TArray<FSectionSpec>& Out, FAnimMcpError& OutError);

	/** 섹션 목록 전체 교체 (시작 시간 순으로 정렬). 현재와 같으면 bOutUnchanged=true 로 no-op */
	bool SetSections(UAnimMontage* Montage, const TArray<FSectionSpec>& Sections, FAnimMcpContext& Context, FAnimMcpError& OutError, bool& bOutUnchanged);

	/**
	 * 스켈레톤에 슬롯 등록 (그룹 생략 = DefaultGroup). 이미 그 그룹에 있으면 unchanged.
	 * 응답: {skeleton, slot, group, added, moved_from, group_created, unchanged, slot_groups[]}
	 */
	TSharedPtr<FJsonObject> AddSkeletonSlot(USkeleton* Skeleton, const FString& Slot, const FString& Group, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** DefaultSlot 은 항상 유효 (엔진 기본 슬롯) */
	bool SkeletonHasSlot(const USkeleton* Skeleton, FName Slot);

	/** [{group, slots[]}] */
	TArray<TSharedPtr<FJsonValue>> SlotGroupsArray(const USkeleton* Skeleton);

	/**
	 * 조회 — asset_path, class, skeleton, length, blend_in, blend_out, blend_out_trigger_time, sync_group, notify_count,
	 * slots[{index, name, in_skeleton, group, segments[{animation, start, length, anim_start, anim_end, play_rate, loop_count}]}],
	 * sections[{index, name, start, length, next}], skeleton_slot_groups[]
	 */
	TSharedRef<FJsonObject> DescribeMontage(UAnimMontage* Montage);

	/** UEditorAssetSubsystem::SaveLoadedAsset(강제). 실패는 진단 SAVE_FAILED */
	bool SaveAsset(UObject* Asset, FAnimMcpContext& Context);
}
