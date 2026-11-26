#pragma once

#include "CoreMinimal.h"
#include "AstralPartyFlowTestController.h"
#include "GameFramework/Info.h"
#include "GameModes/AstralChainBurstComponent.h"
#include "AstralChainBurstTestController.generated.h"

class AAstralCharacter;
class AAstralCombatCharacter;
class AAstralEnemySpawner;
class AAstralPlayerState;
class UAbilitySystemComponent;

/** 서버가 시키는 일 */
UENUM()
enum class EAstralChainOrderKind : uint8
{
	None,

	/** 이어 쓰기 — 채우고, 차단이 풀려 있으면 바로 누른다 */
	Cast,

	/** 함께 누르기 — 자기 화면의 남은 시간이 TogetherRemaining 이하가 되면 누른다(경합) */
	Together,

	/** 마감에 누르기 — 자기 화면의 남은 시간이 LastMomentRemaining 이하가 되면 누른다 */
	LastMoment,

	/** 끝 */
	Done,
};

USTRUCT()
struct FAstralChainOrder
{
	GENERATED_BODY()

	/** 지시 번호 — 자리마다 번호 하나에 한 번만 움직인다 */
	UPROPERTY()
	int32 Serial = 0;

	UPROPERTY()
	EAstralChainOrderKind Kind = EAstralChainOrderKind::None;

	UPROPERTY()
	TArray<int32> PlayerIds;
};

/**
 * 체인 별도 프로세스 시험의 지시 — 서버가 세우는 복제 액터 하나 (설계 Docs/Design/m4-ult-chain.md §6 '단위 E 설계' ③).
 * bIsReady 는 기존 시나리오처럼 클라이언트 → 서버 신호로만 쓰고, 누구 차례인가는 여기로 보낸다
 */
UCLASS(NotPlaceable, Transient)
class AAstralNetTestDirector : public AInfo
{
	GENERATED_BODY()

public:
	AAstralNetTestDirector();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** 서버 — 다음 지시를 낸다 */
	void Issue(EAstralChainOrderKind Kind, const TArray<int32>& PlayerIds);

	UPROPERTY(Replicated)
	FAstralChainOrder Order;

	/** 오의를 맞힐 적 — 자리마다 이쪽으로 몸을 돌린다 */
	UPROPERTY(Replicated)
	TObjectPtr<AAstralCombatCharacter> Target;
};

/**
 * 체인 버스트 별도 프로세스 시험 (설계 Docs/Design/m4-ult-chain.md §6 '단위 E 설계') — `-gauntlet=AstralChainBurstTest -AstralPartyScenario=ChainBurst|ChainDeadline`.
 *
 *   ChainBurst     허브 → RaidMap → 동료 HUD 확인 → 수호병 3(AI 를 떼고 HP 를 크게)을 둘러싸고 한 명씩 이어 쓴다 → 버스트 → 둘째 사람이 나간다 → 동료 줄이 당겨진다
 *   ChainDeadline  CombatTestMap · 클라이언트마다 다른 지연(실행 스크립트가 엔진 패킷 흉내를 건다) — 함께 누르기 1판 + 사람마다 마감에 누르기 1판
 *
 * 프로세스마다 두 몫이 있다: 권위(Dedicated 서버 · 리슨 호스트 — 지시를 내고 결과를 적는다)와 자리(로컬 플레이어가 있는 곳 — 지시대로 누르고 본 것을 적는다). 리슨 호스트는 둘 다다.
 * 서버가 받은 시각 · 상태 변화는 폴링이 아니라 OnChainStateChanged 안에서 적는다. 프로세스 사이 대조는 실행 스크립트(run_party_flow.py)가 한다
 */
UCLASS()
class UAstralChainBurstTestController : public UAstralPartyFlowTestController
{
	GENERATED_BODY()

public:
	virtual void OnInit() override;

protected:
	virtual void TickScenario(const FAstralPartyFlowSnapshot& Snap) override;
	virtual const TCHAR* StartMap() const override;

private:
	/** 체인 컴포넌트에 붙는다(월드마다 한 번). 아직 없으면 false */
	bool BindChain(const FAstralPartyFlowSnapshot& Snap);
	void HandleChainStateChanged(const FAstralChainState& NewState, const FAstralChainState& OldState);

	// ─── 권위 ───

	void TickAuthority(const FAstralPartyFlowSnapshot& Snap);

	/** 적을 세운다 — ChainBurst 는 스포너로 부른 수호병, ChainDeadline 은 시험이 세운 적 한 마리. 다 섰으면 true */
	bool PrepareEnemies(const FAstralPartyFlowSnapshot& Snap);
	bool PlaceHeroes(const FAstralPartyFlowSnapshot& Snap);
	bool MakeSturdy(const FAstralPartyFlowSnapshot& Snap);

