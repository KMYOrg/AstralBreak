#pragma once

#include "CoreMinimal.h"
#include "Curves/RichCurve.h"

/**
 * 애니메이션 키 편집의 계산부 (AI 애니 생성 Phase 2 — Docs/AIAnimation/DevelopmentGuide.md §14 Phase 2 op 표).
 * UObject 를 모른다 — 리그(본 · 부모 · 기준 로컬 포즈)와 키 배열만 다뤄 메모리 단위 테스트(AnimGraphMcp.Generation.Edit)로 검증한다.
 * 애셋 읽기·쓰기·노티파이는 Core/AnimMcpAnimEdit 이 맡는다.
 *
 * 버퍼(FClip) = 출력 프레임레이트의 키 [키][본] 로컬 변환. 키 수 = 프레임 수 + 1, 길이 = 프레임 수 / fps.
 * 시간 인자는 초이고 각 op 직전 버퍼의 타임라인 기준이다. 구간 경계는 가장 가까운 키로 맞추고 실제 값을 FReport 에 남긴다.
 * 키마다 출처(소스 번호 · 소스 시각 · 역재생)를 들고 다녀 노티파이·싱크 마커를 새 타임라인으로 옮길 수 있다.
 * 이음매(seams) — 포즈가 이어 붙거나 재생 속도가 바뀐 시각 — 는 뒤 op 가 타임라인을 바꿀 때 함께 옮겨진다.
 */
namespace AnimMcpAnimEditOps
{
	/** 스켈레톤 계층. 부모 인덱스 < 자기 인덱스(엔진 참조 스켈레톤 규약), 본 0 = 루트 */
	struct FRig
	{
		TArray<FName> Bones;
		TArray<int32> Parents;
		TArray<FTransform> RefLocal;
		/** 기준 포즈의 컴포넌트 공간 회전 — Finalize 가 채운다 (미러 수식) */
		TArray<FQuat> RefComponentRotations;

		void Finalize();
		int32 Find(FName Bone) const { return Bones.IndexOfByKey(Bone); }
		int32 Num() const { return Bones.Num(); }
	};

	/** 읽어 들인 소스 — 원시 키 (리그 본 순서, 트랙 없는 본은 빈 배열 = 기준 포즈) */
	struct FSource
	{
		double FrameRate = 30.0;
		int32 NumKeys = 0;
		TArray<TArray<FTransform>> Tracks;
		TArray<FName> CurveNames;
		TArray<FRichCurve> Curves;
		bool bStep = false;

		double Length() const { return NumKeys > 1 ? (NumKeys - 1) / FrameRate : 0.0; }
	};

	/** 키의 출처 — 노티파이 이동용. Source = INDEX_NONE 이면 합성 키 */
	struct FProvenance
	{
		int32 Source = INDEX_NONE;
		double Time = 0.0;
		bool bReversed = false;
	};

	struct FClip
	{
		double FrameRate = 30.0;
		/** [키][본] 로컬 */
		TArray<TArray<FTransform>> Keys;
		/** 결과에 트랙을 쓸 본 (소스에 트랙이 있었거나 op 가 바꾼 본) */
		TBitArray<> Animated;
		TArray<FName> CurveNames;
		/** [키][커브] */
		TArray<TArray<float>> CurveValues;
		TArray<FProvenance> Provenance;
		/** 이음매 시각 (초) — 검증의 SEAM_JUMP */
		TArray<double> Seams;
		/** 재생 속도 배율의 상한 추정 (retime 의 곱) — 검증의 "물려받은 튐" 기준 */
		double MaxRate = 1.0;

		int32 NumKeys() const { return Keys.Num(); }
		double Length() const { return Keys.Num() > 1 ? (Keys.Num() - 1) / FrameRate : 0.0; }
		int32 TimeToKey(double Time) const { return FMath::Clamp(FMath::RoundToInt32(Time * FrameRate), 0, FMath::Max(0, Keys.Num() - 1)); }
	};

	/** op 하나의 실제 적용 결과 (op 직전 타임라인 기준) */
	struct FReport
	{
		double Start = 0.0;
		double End = 0.0;
		int32 StartKey = 0;
		int32 EndKey = 0;
		double LengthBefore = 0.0;
		double LengthAfter = 0.0;
		FString Note;
		/** concat — 한쪽에만 있어 다른 쪽 구간을 0 으로 채운 커브 */
		TArray<FName> FilledCurves;
	};

