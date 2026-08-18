#include "AstralPartySubsystem.h"

#include "AstralLogChannels.h"

void UAstralPartySubsystem::CacheLoadout(const FUniqueNetIdRepl& PlayerId, const FAstralPlayerLoadout& Loadout)
{
	if (!PlayerId.IsValid())
	{
		UE_LOG(LogAstral, Warning, TEXT("PartySubsystem::CacheLoadout — 무효 PlayerId, 캐시 생략 (클라 재발신 경로가 커버)"));
		return;
	}

	LoadoutCache.Add(PlayerId, Loadout);
}

const FAstralPlayerLoadout* UAstralPartySubsystem::FindLoadout(const FUniqueNetIdRepl& PlayerId) const
{
	if (!PlayerId.IsValid())
	{
		return nullptr;
	}
	return LoadoutCache.Find(PlayerId);
}
