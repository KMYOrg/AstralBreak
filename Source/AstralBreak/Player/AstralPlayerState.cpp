#include "AstralPlayerState.h"

#include "AbilitySystemComponent.h"
#include "AstralLogChannels.h"
#include "AstralPlayerController.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "Character/AstralPawnData.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Components/GameFrameworkComponentManager.h"
#include "GameModes/AstralGameMode.h"
#include "GameModes/AstralGameState.h"
#include "Net/UnrealNetwork.h"

AAstralPlayerState::AAstralPlayerState(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	AbilitySystemComponent = ObjectInitializer.CreateDefaultSubobject<UAstralAbilitySystemComponent>(this, TEXT("AbilitySystemComponent"));
	AbilitySystemComponent->SetIsReplicated(true);
	AbilitySystemComponent->SetReplicationMode(EGameplayEffectReplicationMode::Mixed);
	
	HealthSet = CreateDefaultSubobject<UAstralHealthSet>(TEXT("HealthSet"));
	CombatSet = CreateDefaultSubobject<UAstralCombatSet>(TEXT("CombatSet"));
	
	SetNetUpdateFrequency(100.0f);

}

void AAstralPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	
	FDoRepLifetimeParams SharedParams;
	SharedParams.bIsPushBased = true;

	DOREPLIFETIME_WITH_PARAMS_FAST(ThisClass, PawnData, SharedParams);

	DOREPLIFETIME(ThisClass, MyTeamID);
	DOREPLIFETIME(ThisClass, Loadout);
	DOREPLIFETIME(ThisClass, bIsReady);
}

void AAstralPlayerState::SetLoadout(const FAstralPlayerLoadout& InLoadout)
{
	if (GetLocalRole() != ROLE_Authority)
	{
		return;
	}

	Loadout = InLoadout;
	OnLoadoutChanged.Broadcast();
	ForceNetUpdate();
}

void AAstralPlayerState::SetReady(bool bInReady)
{
	if (GetLocalRole() != ROLE_Authority)
	{
		return;
	}
	bIsReady = bInReady;
	ForceNetUpdate();
}

void AAstralPlayerState::OnRep_Loadout()
{
	OnLoadoutChanged.Broadcast();
}

void AAstralPlayerState::SetGenericTeamId(const FGenericTeamId& NewTeamID)
{
	if (HasAuthority())
	{
		MyTeamID = NewTeamID;
	}
	else
	{
		UE_LOG(LogAstral, Error, TEXT("AAstralPlayerState::SetGenericTeamId: Cannot set team on non-authority for [%s]."), *GetPathNameSafe(this));
	}
}

void AAstralPlayerState::PreInitializeComponents()
{
	Super::PreInitializeComponents();
}

void AAstralPlayerState::Reset()
{
	Super::Reset();
}

void AAstralPlayerState::ClientInitialize(AController* C)
{
	Super::ClientInitialize(C);

	if (UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(GetPawn()))
	{
		PawnExtComp->CheckDefaultInitialization();
	}
}

void AAstralPlayerState::CopyProperties(APlayerState* PlayerState)
{
	Super::CopyProperties(PlayerState);

	// seamless travel 이월 — Loadout만. 없으면 클라 재발신 RPC 도착 전까지 외형이 기본 메시로 나오고,
	// 클라 캐시가 비어 있으면 영영 복구되지 않는다.
	if (AAstralPlayerState* NewPS = Cast<AAstralPlayerState>(PlayerState))
	{
		NewPS->Loadout = Loadout;
	}
}

AAstralPlayerController* AAstralPlayerState::GetAstralPlayerController() const
{
	return Cast<AAstralPlayerController>(GetOwner());
}

UAbilitySystemComponent* AAstralPlayerState::GetAbilitySystemComponent() const
{
	return GetAstralAbilitySystemComponent();
}

void AAstralPlayerState::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	check(AbilitySystemComponent);
	AbilitySystemComponent->InitAbilityActorInfo(this, GetPawn());

	// TODO : M1 마일스톤
	// UWorld* World = GetWorld();
	// if (World && World->IsGameWorld() && World->GetNetMode() != NM_Client)
	// {
	// 	AGameStateBase* GameState = GetWorld()->GetGameState();
	// 	check(GameState);
	// 	UAstralExperienceManagerComponent* ExperienceComponent = GameState->FindComponentByClass<UAstralExperienceManagerComponent>();
	// 	check(ExperienceComponent);
	// 	ExperienceComponent->CallOrRegister_OnExperienceLoaded(FOnAstralExperienceLoaded::FDelegate::CreateUObject(this, &ThisClass::OnExperienceLoaded));
	// }
}

void AAstralPlayerState::SetPawnData(const UAstralPawnData* InPawnData)
{
	check(InPawnData);

	if (GetLocalRole() != ROLE_Authority)
	{
		return;
	}

	if (PawnData)
	{
		UE_LOG(LogAstral, Error, TEXT("Trying to set PawnData [%s] on player state [%s] that already has valid PawnData [%s]."), *GetNameSafe(InPawnData), *GetNameSafe(this), *GetNameSafe(PawnData));
		return;
	}

	MARK_PROPERTY_DIRTY_FROM_NAME(ThisClass, PawnData, this);
	PawnData = InPawnData;

	for (const UAstralAbilitySet* AbilitySet : PawnData->AbilitySets)
	{
		if (AbilitySet)
		{
			AbilitySet->GiveToAbilitySystem(AbilitySystemComponent, nullptr);
		}
	}

	// "이 맵에서 누구나 갖는 능력"(이동/점프 등)은 월드(GameState)가 정의.
	// InitGameState가 PS 생성보다 먼저라 GameState는 항상 존재
	if (const AAstralGameState* AstralGS = GetWorld() ? GetWorld()->GetGameState<AAstralGameState>() : nullptr)
	{
		for (const UAstralAbilitySet* AbilitySet : AstralGS->GetContextAbilitySets())
		{
			if (AbilitySet)
			{
				AbilitySet->GiveToAbilitySystem(AbilitySystemComponent, nullptr);
			}
		}
	}

	// TODO: M1 마일스톤
	// UGameFrameworkComponentManager::SendGameFrameworkComponentExtensionEvent(this, NAME_AstralAbilityReady);
	
	ForceNetUpdate();
}

// TODO: M1 마일스톤
// void AAstralPlayerState::OnExperienceLoaded(const UAstralExperienceDefinition* /*CurrentExperience*/)
// {
// 	if (AAstralGameMode* AstralGameMode = GetWorld()->GetAuthGameMode<AAstralGameMode>())
// 	{
// 		if (const UAstralPawnData* NewPawnData = AstralGameMode->GetPawnDataForController(GetOwningController()))
// 		{
// 			SetPawnData(NewPawnData);
// 		}
// 		else
// 		{
// 			UE_LOG(LogAstral, Error, TEXT("AAstralPlayerState::OnExperienceLoaded(): Unable to find PawnData to initialize player state [%s]!"), *GetNameSafe(this));
// 		}
// 	}
// }

