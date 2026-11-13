#pragma once

#include "CoreMinimal.h"
#include "GauntletTestController.h"
#include "AstralPartyFlowTestController.generated.h"

class AAstralCombatCharacter;
class AAstralEnemySpawner;
class UAstralEnemySpawnerTestListener;
struct FAstralPartyFlowSnapshot;

/**
 * 파티 흐름 네트워크 시험 — 별도 프로세스 구성 (설계 Docs/Design/m3-enemy-ai.md §7-2 ②)
 *
 * 프로세스마다 하나씩 뜬다: `-gauntlet=AstralPartyFlowTest -AstralPartyPlayers=N [-AstralPartyScenario=Flow|LeaderLeaves|EnemyCombat|RaidClear]`.
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

	/**
	 * 적 전투 (설계 §8 검증 계획 A9) — CombatTestMap 에서 바로 시작한다.
	 * 클라이언트 하나(-AstralEnemySpawner)가 SpawnEnemy 로 적을 부르고, 모든 프로세스가 '맞은 히어로와 그 HP' 를 적는다(HIT 줄 — 실행 스크립트가 서로 대조한다).
	 * 클라이언트들이 본 것을 준비 신호로 알리면 권위 프로세스(Dedicated 서버 · 리슨 호스트)가 적을 죽이고, 모두가 적 폰이 사라진 것을 본다(GONE 줄)
	 */
	void TickEnemyCombat(const FAstralPartyFlowSnapshot& Snap);

	/**
	 * 레이드 전멸 (설계 §12 E2) — 허브에서 시작해 선택 · 준비 · 시작 → RaidMap → 구역 진입 → 수호병 3 → 전투 → 처치 → 전멸 → 제거 → 허브 복귀.
	 * 권위 프로세스(Dedicated 서버 · 리슨 호스트)가 히어로를 구역으로 옮기고 수호병을 죽인다. 클라이언트는 본 것을 준비 신호로 알린다:
	 * 켬(A: 도착 · 적 0) → 끔(B: 수호병 3) → 켬(C: 수호병 0). 서버는 A 를 다 본 뒤에만 옮기고 B 를 다 본 뒤에만 죽이며, 방장은 C 를 다 본 뒤에만 돌아간다.
	 * 처치는 히어로의 공격이 아니라 서버의 DamageSelf 다 — 첫 피해를 본 틱에 곧바로 죽여 히어로 HP 가 그 값에서 멈춘다(HEROES 줄 — 실행 스크립트가 서로 대조한다)
	 */
	void TickRaidClear(const FAstralPartyFlowSnapshot& Snap);

	/** 레이드 전멸 — 수호병 폰이 실제로 없어질 때(서버). 틱이 아니라 이벤트로 세어, 방장의 복귀가 서버의 다음 틱보다 먼저 와도 놓치지 않는다 */
	UFUNCTION()
	void HandleRaidGuardianDestroyed(AActor* DestroyedActor);

	/** 이 프로세스가 처음 대기하는 맵 — 시나리오마다 다르다 */
	const TCHAR* StartMap() const;

	/** 서버 · 리슨 호스트는 클라이언트가 다 나갈 때까지(또는 제한 시간) 남는다 */
	void TickLinger(const FAstralPartyFlowSnapshot& Snap, bool bWaitForOthersToLeave);

	void Advance();

	/** 역할마다 앞부분의 단계 수가 다른 시나리오가 같은 번호에서 다시 만나게 한다 */
	void JumpToStage(int32 NewStage);
	double StageAge() const;
	void Pass();
	void Fail(const FString& Reason);
	void Finish(int32 ExitCode);

	static const TCHAR* RoleName(ERole InRole);

	bool bLeaderLeavesScenario = false;
	bool bEnemyCombatScenario = false;
	bool bRaidClearScenario = false;

	// ─── 레이드 전멸 — 권위 프로세스만 쓴다. 월드의 액터는 약하게 잡는다(이동 때 옛 월드를 붙들지 않게) ───

	TWeakObjectPtr<AAstralEnemySpawner> RaidSpawner;
	TArray<TWeakObjectPtr<AAstralCombatCharacter>> RaidGuardians;

	/** 스포너의 OnCleared 횟수 */
	UPROPERTY(Transient)
	TObjectPtr<UAstralEnemySpawnerTestListener> RaidClearedListener;

	int32 NumRaidGuardiansDestroyed = 0;
	double RaidKillTime = 0.0;
	double RaidGoneTime = 0.0;

	/** 마지막 수호병이 없어진 순간의 히어로 HP — 그 틱이 이동 뒤에 올 수 있어 이벤트에서 적어 둔다 */
	FString RaidHeroesAtGone;

	/** 적 전투 — 이 프로세스(클라이언트)가 SpawnEnemy 를 부른다. 실행 스크립트가 클라이언트 하나에만 준다 */
	bool bEnemySpawner = false;
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
