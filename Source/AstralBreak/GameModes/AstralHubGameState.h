#pragma once

#include "CoreMinimal.h"
#include "AstralGameState.h"
#include "Player/AstralPlayerLoadout.h"
#include "AstralHubGameState.generated.h"

/**
 * 로비(Hub) 세션 상태 — 방장이 고른 목적지와 전원 준비 집계.
 * Hub GameMode가 GameStateClass로 지정 (GameState는 맵마다 재생성이라 travel과 상호작용 없음 — PC 분리와 달리 저위험).
 * Raid 쪽 상태(목표·진행도)는 내용물이 생기는 M3+에서 RaidGameState로.
 */
UCLASS()
class ASTRALBREAK_API AAstralHubGameState : public AAstralGameState
{
	GENERATED_BODY()

public:
	AAstralHubGameState();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** 서버 — 방장이 고른 목적지 */
	void SetSelectedRaid(const FAstralRaidRequest& InRequest);

	const FAstralRaidRequest& GetSelectedRaid() const { return SelectedRaid; }

	/** 전원 준비 여부 — 복제 상태만 읽으므로 어디서든 호출 가능 */
	UFUNCTION(BlueprintPure, Category = "Astral|Lobby")
	bool AreAllPlayersReady() const;

protected:
	UPROPERTY(Replicated)
	FAstralRaidRequest SelectedRaid;
};
