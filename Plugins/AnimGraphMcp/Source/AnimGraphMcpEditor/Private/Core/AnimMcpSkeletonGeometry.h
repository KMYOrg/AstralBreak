#pragma once

#include "CoreMinimal.h"

class UIKRigDefinition;
class USkeletalMesh;
struct FReferenceSkeleton;

/**
 * 이름 없이 기준 포즈 기하로 몸을 읽는 공통부 — 팔-몸통 관통(AnimMcpBodyClearance) · 손가락 체인 제안 · 손가락 검증(AnimMcpFingerChains)이 같이 쓴다.
 *
 *   체인 원천 — 인자 직접 지정(호출자) > IK Rig 의 리타깃 체인 > 메시 자동 캐릭터라이즈(템플릿이 맞을 때만 체인이 생긴다).
 *   거울 짝 — 뼈 2개 이상 · 같은 수인 체인 쌍이 두 시작 관절의 수직이등분면에 비춰 본마다 겹치고(허용 = 시작 거리 × 5%) 좌우축이 수평.
 *   팔 · 다리 — 가장 뿌리 쪽 거울 짝 중 끝이 가장 낮은 짝 = 다리, 나머지 중 다리 시작보다 높고 자손이 가장 많은 짝 = 팔.
 *   정면 — 발 영역(바닥 + 키 × 15%)에 양 끝이 있는 부모 → 자식 선분의 수평 벡터 합(anim_gen bvh.facing 과 같은 규칙, 지침서 §10).
 */
namespace AnimMcpSkeletonGeometry
{
	/** 구간이 이보다 짧으면(cm) 방향이 없다 */
	constexpr double MinSegmentCm = 0.5;
	/** 거울 짝 판정 허용 오차 = 두 시작 관절 거리 × 이 비율 (AnimMcpRetargetPoseAlign 과 같은 값) */
	constexpr double MirrorToleranceRatio = 0.05;

	/** 기준 스켈레톤 계층 · 기준 포즈 전역 변환 (부모가 자식보다 앞) */
	struct FTree
	{
		TArray<int32> Parents;
		TArray<FTransform> Global;
		/** 자손 수 · 아래로 가장 긴 경로의 마디 수(자신 포함) */
		TArray<int32> Descendants;
		TArray<int32> Height;

		void Init(const FReferenceSkeleton& Ref);
		int32 Num() const { return Parents.Num(); }
		FVector Pos(int32 Bone) const { return Global[Bone].GetLocation(); }
		bool IsAncestor(int32 Ancestor, int32 Bone) const;
		bool IsSelfOrAncestor(int32 Ancestor, int32 Bone) const { return Ancestor == Bone || IsAncestor(Ancestor, Bone); }
		/** 자손이 가장 많은 자식 — 위팔 아래 팔꿈치(트위스트는 잎) */
		int32 LargestChild(int32 Bone) const;
		TArray<int32> Children(int32 Bone) const;
	};

	/** Start → End 본 번호 (End 가 Start 의 자손이 아니면 빈 배열) */
	TArray<int32> ChainBones(const FReferenceSkeleton& Ref, const FTree& Tree, FName Start, FName End);

	/** A 의 본마다 두 시작 관절의 수직이등분면에 비춘 자리가 B 의 같은 번호 본과 겹치고, 좌우축이 수평(위아래로 쌓인 체인끼리는 짝이 아니다) */
	bool IsMirror(const TArray<int32>& A, const TArray<int32>& B, const FTree& Tree);

	/**
	 * 가장 뿌리 쪽 거울 짝들 — 다른 짝의 체인 본을 조상으로 둔 짝(손가락 · 발가락)은 뺀다. 다리 = 체인 끝이 가장 낮은 짝,
	 * 팔 = 나머지 중 시작이 다리 시작보다 높고 자손이 가장 많은 짝(손 · 손가락을 품는다). 다리가 없으면 자손이 가장 많은 짝이 팔
	 */
	void PickLimbs(const TArray<TArray<int32>>& Chains, const FTree& Tree, int32& OutArmA, int32& OutArmB, int32& OutLegA, int32& OutLegB);

	struct FNamedChain
	{
		FName Name;
		TArray<int32> Bones;
	};

	struct FChainSource
	{
		TArray<FNamedChain> Chains;
		FName Pelvis;
		/** ik_rig | template | characterize | none */
		FString From;
	};

	/** IK Rig 이 있으면 그 리타깃 체인, 없으면 메시 자동 캐릭터라이즈(템플릿이 맞지 않으면 체인 0개). 본이 없는 체인은 뺀다 */
	FChainSource ResolveChains(USkeletalMesh* Mesh, const UIKRigDefinition* Rig, const FReferenceSkeleton& Ref, const FTree& Tree);

	/** 기준 포즈 바닥 · 꼭대기 높이 — 선분 양 끝 높이의 p5 ~ p95 폭보다 더 떨어진 외톨이 본은 뺀다(anim_gen bvh._vertical_range). 본이 없으면 false */
	bool VerticalRange(const FTree& Tree, double& OutFloor, double& OutTop);

	/** 기준 포즈 정면(수평 단위 벡터) — 발 영역 수평 벡터 합. 발 영역 선분이 없거나 합이 0 이면 false */
	bool FeetFacing(const FTree& Tree, FVector& OutFacing);
}
