// 방장 선정 순수 함수 테스트 — 월드 의존이 없어 Session Frontend / -ExecCmds="Automation RunTests AstralBreak.Party"로 돈다

#include "Misc/AutomationTest.h"
#include "GameModes/AstralPartyStatics.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FAstralPartyMember MakeMember(int32 PlayerId, bool bIsBot = false, bool bIsSpectator = false)
	{
		FAstralPartyMember Member;
		Member.PlayerId = PlayerId;
		Member.bIsBot = bIsBot;
		Member.bIsSpectator = bIsSpectator;
		return Member;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralPartySelectLeaderTest, "AstralBreak.Party.SelectLeader", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralPartySelectLeaderTest::RunTest(const FString& Parameters)
{
	using namespace AstralParty;

	// 최소 ID — 엔진 PlayerId 는 256 부터 로그인 순서대로 커진다. 배열 순서에 의존하지 않는다
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(256), MakeMember(257), MakeMember(258) };
		TestEqual(TEXT("min id (first)"), SelectLeaderIndex(Members), 0);

		const TArray<FAstralPartyMember> Shuffled = { MakeMember(258), MakeMember(256), MakeMember(257) };
		TestEqual(TEXT("min id (shuffled)"), SelectLeaderIndex(Shuffled), 1);

		const TArray<FAstralPartyMember> Reversed = { MakeMember(258), MakeMember(257), MakeMember(256) };
		TestEqual(TEXT("min id (last)"), SelectLeaderIndex(Reversed), 2);
	}

	// 혼자 — 그 사람이 방장
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(300) };
		TestEqual(TEXT("single member"), SelectLeaderIndex(Members), 0);
	}

	// 봇 · 관전자 제외 — ID 가 더 작아도 방장이 아니다
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(256, /*bIsBot=*/true), MakeMember(257, false, /*bIsSpectator=*/true), MakeMember(258), MakeMember(259) };
		TestEqual(TEXT("bot and spectator skipped"), SelectLeaderIndex(Members), 2);

		// PlayerId 를 받지 않은 봇(기본값 0)도 같다
		const TArray<FAstralPartyMember> UnregisteredBot = { MakeMember(300), MakeMember(0, /*bIsBot=*/true) };
		TestEqual(TEXT("unregistered bot (id 0) skipped"), SelectLeaderIndex(UnregisteredBot), 0);
	}

	// 후보 없음 → INDEX_NONE
	{
		const TArray<FAstralPartyMember> Empty;
		TestEqual(TEXT("empty"), SelectLeaderIndex(Empty), static_cast<int32>(INDEX_NONE));

		const TArray<FAstralPartyMember> NoHumans = { MakeMember(256, true), MakeMember(257, false, true) };
		TestEqual(TEXT("only bot and spectator"), SelectLeaderIndex(NoHumans), static_cast<int32>(INDEX_NONE));
	}

	// 방장 이탈 — 인계 코드 없이 다음으로 작은 ID 가 방장. 나갔다 돌아온 사람은 새(더 큰) ID 라 되찾지 못한다
	{
		TArray<FAstralPartyMember> Members = { MakeMember(256), MakeMember(258), MakeMember(257) };
		TestEqual(TEXT("before leave"), SelectLeaderIndex(Members), 0);

		Members.RemoveAt(0);
		TestEqual(TEXT("leader left -> next smallest (257)"), SelectLeaderIndex(Members), 1);

		Members.Add(MakeMember(259));
		TestEqual(TEXT("old leader rejoined with new id -> still 257"), SelectLeaderIndex(Members), 1);

		// 방장이 아닌 사람이 나가면 방장은 그대로
		Members.RemoveAt(0);
		TestEqual(TEXT("non-leader left -> leader kept (257)"), SelectLeaderIndex(Members), 0);
	}

	// 동률 — 앞쪽 (시임리스 교체 한 호출 안에서 옛 · 새 PlayerState 가 같은 ID 로 잠깐 겹친다)
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(257), MakeMember(256), MakeMember(256) };
		TestEqual(TEXT("tie -> earlier index"), SelectLeaderIndex(Members), 1);
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralPartyAlliesTest, "AstralBreak.Party.Allies", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralPartyAlliesTest::RunTest(const FString& Parameters)
{
	using namespace AstralParty;
	const auto Ids = [](const TArray<FAstralPartyMember>& Members, const TArray<int32>& Indices)
	{
		TArray<int32> Out;
		for (const int32 Index : Indices)
		{
			Out.Add(Members[Index].PlayerId);
		}
		return Out;
	};

	// 나를 빼고 번호 순 — 배열 순서에 기대지 않는다
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(259), MakeMember(256), MakeMember(258), MakeMember(257) };
		TestEqual(TEXT("seen by 257"), Ids(Members, SelectAllyIndices(Members, 257, 3)), TArray<int32>({ 256, 258, 259 }));
		TestEqual(TEXT("seen by 256"), Ids(Members, SelectAllyIndices(Members, 256, 3)), TArray<int32>({ 257, 258, 259 }));
		TestEqual(TEXT("at most MaxAllies"), Ids(Members, SelectAllyIndices(Members, 256, 2)), TArray<int32>({ 257, 258 }));
		TestEqual(TEXT("no room"), SelectAllyIndices(Members, 256, 0).Num(), 0);
	}

	// 혼자 · 비어 있음
	{
		const TArray<FAstralPartyMember> Alone = { MakeMember(256) };
		TestEqual(TEXT("alone"), SelectAllyIndices(Alone, 256, 3).Num(), 0);
		TestEqual(TEXT("empty"), SelectAllyIndices({}, 256, 3).Num(), 0);
	}

	// 봇 · 관전자 · 번호를 못 받은 항목은 동료가 아니다
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(0), MakeMember(260, true), MakeMember(261, false, true), MakeMember(256), MakeMember(257) };
		TestEqual(TEXT("bot, spectator and unnumbered skipped"), Ids(Members, SelectAllyIndices(Members, 256, 3)), TArray<int32>({ 257 }));
	}

	// 내 번호를 아직 모르면(0) 모두 남으로 보인다 — 부르는 쪽(화면)이 그때는 동료를 그리지 않는다
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(256), MakeMember(257) };
		TestEqual(TEXT("unknown self"), SelectAllyIndices(Members, 0, 3).Num(), 2);
	}

	// 같은 번호가 잠깐 겹침(시임리스 교체) — 하나만, 앞쪽
	{
		const TArray<FAstralPartyMember> Members = { MakeMember(256), MakeMember(258), MakeMember(257), MakeMember(258) };
		const TArray<int32> Allies = SelectAllyIndices(Members, 256, 3);
		TestEqual(TEXT("duplicate id once"), Ids(Members, Allies), TArray<int32>({ 257, 258 }));
		TestEqual(TEXT("duplicate keeps the earlier entry"), Allies.Last(), 1);
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
