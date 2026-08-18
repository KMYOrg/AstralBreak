#include "AstralAnimInstance.h"

#include "AbilitySystemGlobals.h"
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
}
