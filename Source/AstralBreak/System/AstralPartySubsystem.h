#pragma once

#include "CoreMinimal.h"
#include "GameFramework/OnlineReplStructs.h"
#include "Player/AstralPlayerLoadout.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "AstralPartySubsystem.generated.h"

/**
 * 서버 권위 세션 캐시 — 로드아웃 소스 3단의 2단 (travel 직후 PS.Loadout이 비어 있는 창을 메우는 폴백).
 * 같은 프로세스 travel이면 GameInstance가 유지되어 도착 즉시 조회 가능(갭 없음).
 * 별도 인스턴스 서버로 가면 이 캐시는 비고, 클라 재발신 RPC가 1단(PS.Loadout)을 채운다 — 캐시 미스는 설계상 정상 경로.
 * BuildPayload/RestoreLoadoutFor를 명시 함수로 분리 — URL options·백엔드 조회로 교체될 지점.
 */
UCLASS()
class ASTRALBREAK_API UAstralPartySubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	/** 서버 — 플레이어 선택 캐시. 무효 키(PIE/Null OSS에서 가능)는 저장하지 않는다 — 클라 재발신이 커버 */
	void CacheLoadout(const FUniqueNetIdRepl& PlayerId, const FAstralPlayerLoadout& Loadout);

	/** 서버 — 캐시 조회. 없으면 nullptr (호출자는 다음 소스로) */
	const FAstralPlayerLoadout* FindLoadout(const FUniqueNetIdRepl& PlayerId) const;

	void SetSelectedRaid(const FAstralRaidRequest& InRequest) { SelectedRaid = InRequest; }
	const FAstralRaidRequest& GetSelectedRaid() const { return SelectedRaid; }

private:
	/** 키 = UniqueNetId — PIE/Null OSS에서 4인 각각 유효한지는 M1 검증 항목 */
	TMap<FUniqueNetIdRepl, FAstralPlayerLoadout> LoadoutCache;

	FAstralRaidRequest SelectedRaid;
};