	/** 지시를 내고 시전이 하나 끝나기를 기다리는 상태로 간다 */
	void IssueCast(EAstralChainOrderKind Kind, const TArray<int32>& PlayerIds);
	bool IsIssuedCastOver() const { return NumCastsEnded >= ExpectedCastsEnded; }

	void TickBurstAuthority(const FAstralPartyFlowSnapshot& Snap);
	void TickDeadlineAuthority(const FAstralPartyFlowSnapshot& Snap);

	/** 버스트가 나간 순간의 서버 값 — 기여자 · 맞은 적 · 가운데 적이 잃은 HP 와 잃었어야 할 HP */
	void LogBurstReport(const UWorld* World) const;

	/** Dedicated 서버가 보는 마지막 버스트 · 적 HP (자리의 BURST 줄과 대조한다) */
	void LogAuthorityBurst(const FAstralPartyFlowSnapshot& Snap) const;

	void AdvanceAuthority();
	double AuthorityAge() const;

	// ─── 자리 ───

	void TickSeat(const FAstralPartyFlowSnapshot& Snap);

	/** 지시 하나를 따른다 — 준비(채움 · 방향) → 때를 기다림 → 누름 → 결과를 적음 */
	void TickOrders(const FAstralPartyFlowSnapshot& Snap);
	void TickPress(const FAstralPartyFlowSnapshot& Snap);

	/** 체인이 도는 동안 자리에서 본 것 — 차단 태그 · 전투 HUD 숫자 · 배너 */
	void WatchSeat(const FAstralPartyFlowSnapshot& Snap);

	/** 동료 HUD 가 이 사람들(나를 뺀 PlayerId 순)과 맞는가. OutDescription = 본 것 한 줄 */
	bool CheckAllyRows(const FAstralPartyFlowSnapshot& Snap, FString& OutDescription) const;

	void AdvanceSeat();
	double SeatAge() const;

	AAstralNetTestDirector* FindDirector(const UWorld* World) const;

	bool bDeadlineScenario = false;

	TWeakObjectPtr<UAstralChainBurstComponent> Chain;

	// ─── 권위 프로세스만 쓴다 ───

	TWeakObjectPtr<AAstralNetTestDirector> Director;
	TWeakObjectPtr<AAstralEnemySpawner> Spawner;

	/** [0] = 오의를 맞힐 적 */
	TArray<TWeakObjectPtr<AAstralCombatCharacter>> Enemies;

	int32 AuthorityStage = 0;
	double AuthorityStageStart = 0.0;
	bool bAuthorityDone = false;

	/** 마지막으로 본 마감(서버 시각) — 닫힌 뒤에 도착한 시전이 얼마나 늦었는지 잰다 */
	double LastDeadline = 0.0;

	int32 NumCastsEnded = 0;
	int32 ExpectedCastsEnded = 0;

	/** 마지막 시전 — 시작할 때 적는다 */
	int32 LastCasterId = 0;
	double LastCastLeft = 0.0;
	bool bLastCastJoined = false;

	/** 이 지시 동안 서버에서 시전한 사람들 */
	TArray<int32> CastersThisOrder;

	/** 함께 누르기 — 서버에서 오의가 켜진 사람 · 사람별 가장 낮았던 게이지 */
	TSet<int32> ActiveDuringRace;
	TMap<int32, float> MinGaugeDuringRace;

	/** 체인을 잇는 차례 (ChainBurst: 남은 번호 순서, ChainDeadline: 경합 뒤 남은 사람) */
	TArray<int32> Pending;

	int32 Round = 0;
	int32 RoundChainId = 0;

	/** 적이 잃었어야 할 오의 피해의 합 */
	float ExpectedUltDamage = 0.f;

	// ─── 자리 ───

	int32 SeatStage = 0;
	double SeatStageStart = 0.0;
	bool bSeatDone = false;
	double BurstSeenTime = 0.0;

	FAstralChainOrder SeatOrder;
	int32 SeenSerial = 0;

	/** 0 = 할 일 없음, 1 = 준비, 2 = 때를 기다림, 3 = 누름 → 결과를 봄 */
	int32 OrderPhase = 0;
	bool bFillRequested = false;

	/** 이 지시 동안 도는 타이머를 한 번이라도 봤다 — 그 뒤 멈추거나 닫히면 때를 놓친 것이다 */
	bool bSawOpen = false;
	double PressTime = 0.0;
	bool bReleased = false;
	bool bSawActive = false;
	bool bSawCasting = false;
	bool bSawUltBlockedText = false;
	double ActiveEndTime = 0.0;

	TArray<int32> BlockedWhile;
	bool bBlockedByOwnCast = false;
	TArray<FString> ChainCounts;
	FString BannerCount;
};
