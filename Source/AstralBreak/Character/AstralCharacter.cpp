#include "AstralCharacter.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Components/AstralPawnExtensionComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Player/AstralPlayerState.h"


AAstralCharacter::AAstralCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UAstralCharacterMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = false;
	PrimaryActorTick.bStartWithTickEnabled = false;

	bReplicates = true;
	SetReplicatingMovement(true);

	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw   = false;
	bUseControllerRotationRoll  = false;

	UCharacterMovementComponent* AstralMoveComp = GetCharacterMovement();
	AstralMoveComp->bOrientRotationToMovement = true;

	PawnExtComponent = CreateDefaultSubobject<UAstralPawnExtensionComponent>(TEXT("PawnExtComponent"));
}

void AAstralCharacter::PreInitializeComponents()
{
	Super::PreInitializeComponents();
}

void AAstralCharacter::BeginPlay()
{
	Super::BeginPlay();
}

void AAstralCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);
}

void AAstralCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	// 서버 경로: Possess 시점 Init State 시작
	PawnExtComponent->HandleControllerChanged();
}

void AAstralCharacter::UnPossessed()
{
	Super::UnPossessed();
	
	PawnExtComponent->HandleControllerChanged();
}

void AAstralCharacter::OnRep_Controller()
{
	Super::OnRep_Controller();

	PawnExtComponent->HandleControllerChanged();
}

void AAstralCharacter::OnRep_PlayerState()
{
	Super::OnRep_PlayerState();

	PawnExtComponent->HandlePlayerStateReplicated();
}

void AAstralCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	PawnExtComponent->SetupPlayerInputComponent();
}

UAbilitySystemComponent* AAstralCharacter::GetAbilitySystemComponent() const
{
	if (PawnExtComponent == nullptr)
	{
		return nullptr;
	}

	return PawnExtComponent->GetAstralAbilitySystemComponent();
}

AAstralPlayerState* AAstralCharacter::GetAstralPlayerState() const
{
	return CastChecked<AAstralPlayerState>(GetPlayerState(), ECastCheckedType::NullAllowed);
}

UAstralAbilitySystemComponent* AAstralCharacter::GetAstralAbilitySystemComponent() const
{
	return Cast<UAstralAbilitySystemComponent>(GetAbilitySystemComponent());
}