	/** 본 하나의 오프셋 (offset_bone) */
	struct FBoneOffset
	{
		int32 Bone = INDEX_NONE;
		FQuat Rotation = FQuat::Identity;
		FVector Translation = FVector::ZeroVector;
	};

	/** 소스 [Start, End] 를 OutRate 의 키로 고른다 (bReverse 면 End → Start). End 는 키 간격에 맞춰 가장 가까운 키로 */
	void Sample(const FRig& Rig, const FSource& Source, int32 SourceIndex, double OutRate, double Start, double End, bool bReverse, FClip& Out);

	// ---- op — 실패하면 false + OutError(사람이 읽을 이유)이고 버퍼는 바뀌지 않는다 ----

	/** [Start, End] 만 남긴다 */
	bool Trim(FClip& Clip, double Start, double End, FReport& Report, FString& OutError);
	/** [Start, End] 를 Rate 배 빠르게(Rate > 0) — 전체를 재샘플 */
	bool Retime(FClip& Clip, double Start, double End, double Rate, FReport& Report, FString& OutError);
	/** At 의 포즈를 Duration 동안 정지 삽입 (At = 끝이면 연장) */
	bool HoldPose(FClip& Clip, double At, double Duration, FReport& Report, FString& OutError);
	/**
	 * Segment(같은 프레임레이트로 고른 키)를 뒤에 붙인다. Blend 초 동안 크로스페이드(0 이면 Segment 첫 키가 현재 끝 키와 겹친다 —
	 * 한 동작을 둘로 자른 두 구간을 이으면 원래대로). bAlignRoot 면 Segment 의 루트를 겹치는 키의 루트 위치·Yaw 에 맞춘다
	 */
	bool Concat(FClip& Clip, FClip Segment, double Blend, bool bAlignRoot, FReport& Report, FString& OutError);
	/** 전체 좌우 반전 — MirrorBones[b] = 짝(짝 없으면 b 자신). 엔진 FAnimationRuntime::MirrorPose 와 같은 수식 */
	void Mirror(const FRig& Rig, FClip& Clip, EAxis::Type Axis, const TArray<int32>& MirrorBones);
	/**
	 * 본 오프셋 — bComponentSpace 면 회전은 컴포넌트 축으로 본 위치를 축으로 돌리고(자식이 따라온다) 이동은 컴포넌트 축,
	 * 아니면 회전은 본 자신의 축, 이동은 부모 공간. 가중치 = [Start, End] 안에서 BlendIn 동안 0 → 1, BlendOut 동안 1 → 0 (smoothstep)
	 */
	bool OffsetBones(const FRig& Rig, FClip& Clip, TArray<FBoneOffset> Targets, bool bComponentSpace, double Start, double End, double BlendIn, double BlendOut, FReport& Report, FString& OutError);
	/** [Start, End] 동안 루트 Yaw 0 → Yaw (bSmooth 면 smoothstep), 이후 유지. 루트 이동 증분도 그 시점의 Yaw 로 돌려 다시 쌓는다 */
	bool RotateRoot(FClip& Clip, double Yaw, double Start, double End, bool bSmooth, FReport& Report, FString& OutError);

	/** 이름 규칙으로 미러 짝 — 짝이 없거나 서로 가리키지 않으면 자기 자신 */
	TArray<int32> MirrorPairs(const FRig& Rig, TFunctionRef<FName(FName)> MirrorName);

	/** 키 하나의 컴포넌트 공간 */
	void ToComponent(const FRig& Rig, const TArray<FTransform>& Local, TArray<FTransform>& OutComponent);

	/** [i] = 키 i → i+1 의 본 평균 회전(°, 컴포넌트 공간) — 이음매 비의 입력 (검증기와 같은 정의) */
	TArray<double> StepMeans(const FRig& Rig, const FClip& Clip);

	/** 루트(본 0) Yaw 의 첫 → 끝 변화 (°, 프레임마다 펼쳐 누적) */
	double RootYawDelta(const FClip& Clip);
}
