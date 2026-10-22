#include "AnimNode_AstralAimCorrection.h"

#include "Animation/AnimInstanceProxy.h"
#include "Animation/AstralAimCorrection.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AnimNode_AstralAimCorrection)

FAnimNode_AstralAimCorrection::FAnimNode_AstralAimCorrection()
{
	// 기본 = UE5 마네킹 계열 척추 위쪽 3본(골반·하체는 로코모션·턴 클립 몫) · 무기 본 hand_r. 위로 갈수록 몫이 크다 — 가슴이 주로 돌고 허리는 덜
	WeaponBone.BoneName = TEXT("hand_r");
	const TPair<const TCHAR*, float> Defaults[] = { { TEXT("spine_03"), 0.25f }, { TEXT("spine_04"), 0.35f }, { TEXT("spine_05"), 0.4f } };
	for (const TPair<const TCHAR*, float>& Default : Defaults)
	{
		FAstralAimCorrectionBone& Link = Chain.AddDefaulted_GetRef();
		Link.Bone.BoneName = Default.Key;
		Link.Weight = Default.Value;
	}
}

void FAnimNode_AstralAimCorrection::GatherDebugData(FNodeDebugData& DebugData)
{
	FString DebugLine = DebugData.GetNodeName(this);
	DebugLine += FString::Printf(TEXT("(Alpha: %.2f, Error: %.2f -> %.2f deg)"), ActualAlpha, LastInitialError, LastResidualError);
	DebugData.AddDebugItem(DebugLine);
	ComponentPose.GatherDebugData(DebugData);
}

void FAnimNode_AstralAimCorrection::InitializeBoneReferences(const FBoneContainer& RequiredBones)
{
	WeaponBone.Initialize(RequiredBones);
	for (FAstralAimCorrectionBone& Link : Chain)
	{
		Link.Bone.Initialize(RequiredBones);
	}

	// 순서·조상 관계 — 어긋나면 평가하지 않는다(뒤 본의 결과가 앞 본 회전을 덮어 총열이 엉뚱하게 돈다)
	bChainValid = Chain.Num() > 0 && WeaponBone.IsValidToEvaluate(RequiredBones);
	for (int32 Index = 0; bChainValid && Index < Chain.Num(); ++Index)
	{
		const FBoneReference& Bone = Chain[Index].Bone;
		const FBoneReference& Next = Chain.IsValidIndex(Index + 1) ? Chain[Index + 1].Bone : WeaponBone;
		bChainValid = Bone.IsValidToEvaluate(RequiredBones)
			&& RequiredBones.BoneIsChildOf(Next.GetCompactPoseIndex(RequiredBones), Bone.GetCompactPoseIndex(RequiredBones));
	}
}

bool FAnimNode_AstralAimCorrection::IsValidToEvaluate(const USkeleton* Skeleton, const FBoneContainer& RequiredBones)
{
	return bChainValid;
}

void FAnimNode_AstralAimCorrection::EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& OutBoneTransforms)
{
	const FBoneContainer& BoneContainer = Output.Pose.GetPose().GetBoneContainer();

	TArray<FTransform, TInlineAllocator<4>> ChainTransforms;
	TArray<float, TInlineAllocator<4>> Weights;
	for (const FAstralAimCorrectionBone& Link : Chain)
	{
		ChainTransforms.Add(Output.Pose.GetComponentSpaceTransform(Link.Bone.GetCompactPoseIndex(BoneContainer)));
		Weights.Add(Link.Weight);
	}

	FAstralAimCorrectionInput Input;
	Input.Chain = ChainTransforms;
	Input.Weights = Weights;
	Input.WeaponBone = Output.Pose.GetComponentSpaceTransform(WeaponBone.GetCompactPoseIndex(BoneContainer));
	Input.MuzzleInWeaponBone = FTransform(MuzzleRotation, MuzzleLocation);
	Input.Target = AimTarget;
	Input.MaxAngleDegrees = MaxCorrectionAngle;
	Input.Iterations = Iterations;

	const FAstralAimCorrectionResult Result = AstralAimCorrection::Solve(Input);
	if (!Result.bValid)
	{
		return;
	}
	LastInitialError = Result.InitialErrorDegrees;
	LastResidualError = Result.ResidualErrorDegrees;

	for (int32 Index = 0; Index < Chain.Num(); ++Index)
	{
		OutBoneTransforms.Add(FBoneTransform(Chain[Index].Bone.GetCompactPoseIndex(BoneContainer), Result.Chain[Index]));
	}
	// 부모 → 자식 순서 (LocalBlendCSBoneTransforms 요구) — 체인 검증으로 이미 그 순서지만 계약을 명시
	OutBoneTransforms.Sort(FCompareBoneTransformIndex());
}
