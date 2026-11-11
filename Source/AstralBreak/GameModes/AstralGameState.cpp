#include "AstralGameState.h"

#include "AstralPartyStatics.h"
#include "GameFramework/PlayerState.h"

APlayerState* AAstralGameState::GetPartyLeader() const
{
	// 후보 수집만 여기서 — 고르는 규칙은 AstralParty::SelectLeaderIndex (월드 없이 시험)
	TArray<APlayerState*, TInlineAllocator<8>> States;
	TArray<FAstralPartyMember, TInlineAllocator<8>> Members;

	for (APlayerState* PS : PlayerArray)
	{
		if (!PS)
		{
			continue;
		}

		FAstralPartyMember& Member = Members.AddDefaulted_GetRef();
		Member.PlayerId = PS->GetPlayerId();
		Member.bIsBot = PS->IsABot();
		Member.bIsSpectator = PS->IsOnlyASpectator();
		States.Add(PS);
	}

	const int32 LeaderIndex = AstralParty::SelectLeaderIndex(Members);
	return States.IsValidIndex(LeaderIndex) ? States[LeaderIndex] : nullptr;
}
