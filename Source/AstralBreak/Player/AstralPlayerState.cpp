#include "AstralPlayerState.h"

#include "AbilitySystemComponent.h"
#include "AstralLogChannels.h"
#include "AstralPlayerController.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "Character/AstralPawnData.h"
#include "Character/Hero/AstralPawnData_Hero.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Components/GameFrameworkComponentManager.h"
#include "GameModes/AstralGameMode.h"
#include "Net/UnrealNetwork.h"
#include "System/AstralGameData.h"

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

	//@TODO: Copy stats
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

	// 받은 피해 → 오의 수급. OnDamaged는 서버에서만 브로드캐스트되므로 구독 자체는 전역, 실행은 서버만
	if (HealthSet)
	{
		HealthSet->OnDamaged.AddUObject(this, &ThisClass::OnHeroDamaged);
	}

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

	// TODO: M1 마일스톤
	// UGameFrameworkComponentManager::SendGameFrameworkComponentExtensionEvent(this, NAME_AstralAbilityReady);
	
	ForceNetUpdate();
}

void AAstralPlayerState::OnRep_PawnData()
{
}

void AAstralPlayerState::OnHeroDamaged(AActor* DamageInstigator, AActor* DamageCauser, const FGameplayEffectSpec* DamageEffectSpec, float DamageMagnitude, float OldValue, float NewValue)
{
	if (GetLocalRole() != ROLE_Authority || DamageMagnitude <= 0.f)
	{
		return;
	}

	const UAstralPawnData_Hero* HeroData = GetPawnData<UAstralPawnData_Hero>();
	if (!HeroData || HeroData->UltGainOnDamagedRatio <= 0.f)
	{
		return;
	}

	const TSubclassOf<UGameplayEffect> UltGainEffectClass = UAstralGameData::Get().UltGainGameplayEffect_SetByCaller.LoadSynchronous();
	if (!UltGainEffectClass)
	{
		return;
	}

	FGameplayEffectContextHandle Context = AbilitySystemComponent->MakeEffectContext();
	const FGameplayEffectSpecHandle SpecHandle = AbilitySystemComponent->MakeOutgoingSpec(UltGainEffectClass, 1.0f, Context);
	if (SpecHandle.IsValid())
	{
		SpecHandle.Data->SetSetByCallerMagnitude(AstralGameplayTags::SetByCaller_UltGain, DamageMagnitude * HeroData->UltGainOnDamagedRatio);
		AbilitySystemComponent->ApplyGameplayEffectSpecToSelf(*SpecHandle.Data.Get());
	}
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

