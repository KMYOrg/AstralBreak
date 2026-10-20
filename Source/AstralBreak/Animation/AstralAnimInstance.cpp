#include "AstralAnimInstance.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Character/Components/AstralCharacterMovementComponent.h"

namespace
{
	float CalculateDirectionAngle(const FVector& Velocity, const FRotator& BaseRotation)
	{
		if (Velocity.IsNearlyZero())
		{
			return 0.0f;
		}

		const FMatrix RotMatrix = FRotationMatrix(BaseRotation);
		const FVector ForwardVector = RotMatrix.GetScaledAxis(EAxis::X);
		const FVector RightVector   = RotMatrix.GetScaledAxis(EAxis::Y);
		const FVector NormalizedVel = Velocity.GetSafeNormal2D();

		const float ForwardCosAngle   = FVector::DotProduct(ForwardVector, NormalizedVel);
		const float ForwardDeltaDegree = FMath::RadiansToDegrees(FMath::Acos(ForwardCosAngle));
		const float RightCosAngle     = FVector::DotProduct(RightVector, NormalizedVel);

		return (RightCosAngle < 0.0f) ? -ForwardDeltaDegree : ForwardDeltaDegree;
	}
}

UAstralAnimInstance::UAstralAnimInstance(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UAstralAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	// Game Thread 전용 객체 캐싱
	OwningPawn = TryGetPawnOwner();
	if (OwningPawn)
	{
		AstralMovementComponent = Cast<UAstralCharacterMovementComponent>(OwningPawn->GetMovementComponent());
		if (UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(OwningPawn))
		{
			InitializeWithAbilitySystem(ASC);
		}
	}
}

void UAstralAnimInstance::InitializeWithAbilitySystem(UAbilitySystemComponent* ASC)
{
	check(ASC);

	BoundASC = ASC;
	GameplayTagPropertyMap.Initialize(this, ASC);
}

void UAstralAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	if (!OwningPawn || !AstralMovementComponent)
	{
		return;
	}

	Snapshot.WorldVelocity     = AstralMovementComponent->Velocity;
	Snapshot.WorldAcceleration = AstralMovementComponent->GetCurrentAcceleration();
	Snapshot.ActorRotation     = OwningPawn->GetActorRotation();
	Snapshot.bIsInAir          = AstralMovementComponent->IsFalling();
	Snapshot.bIsOnGround       = AstralMovementComponent->IsMovingOnGround();
	Snapshot.GroundDistance    = AstralMovementComponent->GetGroundInfo().GroundDistance;
	Snapshot.BaseAimRotation   = OwningPawn->GetBaseAimRotation();

	// 조준 태그 — ASC 는 Mixed 복제라 전 머신이 같은 값을 본다. 결합 전(폰 도착 직후)은 false
	const UAbilitySystemComponent* ASC = BoundASC.Get();
	Snapshot.bAiming = ASC && ASC->HasMatchingGameplayTag(AstralGameplayTags::State_Ranged_Aiming);
}

void UAstralAnimInstance::NativeThreadSafeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeThreadSafeUpdateAnimation(DeltaSeconds);
	
	Speed             = Snapshot.WorldVelocity.Size2D();
	Acceleration      = Snapshot.WorldAcceleration.Size2D();
	bHasMovementInput = Snapshot.WorldAcceleration.SizeSquared() > KINDA_SMALL_NUMBER;
	bIsOnGround       = Snapshot.bIsOnGround;
	bIsInAir          = Snapshot.bIsInAir;
	bIsJumping        = Snapshot.bIsInAir && (Snapshot.WorldVelocity.Z > 0.0f);
	bIsFalling        = Snapshot.bIsInAir && !bIsJumping;
	GroundDistance    = Snapshot.GroundDistance;
	MovementDirection = CalculateDirectionAngle(Snapshot.WorldVelocity, Snapshot.ActorRotation);

	// 조준 각 = 조준 회전 − 몸 회전 (AimOffset 입력). 조준 중엔 몸이 컨트롤러 Yaw 를 따르므로 Yaw 는 0 근처, Pitch 가 주 성분
	const FRotator AimDelta = (Snapshot.BaseAimRotation - Snapshot.ActorRotation).GetNormalized();
	AimYaw    = AimDelta.Yaw;
	AimPitch  = AimDelta.Pitch;
	bIsAiming = Snapshot.bAiming;
}
