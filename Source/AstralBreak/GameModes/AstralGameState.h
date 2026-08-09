#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "Player/AstralPlayerLoadout.h"
#include "AstralGameState.generated.h"

/**
 * 세션 단위 로비 상태 — 방장이 고른 목적지와 전원 준비 집계.
 * 플레이어별 상태(로드아웃·준비)는 PlayerState 소유.
 */
UCLASS()
class ASTRALBREAK_API AAstralGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** 서버 — 방장이 고른 목적지 */
	void SetSelectedRaid(const FAstralRaidRequest& InRequest);

	const FAstralRaidRequest& GetSelectedRaid() const { return SelectedRaid; }

	/** 전원 준비 여부 (서버 판정용이지만 복제 상태만 읽으므로 어디서든 호출 가능) */
	UFUNCTION(BlueprintPure, Category = "Astral|Lobby")
	bool AreAllPlayersReady() const;

protected:
	UPROPERTY(Replicated)
	FAstralRaidRequest SelectedRaid;
};
