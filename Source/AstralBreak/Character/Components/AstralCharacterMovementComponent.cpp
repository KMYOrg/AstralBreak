#include "AstralCharacterMovementComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "Animation/AnimInstance.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
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

	PolicyOverrides.Reset();

	Super::OnUnregister();
}

float UAstralCharacterMovementComponent::GetMaxSpeed() const
{
	return Super::GetMaxSpeed() * CachedMoveSpeedMultiplier;
}

void UAstralCharacterMovementComponent::PushOrUpdatePawnCollisionPolicy(const FAstralPawnCollisionPolicySource& Source, EAstralRootMotionPawnCollisionPolicy Policy)
{
	// 시뮬 프록시는 SimulateRootMotion 경로라 MoveAlongFloor를 타지 않는다 — 정책을 소비하지 않으므로 배열만 커진다
	if (GetOwnerRole() == ROLE_SimulatedProxy)
	{
		return;
	}

	PruneStalePawnCollisionPolicies();

	for (FAstralPawnCollisionPolicyOverride& Override : PolicyOverrides)
	{
		if (Override.Source == Source)
		{
			Override.Policy = Policy;
			Override.BeginOrder = NextBeginOrder++;
			return;
		}
	}

	FAstralPawnCollisionPolicyOverride& NewOverride = PolicyOverrides.AddDefaulted_GetRef();
	NewOverride.Source = Source;
	NewOverride.Policy = Policy;
	NewOverride.BeginOrder = NextBeginOrder++;
}

void UAstralCharacterMovementComponent::RemovePawnCollisionPolicy(const FAstralPawnCollisionPolicySource& Source)
{
	PruneStalePawnCollisionPolicies();

	PolicyOverrides.RemoveAll([&Source](const FAstralPawnCollisionPolicyOverride& Override)
	{
		return Override.Source == Source;
	});
}

bool UAstralCharacterMovementComponent::IsPawnCollisionPolicySourceAlive(const FAstralPawnCollisionPolicySource& Source) const
{
	const USkeletalMeshComponent* Mesh = CharacterOwner ? CharacterOwner->GetMesh() : nullptr;
	UAnimInstance* AnimInstance = Mesh ? Mesh->GetAnimInstance() : nullptr;
	return AnimInstance && AnimInstance->GetMontageInstanceForID(Source.MontageInstanceID) != nullptr;
}

void UAstralCharacterMovementComponent::PruneStalePawnCollisionPolicies()
{
	PolicyOverrides.RemoveAll([this](const FAstralPawnCollisionPolicyOverride& Override)
	{
		return !IsPawnCollisionPolicySourceAlive(Override.Source);
	});
}

EAstralRootMotionPawnCollisionPolicy UAstralCharacterMovementComponent::GetAuthoredPawnCollisionPolicy() const
{
	const FAstralPawnCollisionPolicyOverride* Latest = nullptr;
	for (const FAstralPawnCollisionPolicyOverride& Override : PolicyOverrides)
	{
		// 죽은 몽타주의 잔여 항목은 선택에서만 제외 — 제거는 비const 시점(Push/Remove)이 한다
		if (!IsPawnCollisionPolicySourceAlive(Override.Source))
		{
			continue;
		}
		if (!Latest || Override.BeginOrder > Latest->BeginOrder)
		{
			Latest = &Override;
		}
	}
	return Latest ? Latest->Policy : EAstralRootMotionPawnCollisionPolicy::Normal;
}

EAstralRootMotionPawnCollisionPolicy UAstralCharacterMovementComponent::GetEffectivePawnCollisionPolicy() const
{
	// 리플레이 중 노티파이는 재발화하지 않아(SimulateAdvance) 저작 배열이 "지금" 값으로 얼어붙는다 — 그 move가 기록한 값을 쓴다
	if (CharacterOwner && CharacterOwner->bClientUpdating)
	{
		return ReplayPawnCollisionPolicy;
	}
	return GetAuthoredPawnCollisionPolicy();
}

bool UAstralCharacterMovementComponent::ShouldStopOnPawn(const FHitResult& Hit) const
{
	if (GetEffectivePawnCollisionPolicy() != EAstralRootMotionPawnCollisionPolicy::StopOnHit)
	{
		return false;
	}

	const APawn* HitPawn = Cast<APawn>(Hit.GetActor());
	if (!HitPawn)
	{
		return false;
	}
	
	// 아군·중립은 Normal(막히고 슬라이드)
	return UAstralCombatStatics::AreHostile(CharacterOwner, HitPawn);
}

float UAstralCharacterMovementComponent::SlideAlongSurface(const FVector& Delta, float Time, const FVector& Normal, FHitResult& Hit, bool bHandleImpact)
{
	if (ShouldStopOnPawn(Hit))
	{
		if (bHandleImpact)
		{
			HandleImpact(Hit, Time, Delta);
		}
		return 0.f;
	}

	return Super::SlideAlongSurface(Delta, Time, Normal, Hit, bHandleImpact);
}

bool UAstralCharacterMovementComponent::CanStepUp(const FHitResult& Hit) const
{
	if (ShouldStopOnPawn(Hit))
	{
		return false;
	}

	return Super::CanStepUp(Hit);
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
