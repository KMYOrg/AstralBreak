#include "AstralHeroMovementComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "GameFramework/Character.h"

//////////////////////////////////////////////////////////////////////////
// UAstralHeroMovementComponent

UAstralHeroMovementComponent::UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

float UAstralHeroMovementComponent::GetMaxSpeed() const
{
	// 베이스가 이미 MoveSpeedMultiplier를 곱해 주므로 여기선 질주 배율만 얹는다 — 곱셈 체인 합성
	if (bWantsToSprint && CanActuallySprint())
	{
		return Super::GetMaxSpeed() * SprintSpeedMultiplier;
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

void UAstralHeroMovementComponent::PerformMovement(float DeltaSeconds)
{
	// 예측 클라·재실행·서버는 각자의 경로가 move 시작 전에 설치한다 (커밋 3). 설치된 것이 없으면 이 move의 라이브 샘플을 만든다
	if (!bHasCurrentMoveInputFacing)
	{
		InstallCurrentMoveInputFacing(MakeLiveInputFacingSample());
	}

	Super::PerformMovement(DeltaSeconds);

	// 샘플 수명은 move 하나 — 다음 평가(다른 move·시뮬레이션)에 새지 않게 항상 해제
	ClearCurrentMoveInputFacing();
}

bool UAstralHeroMovementComponent::GetInputFacingSampleForCurrentMove(FAstralInputFacingSample& OutSample) const
{
	if (!bHasCurrentMoveInputFacing)
	{
		return false;
	}
	OutSample = CurrentMoveInputFacing;
	return true;
}

void UAstralHeroMovementComponent::InstallCurrentMoveInputFacing(const FAstralInputFacingSample& Sample)
{
	CurrentMoveInputFacing = Sample;
	bHasCurrentMoveInputFacing = true;
}

void UAstralHeroMovementComponent::ClearCurrentMoveInputFacing()
{
	CurrentMoveInputFacing = FAstralInputFacingSample();
	bHasCurrentMoveInputFacing = false;
}

FAstralInputFacingSample UAstralHeroMovementComponent::MakeLiveInputFacingSample() const
{
	if (!CharacterOwner)
	{
		return FAstralInputFacingSample();
	}

	// CMC 틱이 ConsumeInputVector로 소비한 이번 틱의 이동 입력 — 원격 폰의 서버 인스턴스·시뮬 프록시는 입력을 더하지 않으므로 0
	const FVector WorldInput = CharacterOwner->GetLastMovementInputVector();
	return AstralInputFacing::MakeSample(WorldInput, CharacterOwner->GetActorRotation().Yaw, IsLocalLockOnActive());
}

bool UAstralHeroMovementComponent::IsLocalLockOnActive() const
{
	if (!CharacterOwner || !CharacterOwner->IsLocallyControlled())
	{
		return false;
	}

	// 록온 우선 — 하드 락 중에는 입력 회전을 요청하지 않는다 (기존 Facing 소유권 슬롯은 커밋 4에서 합류)
	const UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(CharacterOwner);
	return Targeting && Targeting->GetMode() == EAstralTargetingMode::HardLocked;
}

//////////////////////////////////////////////////////////////////////////
// FAstralSavedMove_Hero

FAstralSavedMove_Hero::FAstralSavedMove_Hero()
	: bSavedWantsToSprint(0)
	, SavedPawnCollisionPolicy(EAstralRootMotionPawnCollisionPolicy::Normal)
{
}

void FAstralSavedMove_Hero::Clear()
{
	Super::Clear();
	bSavedWantsToSprint = 0;
	SavedPawnCollisionPolicy = EAstralRootMotionPawnCollisionPolicy::Normal;
}

void FAstralSavedMove_Hero::PostUpdate(ACharacter* C, EPostUpdateMode PostUpdateMode)
{
	Super::PostUpdate(C, PostUpdateMode);

	if (PostUpdateMode == PostUpdate_Record)
	{
		if (const UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(C))
		{
			SavedPawnCollisionPolicy = HeroMC->GetAuthoredPawnCollisionPolicy();
		}
	}
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
		// 리플레이(bClientUpdating) 창에서만 읽힌다 — 루프가 끝나면 저작 정책으로 자동 복귀
		HeroMC->SetReplayPawnCollisionPolicy(SavedPawnCollisionPolicy);
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
