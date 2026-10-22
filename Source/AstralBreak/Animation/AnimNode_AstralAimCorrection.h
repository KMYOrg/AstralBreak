#pragma once

#include "CoreMinimal.h"
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "AnimNode_AstralAimCorrection.generated.h"

/** 조준 보정을 나눠 받을 체인 본 하나 */
USTRUCT(BlueprintType)
struct FAstralAimCorrectionBone
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, Category = "AimCorrection")
	FBoneReference Bone;

	/** 보정 몫 — 체인 가중치 합으로 정규화 */
	UPROPERTY(EditAnywhere, Category = "AimCorrection", Meta = (ClampMin = "0.0"))
	float Weight = 1.f;
};

/**
 * 최종 조준 보정 — AimOffset·로코모션·턴 클립이 만든 포즈에서 총열(총구 소켓 +X)이 조준점을 향하도록 남은 각을 척추 체인에 나눠 돌린다
 * (계산은 AstralAimCorrection::Solve). AO 는 각도 입력으로 저작 포즈를 섞을 뿐이라 샘플 사이 보간·Pitch 극단·가까운 표적의 시차가 남는다 — 그 잔차만 절차적으로 없앤다.
 * 베이스 ABP 루트의 RotateRootBone 뒤(최종 컴포넌트 공간)에 둔다: 척추는 두 팔의 공통 조상이라 손·무기·왼손 IK 결과가 강체로 함께 돌고, 무기 계열과 무관하다.
 * 총구·조준점은 UAstralAnimInstance 가 준다 — 총구 = 무기 소켓(장비 매니저 이벤트, 왼손 파지점과 같은 경로), 조준점 = 발사(ResolveShot)와 같은 카메라 조준점
 * (관찰자는 서버가 복제한 그 점 — AAstralCharacter_Hero::ObservedAimTarget).
 * 알파는 bool(조준 중 ∧ 총구 있음)로 켜고 끈다
 */
USTRUCT(BlueprintInternalUseOnly)
struct ASTRALBREAK_API FAnimNode_AstralAimCorrection : public FAnimNode_SkeletalControlBase
{
	GENERATED_BODY()

	/** 조준점 (컴포넌트 공간) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AimCorrection", Meta = (PinShownByDefault))
	FVector AimTarget = FVector::ZeroVector;

	/** 총구 위치 (WeaponBone 공간) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AimCorrection", Meta = (PinShownByDefault))
	FVector MuzzleLocation = FVector::ZeroVector;

	/** 총구 회전 (WeaponBone 공간, +X = 총열) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AimCorrection", Meta = (PinShownByDefault))
	FRotator MuzzleRotation = FRotator::ZeroRotator;

	/** 무기가 붙은 본 — UAstralAnimInstance::WeaponReferenceBone(총구·파지점의 기준 본)과 같아야 한다 */
	UPROPERTY(EditAnywhere, Category = "AimCorrection")
	FBoneReference WeaponBone;

	/** 보정을 나눠 받을 척추 체인 — 뿌리 → 끝 순서, 각각 앞 본과 WeaponBone 의 조상 */
	UPROPERTY(EditAnywhere, Category = "AimCorrection")
	TArray<FAstralAimCorrectionBone> Chain;

	/** 최대 보정각(도) — 이보다 큰 오차(AO 범위 밖으로 몸이 아직 못 따라온 빠른 회전 등)는 이만큼만 줄인다 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "AimCorrection", Meta = (PinHiddenByDefault, ClampMin = "0.0", ClampMax = "90.0"))
	float MaxCorrectionAngle = 30.f;

	/** 시차 수렴 반복 수 — 체인 피벗이 서로 달라 남는 잔차를 정리한다 */
	UPROPERTY(EditAnywhere, Category = "AimCorrection", Meta = (ClampMin = "1", ClampMax = "8"))
	int32 Iterations = 3;

	FAnimNode_AstralAimCorrection();

	//~FAnimNode_Base
	virtual void GatherDebugData(FNodeDebugData& DebugData) override;
	//~End FAnimNode_Base

	//~FAnimNode_SkeletalControlBase
	virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& OutBoneTransforms) override;
	virtual bool IsValidToEvaluate(const USkeleton* Skeleton, const FBoneContainer& RequiredBones) override;
	//~End FAnimNode_SkeletalControlBase

private:
	//~FAnimNode_SkeletalControlBase
	virtual void InitializeBoneReferences(const FBoneContainer& RequiredBones) override;
	//~End FAnimNode_SkeletalControlBase

	/** 체인이 뿌리 → 끝 조상 관계이고 WeaponBone 이 끝의 자손인가 (본 참조 초기화 때 한 번) */
	bool bChainValid = false;

	/** 마지막 평가의 보정 전·후 오차(도) — 디버그 표시 */
	float LastInitialError = 0.f;
	float LastResidualError = 0.f;
};
