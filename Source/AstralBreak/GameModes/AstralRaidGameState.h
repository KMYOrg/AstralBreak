#pragma once

#include "CoreMinimal.h"
#include "AstralGameState.h"
#include "AstralRaidGameState.generated.h"

class UAstralChainBurstComponent;

/**
 * 레이드(전투) 세션 상태 — 레이드 · 전투 시험 맵의 GameMode BP 가 GameStateClass 로 지정한다 (BP_AstralGameState_Raid 의 부모).
 * 지금은 체인 버스트(UAstralChainBurstComponent — 설계 Docs/Design/m4-ult-chain.md §3)만 갖는다.
 * M5 의 보스 상태, M6 의 목표 · 결과가 얹힐 자리다. 허브에는 이 클래스가 없으므로 체인 상태도 없다.
 */
UCLASS()
class ASTRALBREAK_API AAstralRaidGameState : public AAstralGameState
{
	GENERATED_BODY()

public:
	AAstralRaidGameState(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UFUNCTION(BlueprintPure, Category = "Astral|Chain")
	UAstralChainBurstComponent* GetChainBurstComponent() const { return ChainBurstComponent; }

private:
	/** 체인 판정 · 복제 · 버스트 피해. 값(윈도우 · 유예 · 피해 · 반경)은 BP 에서 이 컴포넌트의 디테일로 고친다 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Chain", meta = (AllowPrivateAccess = true))
	TObjectPtr<UAstralChainBurstComponent> ChainBurstComponent;
};
