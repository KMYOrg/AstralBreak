#include "AstralChainTracker.h"

EAstralChainRegisterResult FAstralChainTracker::Register(int32 ParticipantId, double Now, int32 AlivePartySize, const FAstralChainRules& Rules)
{
	if (bPaused)
	{
		// 멈춰 있던 타이머 — 그 사이 마감은 오지 않았다. 남은 시간으로 되돌려 놓고 판정한다(여기서 닫지 않는다 — 이 오의는 열린 체인의 것이다)
		Resume(Now);
	}
	else
	{
		// 타이머보다 등록이 먼저 온 경우에도 마감이 지난 체인은 여기서 닫힌다 — 결과가 호출 순서가 아니라 시각으로 정해진다
		Advance(Now, Rules);
	}

	switch (Phase)
	{
	case EAstralChainPhase::Open:
		// 규칙 3 — 같은 사람의 두 번째 등록은 무시한다. 마감도 다시 재지 않는다
		if (Participants.Contains(ParticipantId))
		{
			return EAstralChainRegisterResult::Duplicate;
		}
		// 규칙 2 — 참가자에 더하고 마감을 다시 잰다 (유예 안에 도착한 등록도 도착 시각부터)
		Participants.Add(ParticipantId);
		Deadline = Now + Rules.WindowSeconds;
		CloseIfFull(AlivePartySize, Rules);
		return EAstralChainRegisterResult::Joined;

	case EAstralChainPhase::Burst:
		// 규칙 8 — 버스트가 나가는 동안 들어온 오의는 다음 체인의 것이다. 나가는 중인 체인의 참가자였어도 같다
		if (Queued.ContainsByPredicate([ParticipantId](const FQueuedEntry& Entry) { return Entry.ParticipantId == ParticipantId; }))
		{
			return EAstralChainRegisterResult::Duplicate;
		}
		Queued.Add({ ParticipantId, Now });
		return EAstralChainRegisterResult::QueuedForNext;

	case EAstralChainPhase::None:
	default:
		// 규칙 1
		Open(ParticipantId, Now, Rules);
		CloseIfFull(AlivePartySize, Rules);
		return EAstralChainRegisterResult::Opened;
	}
}

bool FAstralChainTracker::Advance(double Now, const FAstralChainRules& Rules)
{
	// 규칙 7 — 마감 + 유예 '까지' 받는다. 그 시각을 넘긴 뒤에만 닫는다. 멈춰 있는 동안(누가 오의를 쓰는 중)에는 닫지 않는다
	if (Phase == EAstralChainPhase::Open && !bPaused && Now > GetCloseTime(Rules))
	{
		Close(Rules);
		return true;
	}
	return false;
}

bool FAstralChainTracker::Pause(double Now, const FAstralChainRules& Rules)
{
	if (bPaused)
	{
		return true;
	}

	// 이미 마감 + 유예를 넘겼으면 닫힌다 — 그 뒤의 오의는 새 체인의 것이다
	Advance(Now, Rules);
	if (Phase != EAstralChainPhase::Open)
	{
		return false;
	}

	bPaused = true;
	PausedRemaining = Deadline - Now;
	return true;
}

void FAstralChainTracker::Resume(double Now)
{
	if (!bPaused)
	{
		return;
	}

	bPaused = false;
	Deadline = Now + PausedRemaining;
	PausedRemaining = 0.0;
}

void FAstralChainTracker::FinishBurst(double Now, int32 AlivePartySize, const FAstralChainRules& Rules)
{
	if (Phase != EAstralChainPhase::Burst)
	{
		return;
	}

	LastBurstChainId = ChainId;
	LastBurstCount = Participants.Num();
	Phase = EAstralChainPhase::None;
	Participants.Reset();

	if (Queued.IsEmpty())
	{
		return;
	}

	// 대기한 사람들로 다음 체인 — 마감은 그들 가운데 마지막 등록부터 잰다
	const TArray<FQueuedEntry> Pending = MoveTemp(Queued);
	Queued.Reset();

	Open(Pending[0].ParticipantId, Pending[0].Time, Rules);
	for (int32 Index = 1; Index < Pending.Num(); ++Index)
	{
		Participants.Add(Pending[Index].ParticipantId);
		Deadline = Pending[Index].Time + Rules.WindowSeconds;
	}

	CloseIfFull(AlivePartySize, Rules);
	Advance(Now, Rules);
}

void FAstralChainTracker::Open(int32 ParticipantId, double Now, const FAstralChainRules& Rules)
{
	++ChainId;
	Phase = EAstralChainPhase::Open;
	Participants.Reset();
	Participants.Add(ParticipantId);
	Deadline = Now + Rules.WindowSeconds;
}

void FAstralChainTracker::Close(const FAstralChainRules& Rules)
{
	bPaused = false;
	PausedRemaining = 0.0;

	// 규칙 5 — 2명 이상이면 버스트, 아니면 조용히 끝난다
	if (Participants.Num() >= Rules.MinBurstParticipants)
	{
		Phase = EAstralChainPhase::Burst;
	}
	else
	{
		Phase = EAstralChainPhase::None;
		Participants.Reset();
	}
}

void FAstralChainTracker::CloseIfFull(int32 AlivePartySize, const FAstralChainRules& Rules)
{
	// 규칙 4 — 4명(또는 살아 있는 파티 전원)이면 바로 닫는다
	const int32 FullCount = FMath::Clamp(AlivePartySize, 1, FMath::Max(Rules.MaxParticipants, 1));
	if (Phase == EAstralChainPhase::Open && Participants.Num() >= FullCount)
	{
		Close(Rules);
	}
}
