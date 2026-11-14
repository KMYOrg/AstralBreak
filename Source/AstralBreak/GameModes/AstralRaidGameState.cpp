#include "AstralRaidGameState.h"

#include "AstralChainBurstComponent.h"

AAstralRaidGameState::AAstralRaidGameState(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	ChainBurstComponent = CreateDefaultSubobject<UAstralChainBurstComponent>(TEXT("ChainBurstComponent"));
}
