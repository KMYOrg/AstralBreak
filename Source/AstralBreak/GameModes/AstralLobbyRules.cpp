#include "AstralLobbyRules.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralLobbyRules)

#define LOCTEXT_NAMESPACE "AstralLobby"

namespace AstralLobby
{
	namespace
	{
		/** 방장 · 파티원 규칙(AstralParty)이 받는 모양 */
		TArray<FAstralPartyMember, TInlineAllocator<8>> PartyView(const FAstralLobbySnapshot& Snapshot)
		{
			TArray<FAstralPartyMember, TInlineAllocator<8>> Out;
			for (const FAstralLobbyMember& Member : Snapshot.Members)
			{
				Out.Add(Member.Party);
			}
			return Out;
		}

		bool IsRequesterLeader(const FAstralLobbySnapshot& Snapshot)
		{
			return Snapshot.RequesterIndex != INDEX_NONE && SelectLeaderIndex(Snapshot) == Snapshot.RequesterIndex;
		}
	}

	EAstralLobbyDenial CheckReady(const FAstralLobbySnapshot& Snapshot)
	{
		return EAstralLobbyDenial::None;
	}

	EAstralLobbyDenial CheckSelect(const FAstralLobbySnapshot& Snapshot, const FString& MapName)
	{
		if (!IsRequesterLeader(Snapshot))
		{
			return EAstralLobbyDenial::NotLeader;
		}
		if (!Snapshot.bInHub)
		{
			return EAstralLobbyDenial::NotInHub;
		}
		if (!IsRaidAllowed(Snapshot.AllowedRaids, MapName))
		{
			return EAstralLobbyDenial::RaidNotAllowed;
		}
		return EAstralLobbyDenial::None;
	}

	EAstralLobbyDenial CheckStart(const FAstralLobbySnapshot& Snapshot)
	{
		if (!IsRequesterLeader(Snapshot))
		{
			return EAstralLobbyDenial::NotLeader;
		}
		if (!Snapshot.bInHub)
		{
			return EAstralLobbyDenial::NotInHub;
		}
		if (Snapshot.SelectedRaid.IsEmpty())
		{
			return EAstralLobbyDenial::NoRaidSelected;
		}
		// 고를 때 이미 본 값이지만 이것이 ServerTravel 주소가 된다 — 목록과 다시 맞춘다
		if (!IsRaidAllowed(Snapshot.AllowedRaids, Snapshot.SelectedRaid))
		{
			return EAstralLobbyDenial::RaidNotAllowed;
		}
		if (!AreAllMembersReady(Snapshot))
		{
			return EAstralLobbyDenial::NotAllReady;
		}
		return EAstralLobbyDenial::None;
	}

	bool AreAllMembersReady(const FAstralLobbySnapshot& Snapshot)
	{
		// 같은 거르기(AstralParty::SortedMemberIndices) — 관전자 · 봇은 세지 않는다
		const TArray<int32> MemberIndices = AstralParty::SortedMemberIndices(PartyView(Snapshot));
		if (MemberIndices.IsEmpty())
		{
			return false;
		}
		for (const int32 Index : MemberIndices)
		{
			if (!Snapshot.Members[Index].bIsReady)
			{
				return false;
			}
		}
		return true;
	}

	int32 SelectLeaderIndex(const FAstralLobbySnapshot& Snapshot)
	{
		return AstralParty::SelectLeaderIndex(PartyView(Snapshot));
	}

	TArray<int32> SelectRowIndices(const FAstralLobbySnapshot& Snapshot, int32 MaxRows)
	{
		TArray<int32> Rows = AstralParty::SortedMemberIndices(PartyView(Snapshot));
		if (Rows.Num() > MaxRows)
		{
			Rows.SetNum(FMath::Max(MaxRows, 0));
		}
		return Rows;
	}

	bool IsRaidAllowed(TConstArrayView<FString> AllowedRaids, const FString& MapName)
	{
		// FString == 는 대소문자를 무시한다 — 목록의 표기 그대로만 받는다
		return !MapName.IsEmpty() && AllowedRaids.ContainsByPredicate([&MapName](const FString& Allowed)
		{
			return Allowed.Equals(MapName, ESearchCase::CaseSensitive);
		});
	}

	FText GetDenialText(EAstralLobbyDenial Denial)
	{
		// 글은 잠정(기획 요소) — 바꾸면 화면 시험(AstralBreak.Net.HubReady.*)은 이 함수로 견주므로 그대로 돈다
		switch (Denial)
		{
		case EAstralLobbyDenial::NotInHub: return LOCTEXT("NotInHub", "허브에서만 할 수 있습니다");
		case EAstralLobbyDenial::NotLeader: return LOCTEXT("NotLeader", "방장이 목적지를 고르고 출정합니다");
		case EAstralLobbyDenial::RaidNotAllowed: return LOCTEXT("RaidNotAllowed", "갈 수 없는 목적지입니다");
		case EAstralLobbyDenial::NoRaidSelected: return LOCTEXT("NoRaidSelected", "목적지를 고르세요");
		case EAstralLobbyDenial::NotAllReady: return LOCTEXT("NotAllReady", "모두 준비하면 출정할 수 있습니다");
		case EAstralLobbyDenial::None:
		default: return FText::GetEmpty();
		}
	}

	FText GetRequestDeniedText(EAstralLobbyDenial Denial)
	{
		return Denial == EAstralLobbyDenial::None ? FText::GetEmpty() : FText::Format(LOCTEXT("RequestDenied", "거절됨 — {0}"), GetDenialText(Denial));
	}

	const TCHAR* LexToString(EAstralLobbyDenial Denial)
	{
		switch (Denial)
		{
		case EAstralLobbyDenial::None: return TEXT("None");
		case EAstralLobbyDenial::NotInHub: return TEXT("NotInHub");
		case EAstralLobbyDenial::NotLeader: return TEXT("NotLeader");
		case EAstralLobbyDenial::RaidNotAllowed: return TEXT("RaidNotAllowed");
		case EAstralLobbyDenial::NoRaidSelected: return TEXT("NoRaidSelected");
		case EAstralLobbyDenial::NotAllReady: return TEXT("NotAllReady");
		default: return TEXT("?");
		}
	}
}

#undef LOCTEXT_NAMESPACE
