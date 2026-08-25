#include "AstralCharacterMovementComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/Character.h"
#include "NativeGameplayTags.h"

namespace AstralCharacter
{
	static float GroundTraceDistance = 100000.0f;
}

UAstralCharacterMovementComponent::UAstralCharacterMovementComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UAstralCharacterMovementComponent::InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC)
{
	if (BoundASC == InASC)
	{
		return;
	}

	UninitializeFromAbilitySystem();

	BoundASC = InASC;
	if (BoundASC)
	{
		OnAbilitySystemBound();
	}
}

void UAstralCharacterMovementComponent::UninitializeFromAbilitySystem()
{
	if (!BoundASC)
	{
		return;
	}

	OnAbilitySystemUnbound();
	BoundASC = nullptr;
}

void UAstralCharacterMovementComponent::OnUnregister()
{
	// 폰의 해제 경로가 먼저 처리했으면 no-op
	UninitializeFromAbilitySystem();

	Super::OnUnregister();
}

float UAstralCharacterMovementComponent::GetMaxSpeed() const
{
	return Super::GetMaxSpeed() * CachedMoveSpeedMultiplier;
}

void UAstralCharacterMovementComponent::OnAbilitySystemBound()
{
	MoveSpeedMultiplierChangedHandle = BoundASC->GetGameplayAttributeValueChangeDelegate(UAstralCombatSet::GetMoveSpeedMultiplierAttribute())
		.AddUObject(this, &ThisClass::HandleMoveSpeedMultiplierChanged);
	
	bool bFound = false;
	const float Multiplier = BoundASC->GetGameplayAttributeValue(UAstralCombatSet::GetMoveSpeedMultiplierAttribute(), bFound);
	CachedMoveSpeedMultiplier = bFound ? Multiplier : 1.0f;
}

void UAstralCharacterMovementComponent::OnAbilitySystemUnbound()
{
	if (MoveSpeedMultiplierChangedHandle.IsValid())
	{
		BoundASC->GetGameplayAttributeValueChangeDelegate(UAstralCombatSet::GetMoveSpeedMultiplierAttribute()).Remove(MoveSpeedMultiplierChangedHandle);
		MoveSpeedMultiplierChangedHandle.Reset();
	}

	CachedMoveSpeedMultiplier = 1.0f;
}

void UAstralCharacterMovementComponent::HandleMoveSpeedMultiplierChanged(const FOnAttributeChangeData& Data)
{
	CachedMoveSpeedMultiplier = Data.NewValue;
}

const FAstralCharacterGroundInfo& UAstralCharacterMovementComponent::GetGroundInfo()
{
	if (!CharacterOwner || (GFrameCounter == CachedGroundInfo.LastUpdateFrame))
	{
		return CachedGroundInfo;
	}

	if (MovementMode == MOVE_Walking)
	{
		CachedGroundInfo.GroundHitResult = CurrentFloor.HitResult;
		CachedGroundInfo.GroundDistance = 0.0f;
	}
	else
	{
		const UCapsuleComponent* CapsuleComp = CharacterOwner->GetCapsuleComponent();
		check(CapsuleComp);

		const float CapsuleHalfHeight = CapsuleComp->GetUnscaledCapsuleHalfHeight();
		const ECollisionChannel CollisionChannel = (UpdatedComponent ? UpdatedComponent->GetCollisionObjectType() : ECC_Pawn);
		const FVector TraceStart(GetActorLocation());
		const FVector TraceEnd(TraceStart.X, TraceStart.Y, (TraceStart.Z - AstralCharacter::GroundTraceDistance - CapsuleHalfHeight));

		FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(AstralCharacterMovementComponent_GetGroundInfo), false, CharacterOwner);
		FCollisionResponseParams ResponseParam;
		InitCollisionParams(QueryParams, ResponseParam);

		FHitResult HitResult;
		GetWorld()->LineTraceSingleByChannel(HitResult, TraceStart, TraceEnd, CollisionChannel, QueryParams, ResponseParam);

		CachedGroundInfo.GroundHitResult = HitResult;
		CachedGroundInfo.GroundDistance = AstralCharacter::GroundTraceDistance;

		if (MovementMode == MOVE_NavWalking)
		{
			CachedGroundInfo.GroundDistance = 0.0f;
		}
		else if (HitResult.bBlockingHit)
		{
			CachedGroundInfo.GroundDistance = FMath::Max((HitResult.Distance - CapsuleHalfHeight), 0.0f);
		}
	}

	CachedGroundInfo.LastUpdateFrame = GFrameCounter;

	return CachedGroundInfo;
}
