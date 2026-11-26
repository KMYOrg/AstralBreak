#include "AstralGameState.h"

#include "AstralPartyStatics.h"
#include "GameFramework/PlayerState.h"
#include "Player/AstralPlayerState.h"

namespace AstralGameStateImpl
{
	/** 방장 · 로비 규칙이 받는 한 사람 — PlayerArray 의 값을 그대로 옮긴다(거르기는 AstralParty::IsPartyMember) */
	FAstralPartyMember ToPartyMember(const APlayerState& PlayerState)
	{
		FAstralPartyMember Member;
		Member.PlayerId = PlayerState.GetPlayerId();
		Member.bIsBot = PlayerState.IsABot();
		Member.bIsSpectator = PlayerState.IsOnlyASpectator();
		return Member;
	}
}

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
		Members.Add(AstralGameStateImpl::ToPartyMember(*PS));
		States.Add(PS);
	}

	const int32 LeaderIndex = AstralParty::SelectLeaderIndex(Members);
	return States.IsValidIndex(LeaderIndex) ? States[LeaderIndex] : nullptr;
}

FAstralLobbySnapshot AAstralGameState::MakeLobbySnapshot(const APlayerState* Requester, TArray<APlayerState*>* OutMemberStates) const
{
	FAstralLobbySnapshot Snapshot;
	if (OutMemberStates)
	{
		OutMemberStates->Reset();
	}

	for (APlayerState* PS : PlayerArray)
	{
		if (!PS)
		{
			continue;
		}
		if (PS == Requester)
		{
			Snapshot.RequesterIndex = Snapshot.Members.Num();
		}
		FAstralLobbyMember& Member = Snapshot.Members.AddDefaulted_GetRef();
		Member.Party = AstralGameStateImpl::ToPartyMember(*PS);
		const AAstralPlayerState* AstralPS = Cast<AAstralPlayerState>(PS);
		Member.bIsReady = AstralPS && AstralPS->IsReady();
		if (OutMemberStates)
		{
			OutMemberStates->Add(PS);
		}
	}

	FillLobbyState(Snapshot);
	return Snapshot;
}

void AAstralGameState::AddPlayerState(APlayerState* PlayerState)
{
	Super::AddPlayerState(PlayerState);
	NotifyPlayerRosterChanged();
}

void AAstralGameState::RemovePlayerState(APlayerState* PlayerState)
{
	Super::RemovePlayerState(PlayerState);
	NotifyPlayerRosterChanged();
}
