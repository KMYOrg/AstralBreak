#include "AstralHeroMovementComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AstralLogChannels.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "GameFramework/Character.h"

//////////////////////////////////////////////////////////////////////////
// UAstralHeroMovementComponent

UAstralHeroMovementComponent::UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// 확장 이동 패킷 — 기존 필드 뒤에 입력 회전 샘플을 싣는다 (packed movement RPC 경로)
	SetNetworkMoveDataContainer(HeroMoveDataContainer);
}

void UAstralHeroMovementComponent::OnRegister()
{
	Super::OnRegister();

	// 확장 이동 데이터는 packed RPC(p.NetUsePackedMovementRPCs, 기본 1)에서만 직렬화된다 — 꺼져 있으면 서버가 입력 샘플을 받지 못한다
	if (!ShouldUsePackedMovementRPCs())
	{
		UE_LOG(LogAstral, Error, TEXT("[InputFacing] %s: packed movement RPC가 꺼져 있다 (p.NetUsePackedMovementRPCs=0) — 입력 회전 샘플이 서버로 전달되지 않는다"), *GetNameSafe(GetOwner()));
	}
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
	// 예측 클라(SetMoveFor)·재실행(PrepMoveFor)·서버(ServerMove_PerformMovement)는 move 시작 전에 설치한다.
	// 설치된 것이 없으면(호스트·Standalone — SavedMove 경로가 없다) 이 move의 라이브 샘플을 만든다
	if (!bHasCurrentMoveInputFacing)
	{
		InstallCurrentMoveInputFacing(MakeLiveInputFacingSample());
	}

	Super::PerformMovement(DeltaSeconds);

	// 샘플 수명은 move 하나 — 다음 평가(다른 move·시뮬레이션)에 새지 않게 항상 해제
	ClearCurrentMoveInputFacing();
}

void UAstralHeroMovementComponent::ServerMove_PerformMovement(const FCharacterNetworkMoveData& MoveData)
{
	// 컨테이너를 우리 타입으로 설치했으므로 세 슬롯(New/Pending/Old) 모두 확장 타입이다. 샘플은 이 move의 것만 — 마지막 값을 재사용하지 않는다
	const FAstralCharacterNetworkMoveData_Hero& HeroMoveData = static_cast<const FAstralCharacterNetworkMoveData_Hero&>(MoveData);
	InstallCurrentMoveInputFacing(HeroMoveData.InputFacing);

	Super::ServerMove_PerformMovement(MoveData);

	// Super가 이동 전에 조기 반환(타임스탬프 만료 등)하면 PerformMovement의 해제가 돌지 않는다 — 여기서도 해제 (멱등)
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
	// 억제 = 현재 록온 선택 ∨ move 시작 시 유효한 기존 Facing 소유권 (클라가 예측 설치한 슬롯). 서버는 자기 슬롯을 Modifier에서 독립 적용한다
	const bool bSuppress = IsLocalLockOnActive() || IsFacingOwnerActive();
	return AstralInputFacing::MakeSample(WorldInput, CharacterOwner->GetActorRotation().Yaw, bSuppress);
}

void UAstralHeroMovementComponent::SetFacingOwner(const FAstralFacingOwnerId& Owner)
{
	if (Owner.IsValid())
	{
		FacingOwner = Owner;
	}
}

void UAstralHeroMovementComponent::ClearFacingOwnerIfMatches(const FAstralFacingOwnerId& Owner)
{
	if (FacingOwner.IsValid() && FacingOwner == Owner)
	{
		FacingOwner = FAstralFacingOwnerId();
	}
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
	SavedInputFacing = FAstralInputFacingSample();
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

	if (UAstralHeroMovementComponent* HeroMC = GetHeroMovementComponent(C))
	{
		bSavedWantsToSprint = HeroMC->WantsToSprint() ? 1 : 0;

		// 입력 회전 샘플 확정 — 부호는 여기서(move 시작 자세) 한 번 고른다. 같은 양자화값을 이번 PerformMovement에도 설치해 첫 로컬 실행과 서버·재실행이 같은 값을 쓴다
		SavedInputFacing = HeroMC->MakeLiveInputFacingSample();
		HeroMC->InstallCurrentMoveInputFacing(SavedInputFacing);
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
		// 재실행 — 이 move의 입력만 복원. 교차 시간·회전량은 보정된 자세·몽타주 위치로 다시 계산한다 (라이브 입력이 과거 move에 새지 않는다)
		HeroMC->InstallCurrentMoveInputFacing(SavedInputFacing);
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
// FAstralCharacterNetworkMoveData_Hero

void FAstralCharacterNetworkMoveData_Hero::ClientFillNetworkMoveData(const FSavedMove_Character& ClientMove, ENetworkMoveType MoveType)
{
	Super::ClientFillNetworkMoveData(ClientMove, MoveType);

	// SavedMove는 FAstralNetworkPredictionData_Client_Hero::AllocateNewMove가 만든 우리 타입
	const FAstralSavedMove_Hero& HeroMove = static_cast<const FAstralSavedMove_Hero&>(ClientMove);
	InputFacing = HeroMove.GetSavedInputFacing();
}

bool FAstralCharacterNetworkMoveData_Hero::Serialize(UCharacterMovementComponent& CharacterMovement, FArchive& Ar, UPackageMap* PackageMap, ENetworkMoveType MoveType)
{
	Super::Serialize(CharacterMovement, Ar, PackageMap, MoveType);

	// 기존 필드 뒤에 26비트 — New/Pending/Old 각 슬롯이 독립적으로 자기 샘플을 싣는다
	InputFacing.SerializeBits(Ar);

	return !Ar.IsError();
}

//////////////////////////////////////////////////////////////////////////
// FAstralCharacterNetworkMoveDataContainer_Hero

FAstralCharacterNetworkMoveDataContainer_Hero::FAstralCharacterNetworkMoveDataContainer_Hero()
{
	NewMoveData     = &HeroMoveData[0];
	PendingMoveData = &HeroMoveData[1];
	OldMoveData     = &HeroMoveData[2];
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
