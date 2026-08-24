#include "AstralHeroMovementComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "GameFramework/Character.h"

//////////////////////////////////////////////////////////////////////////
// UAstralHeroMovementComponent

UAstralHeroMovementComponent::UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

float UAstralHeroMovementComponent::GetMaxSpeed() const
{
	if (bWantsToSprint && CanActuallySprint())
	{
		return SprintSpeed;
	}

	return Super::GetMaxSpeed();
}

FNetworkPredictionData_Client* UAstralHeroMovementComponent::GetPredictionData_Client() const
{
	if (ClientPredictionData == nullptr)
	{
		UAstralHeroMovementComponent* MutableThis = const_cast<UAstralHeroMovementComponent*>(this);
		MutableThis->ClientPredictionData = new FAstralNetworkPredictionData_Client_Hero(*this);
	}

	return ClientPredictionData;
}

void UAstralHeroMovementComponent::UpdateFromCompressedFlags(uint8 Flags)
{
	Super::UpdateFromCompressedFlags(Flags);

	// 서버에서는 이 함수(매 move)와 Sprint GA의 SetSprinting(활성/종료 시)이 둘 다 이 필드에 쓴다.
	// 원격 클라가 GA 종료 후에도 계속 true를 보내면 의도는 true로 남지만, 승인 게이트가 태그를 보므로 속도는 오르지 않는다
	bWantsToSprint = (Flags & FSavedMove_Character::FLAG_Custom_0) != 0;
}

void UAstralHeroMovementComponent::OnAbilitySystemBound()
{
	Super::OnAbilitySystemBound();

	SprintTagChangedHandle = BoundASC->RegisterGameplayTagEvent(AstralGameplayTags::State_Movement_Sprinting, EGameplayTagEventType::NewOrRemoved)
		.AddUObject(this, &ThisClass::HandleSprintTagChanged);

	bSprintAuthorized = BoundASC->HasMatchingGameplayTag(AstralGameplayTags::State_Movement_Sprinting);
}

void UAstralHeroMovementComponent::OnAbilitySystemUnbound()
{
	if (SprintTagChangedHandle.IsValid())
	{
		BoundASC->RegisterGameplayTagEvent(AstralGameplayTags::State_Movement_Sprinting, EGameplayTagEventType::NewOrRemoved).Remove(SprintTagChangedHandle);
		SprintTagChangedHandle.Reset();
	}

	// 안전한 기본값으로 복귀 — ASC 없는 폰은 질주 불가
	bSprintAuthorized = false;

	Super::OnAbilitySystemUnbound();
}

void UAstralHeroMovementComponent::HandleSprintTagChanged(const FGameplayTag Tag, int32 NewCount)
{
	bSprintAuthorized = (NewCount > 0);
}

//////////////////////////////////////////////////////////////////////////
// FAstralSavedMove_Hero

FAstralSavedMove_Hero::FAstralSavedMove_Hero()
	: bSavedWantsToSprint(0)
{
}

void FAstralSavedMove_Hero::Clear()
{
	Super::Clear();
	bSavedWantsToSprint = 0;
}

uint8 FAstralSavedMove_Hero::GetCompressedFlags() const
{
	uint8 Result = Super::GetCompressedFlags();
	if (bSavedWantsToSprint)
	{
		Result |= FLAG_Custom_0;
	}
	return Result;
}

void FAstralSavedMove_Hero::SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData)
{
	Super::SetMoveFor(C, InDeltaTime, NewAccel, ClientData);

	if (const UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(C))
	{
		bSavedWantsToSprint = HeroMC->WantsToSprint() ? 1 : 0;
	}
}

void FAstralSavedMove_Hero::PrepMoveFor(ACharacter* C)
{
	Super::PrepMoveFor(C);

	if (UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(C))
	{
		HeroMC->SetSprinting(bSavedWantsToSprint != 0);
	}
}

bool FAstralSavedMove_Hero::CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const
{
	const FAstralSavedMove_Hero* NewAstralMove = static_cast<const FAstralSavedMove_Hero*>(NewMove.Get());
	if (NewAstralMove && (bSavedWantsToSprint != NewAstralMove->bSavedWantsToSprint))
	{
		return false;
	}

	return Super::CanCombineWith(NewMove, InCharacter, MaxDelta);
}

UAstralHeroMovementComponent* FAstralSavedMove_Hero::GetHeroMovementComponent(ACharacter* C)
{
	return C ? Cast<UAstralHeroMovementComponent>(C->GetCharacterMovement()) : nullptr;
}

//////////////////////////////////////////////////////////////////////////
// FAstralNetworkPredictionData_Client_Hero

FAstralNetworkPredictionData_Client_Hero::FAstralNetworkPredictionData_Client_Hero(const UCharacterMovementComponent& ClientMovement)
	: Super(ClientMovement)
{
}

FSavedMovePtr FAstralNetworkPredictionData_Client_Hero::AllocateNewMove()
{
	return FSavedMovePtr(new FAstralSavedMove_Hero());
}
