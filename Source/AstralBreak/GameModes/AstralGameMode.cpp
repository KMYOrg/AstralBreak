#include "AstralGameMode.h"

#include "AstralGameState.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "Character/AstralPawnData.h"
#include "Character/Hero/AstralCharacter_Hero.h"

AAstralGameMode::AAstralGameMode(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	GameStateClass = AAstralGameState::StaticClass();
	PlayerControllerClass = AAstralPlayerController::StaticClass();
	PlayerStateClass = AAstralPlayerState::StaticClass();
	DefaultPawnClass = AAstralCharacter_Hero::StaticClass();
}

const UAstralPawnData* AAstralGameMode::GetPawnDataForController(const AController* InController) const
{
	return DefaultPawnData.LoadSynchronous();
}

UClass* AAstralGameMode::GetDefaultPawnClassForController_Implementation(AController* InController)
{
	return Super::GetDefaultPawnClassForController_Implementation(InController);
}
