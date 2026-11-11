#pragma once

#include "CoreMinimal.h"
#include "GauntletTestController.h"
#include "AstralPartyFlowTestController.generated.h"

struct FAstralPartyFlowSnapshot;

/**
 * 파티 흐름 네트워크 시험 — 별도 프로세스 구성 (설계 Docs/Design/m3-enemy-ai.md §7-2 ②)
 *
 * 프로세스마다 하나씩 뜬다: `-gauntlet=AstralPartyFlowTest -AstralPartyPlayers=N [-AstralPartyScenario=Flow|LeaderLeaves]`.
 * 실행은 Tools/net_test/run_party_flow.py 가 서버 1 + 클라이언트 N 을 띄워서 한다.
 *
 * 각 프로세스는 복제된 상태만 보고 역할(서버 · 방장 · 비방장)을 정하고 제 대본을 돈다.
 * 프로세스 사이 순서는 bIsReady 로 맞춘다 — 비방장은 '거부당할 요청' 을 보낸 뒤 준비를 켜고, 방장은 전원 준비를 본 뒤 다음으로 간다
 * (bIsReady 는 이동 때 넘어가지 않아 맵마다 다시 쓴다).
 * 판정은 표준 출력의 `ASTRAL_NETTEST RESULT PASS|FAIL` 줄이다. 거부 로그 횟수는 실행 스크립트가 서버 출력에서 센다.
 */
UCLASS()
class UAstralPartyFlowTestController : public UGauntletTestController
{
	GENERATED_BODY()

public:
	//~UGauntletTestController interface
	virtual void OnInit() override;
	virtual void OnTick(float TimeDelta) override;
	//~End of UGauntletTestController interface

private:
	enum class ERole : uint8
	{
		Unknown,
		/** Dedicated 서버 프로세스 — 요청하지 않고 지켜보기만 한다 */
		Server,
		/** 방장 (리슨 호스트 또는 먼저 들어온 클라이언트) */
		Leader,
		NonLeader,
	};

	bool TakeSnapshot(FAstralPartyFlowSnapshot& Out) const;
	bool IsSettled(const FAstralPartyFlowSnapshot& Snap, const TCHAR* Map, int32 NumPlayers) const;

	/** 처음 허브에 모였을 때 — 기준값을 적고 역할을 정한다. 실패하면 false */
	bool RecordBase(const FAstralPartyFlowSnapshot& Snap);

	/** 이동 뒤 번호 · 방장이 그대로인가 (시임리스 이월). 아니면 Fail 하고 false */
	bool CheckKept(const FAstralPartyFlowSnapshot& Snap, const TCHAR* Where);

	void TickFlow(const FAstralPartyFlowSnapshot& Snap);
	void TickLeaderLeaves(const FAstralPartyFlowSnapshot& Snap);

	/** 서버 · 리슨 호스트는 클라이언트가 다 나갈 때까지(또는 제한 시간) 남는다 */
	void TickLinger(const FAstralPartyFlowSnapshot& Snap, bool bWaitForOthersToLeave);

	void Advance();
	double StageAge() const;
	void Pass();
	void Fail(const FString& Reason);
	void Finish(int32 ExitCode);

	static const TCHAR* RoleName(ERole InRole);

	bool bLeaderLeavesScenario = false;
	int32 NumPlayers = 0;
	double TimeoutSeconds = 300.0;

	ERole Role = ERole::Unknown;
	int32 Stage = 0;
	double StartTime = 0.0;
	double StageStartTime = 0.0;

	/** 허브에 처음 모였을 때의 스냅샷 */
	TArray<int32> BaseIds;
	int32 BaseLeaderId = INDEX_NONE;
	int32 BaseMyId = 0;

	bool bReadyLogged = false;
	bool bWasConnected = false;
	bool bResultLogged = false;
	bool bFinished = false;
};
