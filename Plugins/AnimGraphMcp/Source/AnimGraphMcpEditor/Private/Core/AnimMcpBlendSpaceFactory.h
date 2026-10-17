#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UBlendSpace;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * BlendSpace 생성 (Phase 6-3) — UBlendSpaceFactory1D/New::FactoryCreateNew 재현 (EditorFactories.cpp:7353-7369, :7427-7443):
 *   NewObject<UBlendSpace[1D]>(Package, Class, Name, RF_Public|RF_Standalone|RF_Transactional) → SetSkeleton → (선택) SetPreviewMesh.
 * 팩토리 자체는 ConfigureProperties 가 스켈레톤 피커 창을 띄우므로 쓰지 않는다.
 *
 * 축(BlendParameters[3], BlendSpace.h:907)은 protected 이고 공개 setter 가 없다. Persona 도 디테일 패널의 프로퍼티 핸들
 * (BlendSpaceDetails.cpp:208-217 — 리플렉션)로 편집하므로, 여기서도 FProperty 로 주소를 얻어 FBlendParameter 의 고정 필드
 * (DisplayName · Min · Max · GridNum · bSnapToGrid · bWrapInput)만 쓴다. 임의 프로퍼티 범용 명령은 아니다.
 *
 * 샘플은 UBlendSpace::AddSample(UAnimSequence*, FVector)(BlendSpace.h:618). AddSample 은 범위 밖 값을 거부하지 않고 축을
 * **늘린다**(ExpandRangeForSample, BlendSpace.cpp:1610-1626) — 요청한 축을 지키기 위해 도구가 먼저 범위·중복·스켈레톤을
 * 검사해 거부한다. 추가 뒤 Persona 와 같은 순서로 ResampleData → ValidateSampleData → PostEditChange (SAnimationBlendSpace.cpp:192-199).
 */
namespace AnimMcpBlendSpaceFactory
{
	struct FAxisParams
	{
		FString Name;
		float Min = 0.f;
		float Max = 100.f;
		int32 GridNum = 4;
		bool bSnapToGrid = false;
		bool bWrapInput = false;
	};

	struct FSampleParams
	{
		FString AnimationPath;
		/** X[, Y] — 1D 는 1개, 2D 는 2개 */
		TArray<double> Value;
	};

	struct FCreateParams
	{
		/** "/Game/A/BS_X" 또는 "/Game/A/BS_X.BS_X" */
		FString AssetPath;
		FString SkeletonPath;
		FString PreviewMeshPath;
		/** 1 → UBlendSpace1D, 2 → UBlendSpace */
		int32 Dimensions = 1;
		/** Dimensions 개 */
		TArray<FAxisParams> Axes;
		TArray<FSampleParams> Samples;
		bool bOverwrite = false;
	};

	/** 요청 JSON → 파라미터. 형식 오류는 BAD_REQUEST (details.field) */
	bool ParseCreateParams(const TSharedRef<FJsonObject>& Params, FCreateParams& Out, FAnimMcpError& OutError);

	UBlendSpace* CreateBlendSpace(const FCreateParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/**
	 * 조회 — asset_path, class, skeleton, dimensions, axes[{index, name, min, max, grid, snap, wrap}],
	 * samples[{index, animation, value[x,y], rate_scale, valid}], sample_count, grid_sample_count, anim_length, loop
	 */
	TSharedRef<FJsonObject> DescribeBlendSpace(UBlendSpace* BlendSpace);
}
