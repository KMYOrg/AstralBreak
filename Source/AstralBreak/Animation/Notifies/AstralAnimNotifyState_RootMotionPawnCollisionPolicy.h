#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotifyState.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "AstralAnimNotifyState_RootMotionPawnCollisionPolicy.generated.h"

/**
 * 루트모션 폰 충돌 정책 밴드 — 이 구간 동안 소유 캐릭터 CMC의 정책을 덮는다
 * Branching Point(bIsNativeBranchingPoint)라 몽타주 Advance 안에서 즉시 Begin/End가 불린다 — TickCharacterPose가
 * PerformMovement 안(루트모션 중)이라 그 프레임의 SlideAlongSurface보다 먼저 정책이 바뀐다. 일반(큐잉) 노티파이면 한 프레임 늦는다
 * 인터럽트 시 End는 FAnimMontageInstance::Terminate가 보장(단 ValidateInstanceAfterNotifyState 실패 시 누락 가능 → CMC의 InstanceID 필터가 안전망)
 */
UCLASS(Meta = (DisplayName = "Astral Root Motion Pawn Collision Policy"))
class ASTRALBREAK_API UAstralAnimNotifyState_RootMotionPawnCollisionPolicy : public UAnimNotifyState
{
	GENERATED_BODY()

public:
	UAstralAnimNotifyState_RootMotionPawnCollisionPolicy(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	virtual void BranchingPointNotifyBegin(FBranchingPointNotifyPayload& BranchingPointPayload) override;
	virtual void BranchingPointNotifyEnd(FBranchingPointNotifyPayload& BranchingPointPayload) override;

	/** 애셋 검증용 */
	EAstralRootMotionPawnCollisionPolicy GetPolicy() const { return Policy; }

protected:
	static UAstralCharacterMovementComponent* FindMovementComponent(const FBranchingPointNotifyPayload& Payload);

protected:
	/** 이 구간의 정책. 밴드 안의 명시적 Normal은 바깥 override를 잠시 덮는다 */
	UPROPERTY(EditAnywhere, Category = "Astral|PawnCollision")
	EAstralRootMotionPawnCollisionPolicy Policy = EAstralRootMotionPawnCollisionPolicy::StopOnHit;
};
