#include "AstralPlayerController.h"

#include "AstralPlayerState.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"

AAstralPlayerController::AAstralPlayerController(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void AAstralPlayerController::PreInitializeComponents()
{
	Super::PreInitializeComponents();
}

void AAstralPlayerController::BeginPlay()
{
	Super::BeginPlay();
}

void AAstralPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);
}

void AAstralPlayerController::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
}

AAstralPlayerState* AAstralPlayerController::GetAstralPlayerState() const
{
	return CastChecked<AAstralPlayerState>(PlayerState, ECastCheckedType::NullAllowed);
}

UAstralAbilitySystemComponent* AAstralPlayerController::GetAstralAbilitySystemComponent() const
{
	const AAstralPlayerState* AstralPS = GetAstralPlayerState();
	return (AstralPS ? AstralPS->GetAstralAbilitySystemComponent() : nullptr);
}

void AAstralPlayerController::PostProcessInput(const float DeltaTime, const bool bGamePaused)
{
	if (UAstralAbilitySystemComponent* AstralASC = GetAstralAbilitySystemComponent())
	{
		AstralASC->ProcessAbilityInput(DeltaTime, bGamePaused);
	}

	Super::PostProcessInput(DeltaTime, bGamePaused);
}



