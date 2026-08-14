#include "AstralHubGameState.h"

#include "Net/UnrealNetwork.h"
#include "Player/AstralPlayerState.h"

AAstralHubGameState::AAstralHubGameState()
{
	// 로비 = 액터 스폰만(홀스터 표시), 어빌리티·스탯 부여 없음
	EquipmentPolicy = EAstralEquipmentPolicy::VisualOnly;
}

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
