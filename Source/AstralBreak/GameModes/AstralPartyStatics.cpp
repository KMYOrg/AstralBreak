#include "AstralPartyStatics.h"

namespace AstralParty
{
	bool IsPartyMember(const FAstralPartyMember& Member)
	{
		return !Member.bIsBot && !Member.bIsSpectator && Member.PlayerId != 0;
	}

	TArray<int32> SortedMemberIndices(TConstArrayView<FAstralPartyMember> Members)
	{
		TArray<int32> Out;
		for (int32 Index = 0; Index < Members.Num(); ++Index)
		{
			const FAstralPartyMember& Member = Members[Index];
			const bool bDuplicate = Out.ContainsByPredicate([&](int32 Other) { return Members[Other].PlayerId == Member.PlayerId; });
			if (IsPartyMember(Member) && !bDuplicate)
			{
				Out.Add(Index);
			}
		}

		// 번호는 겹치지 않으므로 순서가 하나로 정해진다
		Out.Sort([&](int32 A, int32 B) { return Members[A].PlayerId < Members[B].PlayerId; });
		return Out;
	}

	int32 SelectLeaderIndex(TConstArrayView<FAstralPartyMember> Members)
	{
		int32 LeaderIndex = INDEX_NONE;

		for (int32 Index = 0; Index < Members.Num(); ++Index)
		{
			const FAstralPartyMember& Member = Members[Index];
			if (!IsPartyMember(Member))
			{
				continue;
			}

			// 동률은 앞쪽 유지(<) — 결과가 배열 순서 밖의 것에 기대지 않게 한다
			if (LeaderIndex == INDEX_NONE || Member.PlayerId < Members[LeaderIndex].PlayerId)
			{
				LeaderIndex = Index;
			}
		}

		return LeaderIndex;
	}

	TArray<int32> SelectAllyIndices(TConstArrayView<FAstralPartyMember> Members, int32 SelfPlayerId, int32 MaxAllies)
	{
		TArray<int32> Allies = SortedMemberIndices(Members);
		Allies.RemoveAll([&](int32 Index) { return Members[Index].PlayerId == SelfPlayerId; });
		if (Allies.Num() > MaxAllies)
		{
			Allies.SetNum(FMath::Max(MaxAllies, 0));
		}
		return Allies;
	}
}
