// 로비 규칙 순수 함수 시험 — 월드 의존이 없어 -ExecCmds="Automation RunTests AstralBreak.Lobby" 로 돈다
// (설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ③ · 'Phase 3-4 결과')

#include "Misc/AutomationTest.h"
#include "GameModes/AstralLobbyRules.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	struct FMemberSpec
	{
		int32 PlayerId = 0;
		bool bReady = false;
		bool bBot = false;
		bool bSpectator = false;
	};

	/** Members 와 요청한 사람 · 허브 상태로 스냅숏을 만든다. 목록 = { RaidMap } */
	FAstralLobbySnapshot MakeSnapshot(const TArray<FMemberSpec>& Specs, int32 RequesterIndex, bool bInHub = true, const FString& SelectedRaid = FString())
	{
		FAstralLobbySnapshot Snapshot;
		for (const FMemberSpec& Spec : Specs)
		{
			FAstralLobbyMember& Member = Snapshot.Members.AddDefaulted_GetRef();
			Member.Party.PlayerId = Spec.PlayerId;
			Member.Party.bIsBot = Spec.bBot;
			Member.Party.bIsSpectator = Spec.bSpectator;
			Member.bIsReady = Spec.bReady;
		}
		Snapshot.RequesterIndex = RequesterIndex;
		Snapshot.bInHub = bInHub;
		if (bInHub)
		{
			Snapshot.SelectedRaid = SelectedRaid;
			Snapshot.AllowedRaids = { TEXT("RaidMap") };
		}
		return Snapshot;
	}

	FMemberSpec Player(int32 PlayerId, bool bReady = false) { return { PlayerId, bReady, false, false }; }
	FMemberSpec Bot(int32 PlayerId, bool bReady = false) { return { PlayerId, bReady, true, false }; }
	FMemberSpec Spectator(int32 PlayerId, bool bReady = false) { return { PlayerId, bReady, false, true }; }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralLobbyRulesTest, "AstralBreak.Lobby.Rules", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralLobbyRulesTest::RunTest(const FString& Parameters)
{
	using namespace AstralLobby;
	using E = EAstralLobbyDenial;
	const auto Name = [](E Denial) { return FString(LexToString(Denial)); };
	const FString RaidMap = TEXT("RaidMap");

	// 준비 — 막는 규칙이 없다: 허브 밖(레이드 · 시험 맵의 신호) · 방장 아님 · 명단에 없음 모두 None
	{
		TestEqual(TEXT("ready: hub, non-leader"), Name(CheckReady(MakeSnapshot({ Player(256), Player(257) }, 1))), Name(E::None));
		TestEqual(TEXT("ready: outside the hub"), Name(CheckReady(MakeSnapshot({ Player(256), Player(257) }, 1, /*bInHub*/ false))), Name(E::None));
		TestEqual(TEXT("ready: empty snapshot (no GameState)"), Name(CheckReady(FAstralLobbySnapshot())), Name(E::None));
	}

	// 고르기 — 방장 아님이 먼저(서버 거절 로그를 세는 시험이 이 순서에 기댄다)
	{
		const TArray<FMemberSpec> Two = { Player(256), Player(257) };
		TestEqual(TEXT("select: non-leader, allowed map"), Name(CheckSelect(MakeSnapshot(Two, 1), RaidMap)), Name(E::NotLeader));
		TestEqual(TEXT("select: non-leader, map outside the list -> still NotLeader first"), Name(CheckSelect(MakeSnapshot(Two, 1), TEXT("CombatTestMap"))), Name(E::NotLeader));
		TestEqual(TEXT("select: non-leader outside the hub -> NotLeader first"), Name(CheckSelect(MakeSnapshot(Two, 1, false), RaidMap)), Name(E::NotLeader));
		TestEqual(TEXT("select: leader outside the hub"), Name(CheckSelect(MakeSnapshot(Two, 0, false), RaidMap)), Name(E::NotInHub));
		TestEqual(TEXT("select: leader, other map"), Name(CheckSelect(MakeSnapshot(Two, 0), TEXT("CombatTestMap"))), Name(E::RaidNotAllowed));
		TestEqual(TEXT("select: leader, option injection"), Name(CheckSelect(MakeSnapshot(Two, 0), TEXT("RaidMap?game=/Script/Engine.GameModeBase"))), Name(E::RaidNotAllowed));
		TestEqual(TEXT("select: leader, other case"), Name(CheckSelect(MakeSnapshot(Two, 0), TEXT("raidmap"))), Name(E::RaidNotAllowed));
		TestEqual(TEXT("select: leader, empty name"), Name(CheckSelect(MakeSnapshot(Two, 0), FString())), Name(E::RaidNotAllowed));
		TestEqual(TEXT("select: leader, allowed"), Name(CheckSelect(MakeSnapshot(Two, 0), RaidMap)), Name(E::None));
		TestEqual(TEXT("select: requester not in the list"), Name(CheckSelect(MakeSnapshot(Two, INDEX_NONE), RaidMap)), Name(E::NotLeader));
		TestEqual(TEXT("select: empty snapshot"), Name(CheckSelect(FAstralLobbySnapshot(), RaidMap)), Name(E::NotLeader));

		// 방장 = 파티원 중 PlayerId 최소 — 더 작은 번호의 봇 · 관전자 · 번호 없는 항목은 방장이 아니다
		const TArray<FMemberSpec> Mixed = { Bot(250), Spectator(251), Player(0), Player(258), Player(257) };
		TestEqual(TEXT("leader skips bot/spectator/unnumbered"), SelectLeaderIndex(MakeSnapshot(Mixed, 4)), 4);
		TestEqual(TEXT("select: the real leader (257)"), Name(CheckSelect(MakeSnapshot(Mixed, 4), RaidMap)), Name(E::None));
		TestEqual(TEXT("select: a spectator with a smaller id is not the leader"), Name(CheckSelect(MakeSnapshot(Mixed, 1), RaidMap)), Name(E::NotLeader));

		// 방장이 나가면 인계 코드 없이 다음 사람
		TestEqual(TEXT("select: next leader after the leader left"), Name(CheckSelect(MakeSnapshot({ Player(258), Player(257) }, 1), RaidMap)), Name(E::None));
	}

	// 출정 — 방장 아님 → 허브 아님 → 목적지 미선택 → 목록에 없음 → 전원 준비 아님
	{
		TestEqual(TEXT("start: non-leader, nothing selected -> NotLeader first"), Name(CheckStart(MakeSnapshot({ Player(256), Player(257) }, 1))), Name(E::NotLeader));
		TestEqual(TEXT("start: leader outside the hub"), Name(CheckStart(MakeSnapshot({ Player(256, true), Player(257, true) }, 0, false))), Name(E::NotInHub));
		TestEqual(TEXT("start: leader, nothing selected"), Name(CheckStart(MakeSnapshot({ Player(256, true), Player(257, true) }, 0))), Name(E::NoRaidSelected));
		TestEqual(TEXT("start: leader, selected map no longer in the list"), Name(CheckStart(MakeSnapshot({ Player(256, true) }, 0, true, TEXT("CombatTestMap")))), Name(E::RaidNotAllowed));
		TestEqual(TEXT("start: someone not ready"), Name(CheckStart(MakeSnapshot({ Player(256, true), Player(257, false) }, 0, true, RaidMap))), Name(E::NotAllReady));
		TestEqual(TEXT("start: the leader is not ready"), Name(CheckStart(MakeSnapshot({ Player(256, false), Player(257, true) }, 0, true, RaidMap))), Name(E::NotAllReady));
		TestEqual(TEXT("start: everyone ready"), Name(CheckStart(MakeSnapshot({ Player(256, true), Player(257, true) }, 0, true, RaidMap))), Name(E::None));
		TestEqual(TEXT("start: alone and ready"), Name(CheckStart(MakeSnapshot({ Player(256, true) }, 0, true, RaidMap))), Name(E::None));

		// 명단 거르기 하나 — 준비 안 한 관전자 · 봇 · 번호 없는 항목은 출정을 막지 않는다(예전 AreAllPlayersReady 는 전원을 셌다)
		TestEqual(TEXT("start: an unready spectator does not block"), Name(CheckStart(MakeSnapshot({ Player(256, true), Spectator(257) }, 0, true, RaidMap))), Name(E::None));
		TestEqual(TEXT("start: an unready bot does not block"), Name(CheckStart(MakeSnapshot({ Player(256, true), Bot(0) }, 0, true, RaidMap))), Name(E::None));
		TestEqual(TEXT("start: an unnumbered entry does not block"), Name(CheckStart(MakeSnapshot({ Player(256, true), Player(0) }, 0, true, RaidMap))), Name(E::None));
	}

	// 전원 준비 — 파티원이 하나도 없으면 거짓, 같은 번호가 잠깐 겹치면(시임리스 교체) 앞쪽 하나만 센다
	{
		TestFalse(TEXT("all ready: nobody"), AreAllMembersReady(MakeSnapshot({}, INDEX_NONE)));
		TestFalse(TEXT("all ready: only a spectator"), AreAllMembersReady(MakeSnapshot({ Spectator(256, true) }, INDEX_NONE)));
		TestTrue(TEXT("all ready: duplicate id, earlier entry ready"), AreAllMembersReady(MakeSnapshot({ Player(256, true), Player(256, false) }, 0)));
		TestFalse(TEXT("all ready: duplicate id, earlier entry not ready"), AreAllMembersReady(MakeSnapshot({ Player(256, false), Player(256, true) }, 0)));
	}

	// 화면의 줄 — 파티원을 번호 순으로 최대 넷
	{
		const FAstralLobbySnapshot Snapshot = MakeSnapshot({ Player(260), Spectator(250), Player(257), Bot(251), Player(256), Player(259), Player(258) }, 0);
		TArray<int32> Ids;
		for (const int32 Index : SelectRowIndices(Snapshot, 4))
		{
			Ids.Add(Snapshot.Members[Index].Party.PlayerId);
		}
		TestEqual(TEXT("rows: party members by id, at most 4"), Ids, TArray<int32>({ 256, 257, 258, 259 }));
		TestEqual(TEXT("rows: none"), SelectRowIndices(MakeSnapshot({}, INDEX_NONE), 4).Num(), 0);
		TestEqual(TEXT("rows: no room"), SelectRowIndices(Snapshot, 0).Num(), 0);
	}

	// 허용 목록 — 정확히 같은 이름만
	{
		const TArray<FString> Allowed = { TEXT("RaidMap"), TEXT("RaidMap2") };
		TestTrue(TEXT("allowed: exact"), IsRaidAllowed(Allowed, TEXT("RaidMap2")));
		TestFalse(TEXT("allowed: case"), IsRaidAllowed(Allowed, TEXT("RAIDMAP")));
		TestFalse(TEXT("allowed: prefix"), IsRaidAllowed(Allowed, TEXT("Raid")));
		TestFalse(TEXT("allowed: empty"), IsRaidAllowed(Allowed, FString()));
		TestFalse(TEXT("allowed: empty list"), IsRaidAllowed({}, TEXT("RaidMap")));
	}

	// 글 — 까닭마다 있고, 서버 거절 글은 지금 상태의 글과 구별된다
	{
		TestTrue(TEXT("text: None is empty"), GetDenialText(E::None).IsEmpty() && GetRequestDeniedText(E::None).IsEmpty());
		for (const E Denial : { E::NotInHub, E::NotLeader, E::RaidNotAllowed, E::NoRaidSelected, E::NotAllReady })
		{
			const FString State = GetDenialText(Denial).ToString();
			const FString Denied = GetRequestDeniedText(Denial).ToString();
			TestFalse(*FString::Printf(TEXT("text: %s has a reason"), LexToString(Denial)), State.IsEmpty());
			TestTrue(*FString::Printf(TEXT("text: %s denied text differs and carries the reason"), LexToString(Denial)), Denied != State && Denied.Contains(State));
		}
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
