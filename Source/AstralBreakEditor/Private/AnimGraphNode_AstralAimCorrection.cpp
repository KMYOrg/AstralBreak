#include "AnimGraphNode_AstralAimCorrection.h"

#include "Animation/Skeleton.h"
#include "Kismet2/CompilerResultsLog.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AnimGraphNode_AstralAimCorrection)

#define LOCTEXT_NAMESPACE "AstralAimCorrection"

FText UAnimGraphNode_AstralAimCorrection::GetNodeTitle(ENodeTitleType::Type TitleType) const
{
	return GetControllerDescription();
}

FText UAnimGraphNode_AstralAimCorrection::GetTooltipText() const
{
	return LOCTEXT("Tooltip", "총열(총구 +X)이 조준점을 향하도록 AimOffset 이 남긴 각을 척추 체인에 나눠 돌린다. 베이스 루트의 RotateRootBone 뒤(최종 컴포넌트 공간)에 둔다.");
}

FText UAnimGraphNode_AstralAimCorrection::GetControllerDescription() const
{
	return LOCTEXT("Title", "Astral Aim Correction");
}

void UAnimGraphNode_AstralAimCorrection::ValidateAnimNodeDuringCompilation(USkeleton* ForSkeleton, FCompilerResultsLog& MessageLog)
{
	// 스켈레톤이 아직 로드 중이면(가상 본 판정 불가) 건너뛴다 — 엔진 ModifyBone 노드와 같은 처리
	if (ForSkeleton && !ForSkeleton->HasAnyFlags(RF_NeedPostLoad))
	{
		const FReferenceSkeleton& RefSkeleton = ForSkeleton->GetReferenceSkeleton();
		const int32 WeaponIndex = RefSkeleton.FindBoneIndex(Node.WeaponBone.BoneName);
		if (WeaponIndex == INDEX_NONE)
		{
			MessageLog.Warning(*FText::Format(LOCTEXT("NoWeaponBone", "@@ - 무기 본 {0} 이 스켈레톤에 없다"), FText::FromName(Node.WeaponBone.BoneName)).ToString(), this);
		}
		if (Node.Chain.Num() == 0)
		{
			MessageLog.Warning(*LOCTEXT("EmptyChain", "@@ - 보정 체인이 비어 있다").ToString(), this);
		}

		// 뿌리 → 끝 순서이고 각 본이 다음 본(끝은 무기 본)의 조상이어야 한다 — 런타임은 어긋나면 평가하지 않는다
		for (int32 Index = 0; Index < Node.Chain.Num(); ++Index)
		{
			const FName BoneName = Node.Chain[Index].Bone.BoneName;
			const int32 BoneIndex = RefSkeleton.FindBoneIndex(BoneName);
			const int32 NextIndex = Node.Chain.IsValidIndex(Index + 1) ? RefSkeleton.FindBoneIndex(Node.Chain[Index + 1].Bone.BoneName) : WeaponIndex;
			if (BoneIndex == INDEX_NONE)
			{
				MessageLog.Warning(*FText::Format(LOCTEXT("NoChainBone", "@@ - 체인 본 {0} 이 스켈레톤에 없다"), FText::FromName(BoneName)).ToString(), this);
			}
			else if (NextIndex != INDEX_NONE && !RefSkeleton.BoneIsChildOf(NextIndex, BoneIndex))
			{
				MessageLog.Warning(*FText::Format(LOCTEXT("ChainOrder", "@@ - 체인 본 {0} 이 다음 본(또는 무기 본)의 조상이 아니다 — 뿌리 → 끝 순서여야 한다"), FText::FromName(BoneName)).ToString(), this);
			}
		}
	}

	Super::ValidateAnimNodeDuringCompilation(ForSkeleton, MessageLog);
}

#undef LOCTEXT_NAMESPACE
