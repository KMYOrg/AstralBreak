#pragma once

#include "CoreMinimal.h"
#include "AstralGameState.h"
#include "GameModes/AstralLobbyRules.h"
#include "Player/AstralPlayerLoadout.h"
#include "AstralHubGameState.generated.h"

/**
 * 로비(Hub) 세션 상태 — 고를 수 있는 목적지 목록, 방장이 고른 목적지, 전원 준비 집계.
 * Hub GameMode가 GameStateClass로 지정 (GameState는 맵마다 재생성이라 travel과 상호작용 없음 — PC 분리와 달리 저위험).
 * 판정 규칙은 AstralLobby(순수 함수) — 여기는 값과 통지만 갖는다. Raid 쪽 상태는 AstralRaidGameState.
 */
UCLASS()
class ASTRALBREAK_API AAstralHubGameState : public AAstralGameState
{
	GENERATED_BODY()

public:
	AAstralHubGameState();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** 서버 — 방장이 고른 목적지. 값이 바뀔 때만 OnSelectedRaidChanged */
	void SetSelectedRaid(const FAstralRaidRequest& InRequest);

	const FAstralRaidRequest& GetSelectedRaid() const { return SelectedRaid; }

	/** 고를 수 있는 레이드 — 허용 목록이자 보이는 이름의 단일 원천. 서버 검사(AstralLobby::CheckSelect)도 이것을 본다 */
	const TArray<FAstralRaidDestination>& GetRaidDestinations() const { return RaidDestinations; }

	/** 목록에서 맵 이름이 정확히 같은 것 — 없으면 nullptr */
	const FAstralRaidDestination* FindRaidDestination(const FString& MapName) const;

	/** 전원 준비 여부(파티원만 — 봇 · 관전자 제외, AstralLobby::AreAllMembersReady). 복제 상태만 읽으므로 어디서든 호출 가능 */
	UFUNCTION(BlueprintPure, Category = "Astral|Lobby")
	bool AreAllPlayersReady() const;

	/** 목적지가 바뀌었다 (서버 SetSelectedRaid + 클라 OnRep — 전 머신). 리슨 호스트에는 RepNotify 가 없어 서버 쪽 set 에서도 방송한다 */
	FSimpleMulticastDelegate OnSelectedRaidChanged;

protected:
	//~AAstralGameState interface
	virtual void FillLobbyState(FAstralLobbySnapshot& Snapshot) const override;
	//~End of AAstralGameState interface

	UFUNCTION()
	void OnRep_SelectedRaid();

	UPROPERTY(ReplicatedUsing = OnRep_SelectedRaid)
	FAstralRaidRequest SelectedRaid;

	/**
	 * 고를 수 있는 레이드(편집 기본값 — 복제하지 않는다. 클라이언트도 같은 기본 객체에서 읽는다).
	 * 클라이언트가 보낸 이름이 그대로 ServerTravel 주소가 되므로 여기 있는 것만 받는다. 정식 퀘스트 구조(M6)가 생기면 원천을 그쪽으로 바꾼다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Lobby", meta = (TitleProperty = "MapName"))
	TArray<FAstralRaidDestination> RaidDestinations;
};
