#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "AstralGameState.generated.h"

/**
 * 공통 베이스 — 정말 공통인 파티/플레이어 수준 상태만.
 * 로비 상태(SelectedRaid·준비 집계)는 AstralHubGameState, 레이드 상태(목표·진행도)는 M3+의 RaidGameState.
 * 플레이어별 상태(로드아웃·준비)는 PlayerState 소유.
 */
UCLASS()
class ASTRALBREAK_API AAstralGameState : public AGameStateBase
{
	GENERATED_BODY()
};
