// 체인 버스트 판정 구조체 시험 — 월드 의존이 없다 (설계 Docs/Design/m4-ult-chain.md §3 의 규칙 8개)
//
// 참가자는 PlayerId(엔진이 256 부터 준다), 시각은 초. 값은 구조체 기본값(윈도우 6.0 · 유예 0.25 · 최대 4명)이고 전부 잠정이다 —
// 시험은 값이 아니라 규칙을 본다(경계는 Rules 에서 계산한다).

#include "Misc/AutomationTest.h"
#include "GameModes/AstralChainTracker.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralChainTrackerTest, "AstralBreak.Chain.Tracker", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralChainTrackerTest::RunTest(const FString& Parameters)
{
	const FAstralChainRules Rules;
	const double Window = Rules.WindowSeconds;
	const double Grace = Rules.GraceSeconds;
	constexpr int32 A = 256, B = 257, C = 258, D = 259;
	constexpr int32 Party = 4;

	const auto PhaseOf = [](const FAstralChainTracker& Tracker) { return static_cast<int32>(Tracker.GetPhase()); };
	constexpr int32 None = static_cast<int32>(EAstralChainPhase::None);
	constexpr int32 Open = static_cast<int32>(EAstralChainPhase::Open);
	constexpr int32 Burst = static_cast<int32>(EAstralChainPhase::Burst);
	const auto ResultOf = [](EAstralChainRegisterResult Result) { return static_cast<int32>(Result); };

	// 규칙 1 · 5 — 첫 오의가 연다. 혼자면 마감 뒤 조용히 끝난다(버스트 없음)
	{
		FAstralChainTracker Tracker;
		TestEqual(TEXT("fresh: phase none"), PhaseOf(Tracker), None);
		TestEqual(TEXT("fresh: chain id 0"), Tracker.GetChainId(), 0);

		TestEqual(TEXT("solo: first ult opens"), ResultOf(Tracker.Register(A, 10.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Opened));
		TestEqual(TEXT("solo: phase open"), PhaseOf(Tracker), Open);
		TestEqual(TEXT("solo: chain id 1"), Tracker.GetChainId(), 1);
		TestEqual(TEXT("solo: one participant"), Tracker.GetParticipants().Num(), 1);
		TestEqual(TEXT("solo: deadline = registration + window"), Tracker.GetDeadline(), 10.0 + Window);

		TestFalse(TEXT("solo: still open at the deadline"), Tracker.Advance(10.0 + Window, Rules));
		TestFalse(TEXT("solo: still open at deadline + grace (inclusive)"), Tracker.Advance(10.0 + Window + Grace, Rules));
		TestTrue(TEXT("solo: closes just after deadline + grace"), Tracker.Advance(10.0 + Window + Grace + 0.001, Rules));
		TestEqual(TEXT("solo: closes quietly"), PhaseOf(Tracker), None);
		TestEqual(TEXT("solo: no participants left"), Tracker.GetParticipants().Num(), 0);
		TestEqual(TEXT("solo: no burst recorded"), Tracker.GetLastBurstChainId(), 0);
		TestEqual(TEXT("solo: no burst count"), Tracker.GetLastBurstCount(), 0);
	}

	// 규칙 2 · 5 — 2인: 이어지면 마감을 다시 재고, 닫힐 때 버스트
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		TestEqual(TEXT("2p: second joins"), ResultOf(Tracker.Register(B, 4.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Joined));
		TestEqual(TEXT("2p: deadline re-measured from the last registration"), Tracker.GetDeadline(), 4.0 + Window);
		TestEqual(TEXT("2p: order kept"), Tracker.GetParticipants(), TArray<int32>({ A, B }));

		TestFalse(TEXT("2p: open past the first deadline"), Tracker.Advance(Window + Grace + 1.0, Rules));
		TestTrue(TEXT("2p: closes after the new deadline + grace"), Tracker.Advance(4.0 + Window + Grace + 0.001, Rules));
		TestEqual(TEXT("2p: phase burst"), PhaseOf(Tracker), Burst);
		TestEqual(TEXT("2p: participants kept during burst"), Tracker.GetParticipants().Num(), 2);
		TestEqual(TEXT("2p: burst not recorded until it finishes"), Tracker.GetLastBurstChainId(), 0);

		Tracker.FinishBurst(4.0 + Window + Grace + 0.5, Party, Rules);
		TestEqual(TEXT("2p: phase none after the burst"), PhaseOf(Tracker), None);
		TestEqual(TEXT("2p: last burst chain id"), Tracker.GetLastBurstChainId(), 1);
		TestEqual(TEXT("2p: last burst count"), Tracker.GetLastBurstCount(), 2);
		TestEqual(TEXT("2p: participants cleared"), Tracker.GetParticipants().Num(), 0);
	}

	// 3인 — 4인 파티에서 셋이면 마감까지 기다린다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		Tracker.Register(B, 1.0, Party, Rules);
		Tracker.Register(C, 2.0, Party, Rules);
		TestEqual(TEXT("3p: still open with three of four"), PhaseOf(Tracker), Open);
		TestTrue(TEXT("3p: closes on the deadline"), Tracker.Advance(2.0 + Window + Grace + 0.001, Rules));
		TestEqual(TEXT("3p: phase burst"), PhaseOf(Tracker), Burst);
		Tracker.FinishBurst(9.0, Party, Rules);
		TestEqual(TEXT("3p: last burst count"), Tracker.GetLastBurstCount(), 3);
	}

	// 규칙 4 — 4명이 차면 바로 닫는다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		Tracker.Register(B, 0.5, Party, Rules);
		Tracker.Register(C, 1.0, Party, Rules);
		TestEqual(TEXT("4p: the fourth joins"), ResultOf(Tracker.Register(D, 1.5, Party, Rules)), ResultOf(EAstralChainRegisterResult::Joined));
		TestEqual(TEXT("4p: full chain closes at once"), PhaseOf(Tracker), Burst);
		TestEqual(TEXT("4p: four participants"), Tracker.GetParticipants(), TArray<int32>({ A, B, C, D }));
		Tracker.FinishBurst(3.5, Party, Rules);
		TestEqual(TEXT("4p: last burst count"), Tracker.GetLastBurstCount(), 4);
		TestEqual(TEXT("4p: phase none"), PhaseOf(Tracker), None);
	}

	// 규칙 4 — 살아 있는 파티 전원이면 바로 닫는다 (등록 시점의 인원으로 본다)
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, /*AlivePartySize=*/2, Rules);
		TestEqual(TEXT("alive 2: open after the first"), PhaseOf(Tracker), Open);
		Tracker.Register(B, 1.0, 2, Rules);
		TestEqual(TEXT("alive 2: both alive players in -> closes at once"), PhaseOf(Tracker), Burst);

		// 혼자 살아 있으면 첫 오의에서 조용히 닫힌다 — 열린 체인을 붙들지 않는다
		FAstralChainTracker Solo;
		TestEqual(TEXT("alive 1: the ult still opens a chain"), ResultOf(Solo.Register(A, 0.0, 1, Rules)), ResultOf(EAstralChainRegisterResult::Opened));
		TestEqual(TEXT("alive 1: closes quietly at once"), PhaseOf(Solo), None);
		TestEqual(TEXT("alive 1: chain id consumed"), Solo.GetChainId(), 1);
		TestEqual(TEXT("alive 1: no burst"), Solo.GetLastBurstChainId(), 0);

		// 최대치를 넘는 인원은 최대치로 본다
		FAstralChainTracker Big;
		Big.Register(A, 0.0, 99, Rules);
		Big.Register(B, 0.1, 99, Rules);
		Big.Register(C, 0.2, 99, Rules);
		TestEqual(TEXT("alive 99: three is not full"), PhaseOf(Big), Open);
		Big.Register(D, 0.3, 99, Rules);
		TestEqual(TEXT("alive 99: max participants closes"), PhaseOf(Big), Burst);
	}

	// 규칙 3 — 같은 사람의 두 번째 등록은 무시한다. 마감도 그대로
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		TestEqual(TEXT("dup: second registration ignored"), ResultOf(Tracker.Register(A, 3.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Duplicate));
		TestEqual(TEXT("dup: one participant"), Tracker.GetParticipants().Num(), 1);
		TestEqual(TEXT("dup: deadline unchanged"), Tracker.GetDeadline(), Window);
		TestTrue(TEXT("dup: closes on the original deadline"), Tracker.Advance(Window + Grace + 0.001, Rules));
		TestEqual(TEXT("dup: one participant is no burst"), PhaseOf(Tracker), None);
	}

	// 규칙 7 — 마감 · 유예 경계. Register 는 타이머가 돌지 않았어도 시각만으로 판정한다
	{
		// 마감 정각
		FAstralChainTracker AtDeadline;
		AtDeadline.Register(A, 0.0, Party, Rules);
		TestEqual(TEXT("edge: at the deadline joins"), ResultOf(AtDeadline.Register(B, Window, Party, Rules)), ResultOf(EAstralChainRegisterResult::Joined));

		// 유예 안 — 받는다. 마감은 도착 시각부터 다시
		FAstralChainTracker InGrace;
		InGrace.Register(A, 0.0, Party, Rules);
		TestEqual(TEXT("edge: inside the grace joins"), ResultOf(InGrace.Register(B, Window + Grace, Party, Rules)), ResultOf(EAstralChainRegisterResult::Joined));
		TestEqual(TEXT("edge: same chain"), InGrace.GetChainId(), 1);
		TestEqual(TEXT("edge: deadline from the late arrival"), InGrace.GetDeadline(), Window + Grace + Window);

		// 유예 밖 — 앞 체인은 혼자라 조용히 닫히고, 늦은 오의가 새 체인을 연다
		FAstralChainTracker Late;
		Late.Register(A, 0.0, Party, Rules);
		TestEqual(TEXT("edge: past the grace opens a new chain"), ResultOf(Late.Register(B, Window + Grace + 0.01, Party, Rules)), ResultOf(EAstralChainRegisterResult::Opened));
		TestEqual(TEXT("edge: chain id 2"), Late.GetChainId(), 2);
		TestEqual(TEXT("edge: only the late one"), Late.GetParticipants(), TArray<int32>({ B }));
		TestEqual(TEXT("edge: the lone first chain did not burst"), Late.GetLastBurstChainId(), 0);

		// 유예 밖 + 앞 체인이 2명 — 앞 체인은 버스트로 넘어가고 늦은 오의는 다음 체인의 대기자
		FAstralChainTracker LateAfterTwo;
		LateAfterTwo.Register(A, 0.0, Party, Rules);
		LateAfterTwo.Register(B, 1.0, Party, Rules);
		TestEqual(TEXT("edge: late after a 2-chain is queued"), ResultOf(LateAfterTwo.Register(C, 1.0 + Window + Grace + 0.01, Party, Rules)), ResultOf(EAstralChainRegisterResult::QueuedForNext));
		TestEqual(TEXT("edge: the 2-chain is bursting"), PhaseOf(LateAfterTwo), Burst);
		TestEqual(TEXT("edge: the late one is not in the bursting chain"), LateAfterTwo.GetParticipants(), TArray<int32>({ A, B }));
	}

	// 규칙 8 — 버스트 중 들어온 오의는 다음 체인의 첫 번째다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, 2, Rules);
		Tracker.Register(B, 1.0, 2, Rules); // 살아 있는 2명 전원 -> Burst
		TestEqual(TEXT("next: bursting"), PhaseOf(Tracker), Burst);

		TestEqual(TEXT("next: an ult during the burst is queued"), ResultOf(Tracker.Register(C, 2.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::QueuedForNext));
		TestEqual(TEXT("next: the same one again is ignored"), ResultOf(Tracker.Register(C, 2.2, Party, Rules)), ResultOf(EAstralChainRegisterResult::Duplicate));
		TestEqual(TEXT("next: a participant of the bursting chain can be queued too"), ResultOf(Tracker.Register(A, 2.5, Party, Rules)), ResultOf(EAstralChainRegisterResult::QueuedForNext));
		TestEqual(TEXT("next: bursting chain unchanged"), Tracker.GetParticipants(), TArray<int32>({ A, B }));
		TestEqual(TEXT("next: two queued"), Tracker.GetNumQueued(), 2);

		Tracker.FinishBurst(3.0, Party, Rules);
		TestEqual(TEXT("next: first burst recorded"), Tracker.GetLastBurstChainId(), 1);
		TestEqual(TEXT("next: first burst count"), Tracker.GetLastBurstCount(), 2);
		TestEqual(TEXT("next: the next chain is open"), PhaseOf(Tracker), Open);
		TestEqual(TEXT("next: chain id 2"), Tracker.GetChainId(), 2);
		TestEqual(TEXT("next: queued ults are its participants in order"), Tracker.GetParticipants(), TArray<int32>({ C, A }));
		TestEqual(TEXT("next: deadline from the last queued ult"), Tracker.GetDeadline(), 2.5 + Window);
		TestEqual(TEXT("next: queue emptied"), Tracker.GetNumQueued(), 0);

		TestTrue(TEXT("next: closes on its own deadline"), Tracker.Advance(2.5 + Window + Grace + 0.001, Rules));
		TestEqual(TEXT("next: second burst"), PhaseOf(Tracker), Burst);
		Tracker.FinishBurst(10.0, Party, Rules);
		TestEqual(TEXT("next: second burst recorded"), Tracker.GetLastBurstChainId(), 2);
	}

	// 규칙 8 — 대기한 오의가 하나뿐이고 버스트가 길었으면, 다음 체인은 열리자마자 마감이 지나 조용히 끝난다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, 2, Rules);
		Tracker.Register(B, 1.0, 2, Rules);
		Tracker.Register(C, 2.0, Party, Rules);
		Tracker.FinishBurst(2.0 + Window + Grace + 1.0, Party, Rules);
		TestEqual(TEXT("stale next: closed quietly"), PhaseOf(Tracker), None);
		TestEqual(TEXT("stale next: chain id still consumed"), Tracker.GetChainId(), 2);
		TestEqual(TEXT("stale next: last burst is the first chain"), Tracker.GetLastBurstChainId(), 1);
	}

	// ─── B 다듬기 — 누가 오의를 쓰는 동안 타이머가 멈춘다. 등록 시각은 오의가 끝난 시각이다 ───

	// 멈춤 → 못 맞힘: 멈출 때 남아 있던 시간으로 다시 돈다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules); // 마감 = Window
		TestFalse(TEXT("pause: not paused at first"), Tracker.IsPaused());

		TestTrue(TEXT("pause: an open chain pauses"), Tracker.Pause(2.0, Rules));
		TestTrue(TEXT("pause: paused"), Tracker.IsPaused());
		TestEqual(TEXT("pause: remaining = deadline - now"), Tracker.GetPausedRemaining(), Window - 2.0);
		TestEqual(TEXT("pause: still open"), PhaseOf(Tracker), Open);

		// 연출이 마감을 넘겨도 닫히지 않는다
		TestFalse(TEXT("pause: does not close while paused, long past the deadline"), Tracker.Advance(Window + Grace + 10.0, Rules));
		TestEqual(TEXT("pause: still open past the deadline"), PhaseOf(Tracker), Open);

		Tracker.Resume(20.0);
		TestFalse(TEXT("resume: not paused"), Tracker.IsPaused());
		TestEqual(TEXT("resume: deadline = now + what was left"), Tracker.GetDeadline(), 20.0 + (Window - 2.0));
		TestEqual(TEXT("resume: participants untouched"), Tracker.GetParticipants(), TArray<int32>({ A }));
		TestFalse(TEXT("resume: open until the new deadline + grace"), Tracker.Advance(20.0 + (Window - 2.0) + Grace, Rules));
		TestTrue(TEXT("resume: closes after the new deadline + grace"), Tracker.Advance(20.0 + (Window - 2.0) + Grace + 0.001, Rules));
		TestEqual(TEXT("resume: the lone chain ends quietly"), PhaseOf(Tracker), None);
	}

	// 멈춤 → 맞힘: 끝난 시각으로 들어가고 마감을 그 시각부터 다시 잰다 (연출 시간이 창을 깎지 않는다)
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		Tracker.Pause(Window - 0.5, Rules); // 마감 0.5초 전에 누름
		const double EndTime = Window + 3.0; // 연출이 마감 + 유예를 넘겨 끝남
		TestEqual(TEXT("pause+hit: joins the paused chain"), ResultOf(Tracker.Register(B, EndTime, Party, Rules)), ResultOf(EAstralChainRegisterResult::Joined));
		TestEqual(TEXT("pause+hit: same chain"), Tracker.GetChainId(), 1);
		TestFalse(TEXT("pause+hit: no longer paused"), Tracker.IsPaused());
		TestEqual(TEXT("pause+hit: deadline = end of the ult + window"), Tracker.GetDeadline(), EndTime + Window);
		TestEqual(TEXT("pause+hit: both in"), Tracker.GetParticipants(), TArray<int32>({ A, B }));
	}

	// 멈춤 → 넷째가 맞힘: 바로 닫힌다. 닫히면 멈춤도 풀린다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		Tracker.Register(B, 1.0, Party, Rules);
		Tracker.Register(C, 2.0, Party, Rules);
		Tracker.Pause(3.0, Rules);
		Tracker.Register(D, 5.0, Party, Rules);
		TestEqual(TEXT("pause+full: closes at once"), PhaseOf(Tracker), Burst);
		TestFalse(TEXT("pause+full: not paused after closing"), Tracker.IsPaused());
	}

	// 멈춤 → 이미 들어 있는 사람이 또 맞힘(규칙 3): 참가는 무시하고, 타이머는 남아 있던 시간으로 다시 돈다 — 마감을 새로 재지 않는다
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		Tracker.Pause(4.0, Rules);
		TestEqual(TEXT("pause+dup: ignored"), ResultOf(Tracker.Register(A, 9.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Duplicate));
		TestFalse(TEXT("pause+dup: timer runs again"), Tracker.IsPaused());
		TestEqual(TEXT("pause+dup: deadline = now + what was left, not a fresh window"), Tracker.GetDeadline(), 9.0 + (Window - 4.0));
		TestEqual(TEXT("pause+dup: one participant"), Tracker.GetParticipants().Num(), 1);
	}

	// 유예 안에서 시작한 시전: 남은 시간이 음수인 채 멈춘다. 못 맞히면 남은 유예만큼만 더 돌고 닫히고, 맞히면 들어간다
	{
		FAstralChainTracker Missed;
		Missed.Register(A, 0.0, Party, Rules);
		Missed.Register(B, 1.0, Party, Rules); // 마감 = 1 + Window
		const double PauseTime = 1.0 + Window + Grace * 0.4; // 마감은 지났고 유예는 남았다
		TestTrue(TEXT("grace pause: still pauses inside the grace"), Missed.Pause(PauseTime, Rules));
		TestTrue(TEXT("grace pause: remaining is negative"), Missed.GetPausedRemaining() < 0.0);
		Missed.Resume(50.0);
		TestFalse(TEXT("grace miss: open for the rest of the grace"), Missed.Advance(50.0 + Grace * 0.5, Rules));
		TestTrue(TEXT("grace miss: closes once the rest of the grace is over"), Missed.Advance(50.0 + Grace * 0.7, Rules));
		TestEqual(TEXT("grace miss: the two already in still burst"), PhaseOf(Missed), Burst);

		FAstralChainTracker Hit;
		Hit.Register(A, 0.0, Party, Rules);
		Hit.Pause(Window + Grace * 0.4, Rules);
		TestEqual(TEXT("grace hit: joins"), ResultOf(Hit.Register(B, 30.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Joined));
		TestEqual(TEXT("grace hit: same chain"), Hit.GetChainId(), 1);
	}

	// 멈출 것이 없는 경우 — 체인이 없거나, 마감 + 유예를 이미 넘겼거나, 버스트 중
	{
		FAstralChainTracker NoChain;
		TestFalse(TEXT("pause on none: nothing to pause"), NoChain.Pause(1.0, Rules));
		TestFalse(TEXT("pause on none: not paused"), NoChain.IsPaused());
		NoChain.Resume(2.0);
		TestEqual(TEXT("resume on none: nothing"), PhaseOf(NoChain), None);
		// 그 오의가 맞히면 끝난 시각에 새 체인을 연다
		TestEqual(TEXT("pause on none: the ult opens a chain when it ends"), ResultOf(NoChain.Register(A, 3.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Opened));
		TestEqual(TEXT("pause on none: deadline from the end of the ult"), NoChain.GetDeadline(), 3.0 + Window);

		FAstralChainTracker Expired;
		Expired.Register(A, 0.0, Party, Rules);
		TestFalse(TEXT("pause past the grace: the old chain closes instead"), Expired.Pause(Window + Grace + 0.01, Rules));
		TestEqual(TEXT("pause past the grace: closed"), PhaseOf(Expired), None);
		TestEqual(TEXT("pause past the grace: the ult then opens a new chain"), ResultOf(Expired.Register(B, Window + Grace + 2.0, Party, Rules)), ResultOf(EAstralChainRegisterResult::Opened));
		TestEqual(TEXT("pause past the grace: chain id 2"), Expired.GetChainId(), 2);

		FAstralChainTracker Bursting;
		Bursting.Register(A, 0.0, 2, Rules);
		Bursting.Register(B, 1.0, 2, Rules);
		TestFalse(TEXT("pause on burst: nothing to pause"), Bursting.Pause(1.5, Rules));
		TestEqual(TEXT("pause on burst: still bursting"), PhaseOf(Bursting), Burst);
	}

	// 멈춘 채 다시 멈춤 요청 — 남은 시간은 처음 멈춘 때의 것 그대로
	{
		FAstralChainTracker Tracker;
		Tracker.Register(A, 0.0, Party, Rules);
		Tracker.Pause(1.0, Rules);
		TestTrue(TEXT("pause twice: still paused"), Tracker.Pause(3.0, Rules));
		TestEqual(TEXT("pause twice: remaining from the first pause"), Tracker.GetPausedRemaining(), Window - 1.0);
	}

	// Burst 가 아닐 때 FinishBurst 는 아무 일도 하지 않는다
	{
		FAstralChainTracker Tracker;
		Tracker.FinishBurst(1.0, Party, Rules);
		TestEqual(TEXT("finish on none: nothing"), Tracker.GetLastBurstChainId(), 0);
		Tracker.Register(A, 2.0, Party, Rules);
		Tracker.FinishBurst(3.0, Party, Rules);
		TestEqual(TEXT("finish on open: still open"), PhaseOf(Tracker), Open);
		TestEqual(TEXT("finish on open: no burst"), Tracker.GetLastBurstChainId(), 0);
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
