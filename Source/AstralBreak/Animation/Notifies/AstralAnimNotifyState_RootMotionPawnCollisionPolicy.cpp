#include "AstralAnimNotifyState_RootMotionPawnCollisionPolicy.h"

#include "Animation/AnimNotifies/AnimNotify.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"

UAstralAnimNotifyState_RootMotionPawnCollisionPolicy::UAstralAnimNotifyState_RootMotionPawnCollisionPolicy(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
#if WITH_EDITORONLY_DATA
	bShouldFireInEditor = false;
#endif
	// 몽타주 Advance 안에서 즉시 처리 — 그 프레임의 이동(SlideAlongSurface)보다 먼저 정책이 걸린다
	bIsNativeBranchingPoint = true;
}

UAstralCharacterMovementComponent* UAstralAnimNotifyState_RootMotionPawnCollisionPolicy::FindMovementComponent(const FBranchingPointNotifyPayload& Payload)
{
	const AActor* Owner = Payload.SkelMeshComponent ? Payload.SkelMeshComponent->GetOwner() : nullptr;
	const ACharacter* Character = Cast<ACharacter>(Owner);
	return Character ? Cast<UAstralCharacterMovementComponent>(Character->GetCharacterMovement()) : nullptr;
}

void UAstralAnimNotifyState_RootMotionPawnCollisionPolicy::BranchingPointNotifyBegin(FBranchingPointNotifyPayload& BranchingPointPayload)
{
	Super::BranchingPointNotifyBegin(BranchingPointPayload);

	if (UAstralCharacterMovementComponent* MovementComponent = FindMovementComponent(BranchingPointPayload))
	{
		FAstralPawnCollisionPolicySource Source;
		Source.NotifyState = this;
		Source.MontageInstanceID = BranchingPointPayload.MontageInstanceID;
		MovementComponent->PushOrUpdatePawnCollisionPolicy(Source, Policy);
	}
}

void UAstralAnimNotifyState_RootMotionPawnCollisionPolicy::BranchingPointNotifyEnd(FBranchingPointNotifyPayload& BranchingPointPayload)
{
	Super::BranchingPointNotifyEnd(BranchingPointPayload);

	if (UAstralCharacterMovementComponent* MovementComponent = FindMovementComponent(BranchingPointPayload))
	{
		FAstralPawnCollisionPolicySource Source;
		Source.NotifyState = this;
		Source.MontageInstanceID = BranchingPointPayload.MontageInstanceID;
		MovementComponent->RemovePawnCollisionPolicy(Source);
	}
}
