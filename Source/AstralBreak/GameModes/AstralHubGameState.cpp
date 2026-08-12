#include "AstralHubGameState.h"

#include "Net/UnrealNetwork.h"
#include "Player/AstralPlayerState.h"

void AAstralHubGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralHubGameState, SelectedRaid);
}

void AAstralHubGameState::SetSelectedRaid(const FAstralRaidRequest& InRequest)
{
	if (!HasAuthority())
	{
		return;
	}
	SelectedRaid = InRequest;
	ForceNetUpdate();
}

bool AAstralHubGameState::AreAllPlayersReady() const
{
	if (PlayerArray.Num() == 0)
	{
		return false;
	}

	for (const APlayerState* PS : PlayerArray)
	{
		const AAstralPlayerState* AstralPS = Cast<AAstralPlayerState>(PS);
		if (!AstralPS || !AstralPS->IsReady())
		{
			return false;
		}
	}
	return true;
}
