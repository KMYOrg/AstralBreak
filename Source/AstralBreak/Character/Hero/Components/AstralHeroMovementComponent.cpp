#include "AstralHeroMovementComponent.h"

UAstralHeroMovementComponent::UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

float UAstralHeroMovementComponent::GetMaxSpeed() const
{
	if (bWantsToSprint && IsMovingOnGround())
	{
		return SprintSpeed;
	}

	return Super::GetMaxSpeed();
}
