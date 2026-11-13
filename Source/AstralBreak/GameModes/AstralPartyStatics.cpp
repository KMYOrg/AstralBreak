#include "AstralPartyStatics.h"

namespace AstralParty
{
	int32 SelectLeaderIndex(TConstArrayView<FAstralPartyMember> Members)
	{
		int32 LeaderIndex = INDEX_NONE;

		for (int32 Index = 0; Index < Members.Num(); ++Index)
		{
			const FAstralPartyMember& Member = Members[Index];
			if (Member.bIsBot || Member.bIsSpectator)
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
}
