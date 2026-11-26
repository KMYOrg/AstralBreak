#pragma once

#include "CoreMinimal.h"
#include "AstralChainTracker.generated.h"

/** 체인의 단계 — 복제 상태(FAstralChainState)와 판정 구조체(FAstralChainTracker)가 같이 쓴다 */
UENUM(BlueprintType)
enum class EAstralChainPhase : uint8
{
	/** 체인 없음 */
	None,

	/** 열림 — 마감 전까지 다른 사람의 오의를 받는다 */
	Open,

	/** 2명 이상으로 닫힘 — 참가자들의 오의 연출이 끝나면 버스트 피해가 나간다. 그 사이 들어온 오의는 다음 체인의 첫 번째다 */
	Burst,
};

/** 판정 값 — 전부 잠정 (설계 Docs/Design/m4-ult-chain.md §3). 원본은 UAstralChainBurstComponent 의 프로퍼티다 */
struct FAstralChainRules
{
	/** 마감 = 마지막 등록 + 이 값 */
	double WindowSeconds = 6.0;

	/** 서버는 마감 뒤 이만큼 더 받는다 — 마감 직전에 누른 입력이 지연으로 늦게 도착해도 인정 */
	double GraceSeconds = 0.25;

	/** 이 인원이 차면 바로 닫는다 */
	int32 MaxParticipants = 4;

	/** 닫힐 때 이 인원 이상이면 버스트 */
	int32 MinBurstParticipants = 2;
};

enum class EAstralChainRegisterResult : uint8
{
	/** 체인이 없어서 새로 열었다 */
	Opened,

	/** 열려 있는 체인에 들어갔다 */
	Joined,

	/** 이미 들어 있는 사람 — 무시 */
	Duplicate,

	/** 버스트가 나가는 중 — 다음 체인의 참가자로 대기 */
	QueuedForNext,
};

/**
 * 체인 버스트 판정 — 월드 없이 도는 순수 구조체 (설계 §3 의 규칙 8개, Automation 시험 대상).
 * 입력은 (참가자, 시각)이고 출력은 단계 · 참가자 · 마감 · 마지막 버스트다. 타이머 · 복제 · 피해는 UAstralChainBurstComponent 가 맡는다.
 *
 * 시각은 호출자가 주는 단조 증가 값(서버 월드 시간)이다. Register 는 들어오면서 먼저 Advance 를 하므로
 * 타이머가 늦게 돌아도 결과는 등록 시각만으로 정해진다.
 *
 * B 다듬기(설계 §3 끝): 등록 시각은 '오의를 누른 시각' 이 아니라 '오의가 끝난 시각' 이다. 누가 오의를 쓰는 동안에는
 * 열린 체인의 타이머를 멈추고(Pause), 그 오의가 맞혔으면 Register, 못 맞혔으면 Resume 으로 끝낸다 — 연출 중에는 마감이 오지 않는다.
 */
struct ASTRALBREAK_API FAstralChainTracker
{
	/**
	 * 오의 한 번을 등록한다 — Now 는 그 오의가 끝난 시각. 타이머가 멈춰 있었으면 먼저 남은 시간으로 되돌린 뒤 판정한다
	 * (새로 들어가면 마감을 다시 재고, 이미 들어 있던 사람이면 되돌린 마감이 그대로 남는다).
	 * AlivePartySize — 지금 살아 있는 파티 인원. 참가자가 min(MaxParticipants, AlivePartySize) 에 닿으면 바로 닫는다(등록 시점에만 본다)
	 */
	EAstralChainRegisterResult Register(int32 ParticipantId, double Now, int32 AlivePartySize, const FAstralChainRules& Rules);

	/** 시간만 흐른다 — 열린 체인이 마감 + 유예를 넘겼으면 닫는다. 닫았으면 true. 멈춰 있는 동안에는 닫지 않는다 */
	bool Advance(double Now, const FAstralChainRules& Rules);

	/**
	 * 타이머를 멈춘다 — 누가 오의를 쓰기 시작했다. 마감 + 유예가 이미 지났으면 먼저 닫는다(멈출 것이 없다).
	 * 열린 체인을 멈췄으면 true. 남은 시간은 음수일 수 있다(마감은 지났고 유예 안에서 시작한 시전)
	 */
	bool Pause(double Now, const FAstralChainRules& Rules);

	/** 멈춘 타이머를 멈출 때 남아 있던 시간으로 다시 돌린다 — 그 오의가 못 맞혔다. 멈춰 있지 않으면 아무 일도 없다 */
	void Resume(double Now);

	bool IsPaused() const { return bPaused; }

	/** 멈출 때 남아 있던 시간(초, 유예 제외) — IsPaused 일 때만 뜻이 있다 */
	double GetPausedRemaining() const { return PausedRemaining; }

	/**
	 * 버스트가 끝났다(피해를 넣었다) — LastBurst* 를 적고 체인을 비운다.
	 * 버스트 중 대기한 참가자가 있으면 그들로 다음 체인을 바로 연다(마감 = 그중 마지막 등록 + 윈도우). Burst 단계가 아니면 아무 일도 없다
	 */
	void FinishBurst(double Now, int32 AlivePartySize, const FAstralChainRules& Rules);

	EAstralChainPhase GetPhase() const { return Phase; }

	/** 체인 번호 — 열릴 때마다 1 씩 커진다. 0 = 아직 한 번도 열리지 않았다 */
	int32 GetChainId() const { return ChainId; }

	/** 등록 순서대로. None 이면 비어 있다 */
	const TArray<int32>& GetParticipants() const { return Participants; }

	/** 마감 시각(유예 제외) — Open 일 때만 뜻이 있다 */
	double GetDeadline() const { return Deadline; }

	/** 서버가 실제로 닫는 시각 = 마감 + 유예 */
	double GetCloseTime(const FAstralChainRules& Rules) const { return Deadline + Rules.GraceSeconds; }

	int32 GetLastBurstChainId() const { return LastBurstChainId; }
	int32 GetLastBurstCount() const { return LastBurstCount; }

	/** 버스트 중 대기한 다음 체인 참가자 수 */
	int32 GetNumQueued() const { return Queued.Num(); }

private:
	struct FQueuedEntry
	{
		int32 ParticipantId = 0;
		double Time = 0.0;
	};

	void Open(int32 ParticipantId, double Now, const FAstralChainRules& Rules);
	void Close(const FAstralChainRules& Rules);
	void CloseIfFull(int32 AlivePartySize, const FAstralChainRules& Rules);

	EAstralChainPhase Phase = EAstralChainPhase::None;
	int32 ChainId = 0;
	TArray<int32> Participants;
	double Deadline = 0.0;
	bool bPaused = false;
	double PausedRemaining = 0.0;
	int32 LastBurstChainId = 0;
	int32 LastBurstCount = 0;
	TArray<FQueuedEntry> Queued;
};
