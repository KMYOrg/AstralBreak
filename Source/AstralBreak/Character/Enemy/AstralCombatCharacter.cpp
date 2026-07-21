#include "AstralCombatCharacter.h"

#include "AbilitySystem/AstralAbilitySet.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Net/UnrealNetwork.h"

AAstralCombatCharacter::AAstralCombatCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryActorTick.bCanEverTick = false;
	PrimaryActorTick.bStartWithTickEnabled = false;

	bReplicates = true;
	SetReplicatingMovement(true);

	// NPC는 GE 상세를 클라에 복제할 필요 없음 — 태그/큐/어트리뷰트만 (GAS 정석)
	AbilitySystemComponent = CreateDefaultSubobject<UAstralAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AbilitySystemComponent->SetIsReplicated(true);
	AbilitySystemComponent->SetReplicationMode(EGameplayEffectReplicationMode::Minimal);

	HealthSet = CreateDefaultSubobject<UAstralHealthSet>(TEXT("HealthSet"));
	CombatSet = CreateDefaultSubobject<UAstralCombatSet>(TEXT("CombatSet"));

	HealthComponent = CreateDefaultSubobject<UAstralHealthComponent>(TEXT("HealthComponent"));
}

UAbilitySystemComponent* AAstralCombatCharacter::GetAbilitySystemComponent() const
{
	return AbilitySystemComponent;
}

void AAstralCombatCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralCombatCharacter, TeamId);
}

void AAstralCombatCharacter::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	check(AbilitySystemComponent);
	AbilitySystemComponent->InitAbilityActorInfo(this, this);

	HealthComponent->InitializeWithAbilitySystem(AbilitySystemComponent);
	HealthComponent->OnDeathStarted.AddDynamic(this, &ThisClass::HandleDeathStarted);
	HealthComponent->OnDeathFinished.AddDynamic(this, &ThisClass::HandleDeathFinished);
}

void AAstralCombatCharacter::BeginPlay()
{
	Super::BeginPlay();

	if (HasAuthority())
	{
		for (const UAstralAbilitySet* AbilitySet : AbilitySets)
		{
			if (AbilitySet)
			{
				AbilitySet->GiveToAbilitySystem(AbilitySystemComponent, nullptr, this);
			}
		}
	}
}

void AAstralCombatCharacter::HandleDeathStarted(AActor* OwningActor)
{
	// 물리 반응 — 히트 판정(ECC_Pawn 스윕)에서 빠지고 이동 정지
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->StopMovementImmediately();
		MoveComp->DisableMovement();
	}

	// FinishDeath는 GA_Death(DeathDuration)가 호출 — AbilitySet에 GA_Death 부여 필수
}

void AAstralCombatCharacter::HandleDeathFinished(AActor* OwningActor)
{
	if (HasAuthority())
	{
		// 복제 액터라 서버 LifeSpan 만료 시 클라에서도 함께 제거됨
		SetLifeSpan(DestroyAfterDeathDelay);
	}
}
