// 적 타깃 선정 순수 함수 테스트 — 월드 의존이 없어 Session Frontend / -ExecCmds="Automation RunTests AstralBreak.Enemy.SelectNearest"로 돈다

#include "Misc/AutomationTest.h"
#include "AI/AstralEnemyTargeting.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FAstralEnemyTargetCandidate MakeEnemyTargetCandidate(const FVector& Location, bool bDeadOrDying = false)
	{
		FAstralEnemyTargetCandidate Candidate;
		Candidate.Location = Location;
		Candidate.bDeadOrDying = bDeadOrDying;
		return Candidate;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemySelectNearestTest, "AstralBreak.Enemy.SelectNearest", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralEnemySelectNearestTest::RunTest(const FString& Parameters)
{
	using namespace AstralEnemyTargeting;

	const FVector Origin(100.0, 200.0, 0.0);

	// 가장 가까운 것 — 배열 순서에 의존하지 않는다
	{
		const TArray<FAstralEnemyTargetCandidate> Near = { MakeEnemyTargetCandidate(Origin + FVector(300.0, 0.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(900.0, 0.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(0.0, 600.0, 0.0)) };
		TestEqual(TEXT("nearest (first)"), SelectNearestIndex(Origin, Near), 0);

		const TArray<FAstralEnemyTargetCandidate> Shuffled = { MakeEnemyTargetCandidate(Origin + FVector(900.0, 0.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(0.0, 600.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(-300.0, 0.0, 0.0)) };
		TestEqual(TEXT("nearest (last)"), SelectNearestIndex(Origin, Shuffled), 2);

		// 원점 기준이 아니라 Origin 기준 — 원점에 더 가까운 후보가 뽑히지 않는다
		const TArray<FAstralEnemyTargetCandidate> OriginRelative = { MakeEnemyTargetCandidate(FVector::ZeroVector), MakeEnemyTargetCandidate(Origin + FVector(50.0, 0.0, 0.0)) };
		TestEqual(TEXT("distance is measured from Origin"), SelectNearestIndex(Origin, OriginRelative), 1);
	}

	// 혼자
	{
		const TArray<FAstralEnemyTargetCandidate> Single = { MakeEnemyTargetCandidate(Origin + FVector(5000.0, 0.0, 0.0)) };
		TestEqual(TEXT("single candidate"), SelectNearestIndex(Origin, Single), 0);
	}

	// 죽은 후보 제외 — 더 가까워도 뽑지 않는다
	{
		const TArray<FAstralEnemyTargetCandidate> DeadIsNearer = { MakeEnemyTargetCandidate(Origin + FVector(100.0, 0.0, 0.0), /*bDeadOrDying=*/true), MakeEnemyTargetCandidate(Origin + FVector(800.0, 0.0, 0.0)) };
		TestEqual(TEXT("dead candidate skipped even when nearer"), SelectNearestIndex(Origin, DeadIsNearer), 1);

		const TArray<FAstralEnemyTargetCandidate> DeadAtOrigin = { MakeEnemyTargetCandidate(Origin, true), MakeEnemyTargetCandidate(Origin + FVector(0.0, 0.0, 400.0)), MakeEnemyTargetCandidate(Origin + FVector(0.0, 300.0, 0.0)) };
		TestEqual(TEXT("dead at distance 0 skipped"), SelectNearestIndex(Origin, DeadAtOrigin), 2);
	}

	// 후보 없음 → INDEX_NONE
	{
		const TArray<FAstralEnemyTargetCandidate> Empty;
		TestEqual(TEXT("empty"), SelectNearestIndex(Origin, Empty), static_cast<int32>(INDEX_NONE));

		const TArray<FAstralEnemyTargetCandidate> AllDead = { MakeEnemyTargetCandidate(Origin + FVector(100.0, 0.0, 0.0), true), MakeEnemyTargetCandidate(Origin + FVector(200.0, 0.0, 0.0), true) };
		TestEqual(TEXT("everyone dead"), SelectNearestIndex(Origin, AllDead), static_cast<int32>(INDEX_NONE));
	}

	// 동률 — 앞쪽
	{
		const TArray<FAstralEnemyTargetCandidate> Tie = { MakeEnemyTargetCandidate(Origin + FVector(900.0, 0.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(400.0, 0.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(0.0, -400.0, 0.0)) };
		TestEqual(TEXT("tie -> earlier index"), SelectNearestIndex(Origin, Tie), 1);

		const TArray<FAstralEnemyTargetCandidate> TieAfterDead = { MakeEnemyTargetCandidate(Origin + FVector(400.0, 0.0, 0.0), true), MakeEnemyTargetCandidate(Origin + FVector(0.0, 400.0, 0.0)), MakeEnemyTargetCandidate(Origin + FVector(0.0, 0.0, 400.0)) };
		TestEqual(TEXT("tie among the living -> earlier living index"), SelectNearestIndex(Origin, TieAfterDead), 1);
	}

	// 높이도 거리에 든다 (3D)
	{
		const TArray<FAstralEnemyTargetCandidate> Height = { MakeEnemyTargetCandidate(Origin + FVector(300.0, 0.0, 1000.0)), MakeEnemyTargetCandidate(Origin + FVector(600.0, 0.0, 0.0)) };
		TestEqual(TEXT("height counts"), SelectNearestIndex(Origin, Height), 1);
	}

	return true;
}

// ─── 단위 B — 가중 뽑기 · 위협 규칙 (설계 §9 검증 계획 B1 · B2) ───

namespace
{
	FAstralEnemyThreatCandidate MakeEnemyThreatCandidate(const FVector& Location, float RecentDamage = 0.f, float Hostility = 100.f)
	{
		FAstralEnemyThreatCandidate Candidate;
		Candidate.Location = Location;
		Candidate.RecentDamage = RecentDamage;
		Candidate.Hostility = Hostility;
		return Candidate;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemySelectWeightedTest, "AstralBreak.Enemy.SelectWeighted", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralEnemySelectWeightedTest::RunTest(const FString& Parameters)
{
	using namespace AstralEnemyTargeting;

	// 경계값 — 구간은 [앞, 뒤). 300 : 100 이면 0.75 가 경계다
	{
		const TArray<float> Weights = { 300.f, 100.f };
		TestEqual(TEXT("roll 0 -> first"), SelectWeightedIndex(Weights, 0.f), 0);
		TestEqual(TEXT("roll just under the boundary -> first"), SelectWeightedIndex(Weights, 0.7499f), 0);
		TestEqual(TEXT("roll on the boundary -> second"), SelectWeightedIndex(Weights, 0.75f), 1);
		TestEqual(TEXT("roll 1 -> last"), SelectWeightedIndex(Weights, 1.f), 1);
		TestEqual(TEXT("roll below 0 is clamped"), SelectWeightedIndex(Weights, -3.f), 0);
		TestEqual(TEXT("roll above 1 is clamped"), SelectWeightedIndex(Weights, 7.f), 1);
	}

	// 가중치 0 은 뽑히지 않는다 — 앞 · 가운데 · 뒤 어디에 있어도
	{
		const TArray<float> ZeroFirst = { 0.f, 50.f, 50.f };
		TestEqual(TEXT("zero weight first, roll 0"), SelectWeightedIndex(ZeroFirst, 0.f), 1);

		const TArray<float> ZeroMiddle = { 50.f, 0.f, 50.f };
		TestEqual(TEXT("zero weight middle, roll on the seam"), SelectWeightedIndex(ZeroMiddle, 0.5f), 2);

		const TArray<float> ZeroLast = { 50.f, 50.f, 0.f };
		TestEqual(TEXT("zero weight last, roll 1"), SelectWeightedIndex(ZeroLast, 1.f), 1);

		const TArray<float> Negative = { -40.f, 10.f };
		TestEqual(TEXT("negative weight counts as zero"), SelectWeightedIndex(Negative, 0.f), 1);
	}

	// 전부 0 · 빈 배열 · 한 명
	{
		const TArray<float> AllZero = { 0.f, 0.f, 0.f };
		TestEqual(TEXT("all zero"), SelectWeightedIndex(AllZero, 0.5f), static_cast<int32>(INDEX_NONE));

		const TArray<float> Empty;
		TestEqual(TEXT("empty"), SelectWeightedIndex(Empty, 0.5f), static_cast<int32>(INDEX_NONE));

		const TArray<float> Single = { 12.f };
		TestEqual(TEXT("single, roll 0"), SelectWeightedIndex(Single, 0.f), 0);
		TestEqual(TEXT("single, roll 1"), SelectWeightedIndex(Single, 1.f), 0);
	}

	// 분포 — 시드 고정 2만 회가 가중치 비율(60 % · 30 % · 0 % · 10 %) 안에 든다
	{
		const TArray<float> Weights = { 300.f, 150.f, 0.f, 50.f };
		constexpr int32 NumDraws = 20000;
		int32 Counts[4] = { 0, 0, 0, 0 };
		bool bAllValid = true;

		FRandomStream Stream(20261111);
		for (int32 Draw = 0; Draw < NumDraws; ++Draw)
		{
			const int32 Index = SelectWeightedIndex(Weights, Stream.FRand());
			if (Index >= 0 && Index < 4)
			{
				++Counts[Index];
			}
			else
			{
				bAllValid = false;
			}
		}

		TestTrue(TEXT("every draw returns a valid index"), bAllValid);
		TestEqual(TEXT("zero weight is never drawn"), Counts[2], 0);
		TestTrue(TEXT("60 % share within 1.5 points"), FMath::Abs(static_cast<double>(Counts[0]) / NumDraws - 0.60) <= 0.015);
		TestTrue(TEXT("30 % share within 1.5 points"), FMath::Abs(static_cast<double>(Counts[1]) / NumDraws - 0.30) <= 0.015);
		TestTrue(TEXT("10 % share within 1.5 points"), FMath::Abs(static_cast<double>(Counts[3]) / NumDraws - 0.10) <= 0.015);
		AddInfo(FString::Printf(TEXT("distribution over %d draws: %d / %d / %d / %d"), NumDraws, Counts[0], Counts[1], Counts[2], Counts[3]));
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyThreatRulesTest, "AstralBreak.Enemy.ThreatRules", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralEnemyThreatRulesTest::RunTest(const FString& Parameters)
{
	using namespace AstralEnemyTargeting;

	const FVector Origin(100.0, 200.0, 0.0);
	const FVector NearLocation = Origin + FVector(300.0, 0.0, 0.0);
	const FVector FarLocation = Origin + FVector(0.0, 2000.0, 0.0);

	// 가중치 산술 — 설계 §9 ① 의 잠정값 예시 (적대심 100 · 피해 가중 2)
	{
		TestEqual(TEXT("sole hitter: 100 x (1 + 2 x 1)"), ComputeThreatWeight(100.f, 2.f, 1.f), 300.f);
		TestEqual(TEXT("no damage: 100"), ComputeThreatWeight(100.f, 2.f, 0.f), 100.f);
		TestEqual(TEXT("half share: 200"), ComputeThreatWeight(100.f, 2.f, 0.5f), 200.f);
		TestEqual(TEXT("Provoke +50 at half share: 300"), ComputeThreatWeight(150.f, 2.f, 0.5f), 300.f);
		TestEqual(TEXT("damage weight 0 ignores the share"), ComputeThreatWeight(100.f, 0.f, 1.f), 100.f);
		TestEqual(TEXT("hostility 0 -> weight 0"), ComputeThreatWeight(0.f, 2.f, 1.f), 0.f);
		TestEqual(TEXT("negative hostility counts as 0"), ComputeThreatWeight(-50.f, 2.f, 1.f), 0.f);
		TestEqual(TEXT("share is clamped to 1"), ComputeThreatWeight(100.f, 2.f, 4.f), 300.f);
	}

	// 시각 비교 — 유지 시간 · 제외 · 재추첨 간격이 전부 이 함수다
	{
		TestTrue(TEXT("hold 6 s: 5.9 s after acquiring -> still held"), IsWithinDuration(10.0, 15.9, 6.0));
		TestFalse(TEXT("hold 6 s: exactly 6 s -> expired"), IsWithinDuration(10.0, 16.0, 6.0));
		TestFalse(TEXT("hold 6 s: 7 s -> expired"), IsWithinDuration(10.0, 17.0, 6.0));
		TestTrue(TEXT("exclusion 5 s: 4.99 s -> still excluded"), IsWithinDuration(3.0, 7.99, 5.0));
		TestFalse(TEXT("exclusion 5 s: 5.01 s -> candidate again"), IsWithinDuration(3.0, 8.01, 5.0));
		TestFalse(TEXT("negative start = never"), IsWithinDuration(-1.0, 0.5, 6.0));
		TestFalse(TEXT("zero duration never holds"), IsWithinDuration(10.0, 10.0, 0.0));
		TestTrue(TEXT("start at world time 0 counts"), IsWithinDuration(0.0, 1.0, 3.0));
	}

	// 피해 창 — 창 밖 기록은 세지 않는다
	{
		TArray<FAstralEnemyDamageEntry> Entries;
		Entries.Add({ 0.5, 40.f });
		Entries.Add({ 9.0, 25.f });
		Entries.Add({ 10.2, 5.f });
		TestEqual(TEXT("window 10 s at t 10.4: every entry counts"), SumDamageInWindow(Entries, 10.4, 10.0), 70.f);
		TestEqual(TEXT("window 10 s at t 12: the 0.5 s entry is out"), SumDamageInWindow(Entries, 12.0, 10.0), 30.f);
		TestEqual(TEXT("window 10 s at t 30: nothing"), SumDamageInWindow(Entries, 30.0, 10.0), 0.f);

		const TArray<FAstralEnemyDamageEntry> NoEntries;
		TestEqual(TEXT("no entries"), SumDamageInWindow(NoEntries, 5.0, 10.0), 0.f);
	}

	// 피해 기록 없음 → 추첨하지 않고 가장 가까운 후보 (Roll 과 무관)
	{
		const TArray<FAstralEnemyThreatCandidate> NoDamage = { MakeEnemyThreatCandidate(FarLocation), MakeEnemyThreatCandidate(NearLocation) };
		TestEqual(TEXT("no damage, roll 0 -> nearest"), SelectThreatIndex(Origin, NoDamage, 2.f, 0.f), 1);
		TestEqual(TEXT("no damage, roll 0.99 -> nearest"), SelectThreatIndex(Origin, NoDamage, 2.f, 0.99f), 1);

		// 높은 적대심도 기록이 없으면 거리를 못 이긴다
		const TArray<FAstralEnemyThreatCandidate> HostileFar = { MakeEnemyThreatCandidate(FarLocation, 0.f, 900.f), MakeEnemyThreatCandidate(NearLocation) };
		TestEqual(TEXT("no damage, hostile far candidate -> still nearest"), SelectThreatIndex(Origin, HostileFar, 2.f, 0.f), 1);
	}

	// 점유율 추첨 — 혼자 때린 사람 75 % · 안 때린 사람 25 %, 반반 50 % · 50 %, Provoke +50 은 60 % · 40 %
	{
		const TArray<FAstralEnemyThreatCandidate> SoleHitter = { MakeEnemyThreatCandidate(FarLocation, 40.f), MakeEnemyThreatCandidate(NearLocation) };
		TestEqual(TEXT("sole hitter: roll 0.74 -> hitter"), SelectThreatIndex(Origin, SoleHitter, 2.f, 0.74f), 0);
		TestEqual(TEXT("sole hitter: roll 0.76 -> the other"), SelectThreatIndex(Origin, SoleHitter, 2.f, 0.76f), 1);

		// 대조 — 피해 가중 0 이면 같은 Roll 에서 때린 사람이 뽑히지 않는다 (50 % · 50 %)
		TestEqual(TEXT("damage weight 0: roll 0.6 -> the other"), SelectThreatIndex(Origin, SoleHitter, 0.f, 0.6f), 1);
		TestEqual(TEXT("damage weight 2: roll 0.6 -> hitter"), SelectThreatIndex(Origin, SoleHitter, 2.f, 0.6f), 0);

		const TArray<FAstralEnemyThreatCandidate> EvenHitters = { MakeEnemyThreatCandidate(FarLocation, 30.f), MakeEnemyThreatCandidate(NearLocation, 30.f) };
		TestEqual(TEXT("even hitters: roll 0.49 -> first"), SelectThreatIndex(Origin, EvenHitters, 2.f, 0.49f), 0);
		TestEqual(TEXT("even hitters: roll 0.51 -> second"), SelectThreatIndex(Origin, EvenHitters, 2.f, 0.51f), 1);

		const TArray<FAstralEnemyThreatCandidate> Provoke = { MakeEnemyThreatCandidate(FarLocation, 30.f, 150.f), MakeEnemyThreatCandidate(NearLocation, 30.f) };
		TestEqual(TEXT("Provoke +50: roll 0.59 -> provoker"), SelectThreatIndex(Origin, Provoke, 2.f, 0.59f), 0);
		TestEqual(TEXT("Provoke +50: roll 0.61 -> the other"), SelectThreatIndex(Origin, Provoke, 2.f, 0.61f), 1);
	}

	// 자격 — 죽은 후보 · 제외 중인 후보 · 적대심 0 은 어느 경로에서도 뽑히지 않는다
	{
		FAstralEnemyThreatCandidate DeadHitter = MakeEnemyThreatCandidate(NearLocation, 80.f);
		DeadHitter.bDeadOrDying = true;
		FAstralEnemyThreatCandidate ExcludedHitter = MakeEnemyThreatCandidate(NearLocation, 80.f);
		ExcludedHitter.bExcluded = true;
		const FAstralEnemyThreatCandidate ZeroHostility = MakeEnemyThreatCandidate(NearLocation, 80.f, 0.f);
		const FAstralEnemyThreatCandidate Other = MakeEnemyThreatCandidate(FarLocation);

		TestFalse(TEXT("dead is not eligible"), IsThreatEligible(DeadHitter));
		TestFalse(TEXT("excluded is not eligible"), IsThreatEligible(ExcludedHitter));
		TestFalse(TEXT("hostility 0 is not eligible"), IsThreatEligible(ZeroHostility));
		TestTrue(TEXT("a plain candidate is eligible"), IsThreatEligible(Other));

		// 자격 없는 후보의 피해는 점유율에도 들지 않는다 — 남은 후보는 기록이 없으므로 가까운 사람 규칙으로 간다
		const TArray<FAstralEnemyThreatCandidate> WithDead = { DeadHitter, Other };
		const TArray<FAstralEnemyThreatCandidate> WithExcluded = { ExcludedHitter, Other };
		const TArray<FAstralEnemyThreatCandidate> WithZeroHostility = { ZeroHostility, Other };
		TestEqual(TEXT("dead hitter skipped"), SelectThreatIndex(Origin, WithDead, 2.f, 0.f), 1);
		TestEqual(TEXT("excluded hitter skipped"), SelectThreatIndex(Origin, WithExcluded, 2.f, 0.f), 1);
		TestEqual(TEXT("hostility 0 hitter skipped"), SelectThreatIndex(Origin, WithZeroHostility, 2.f, 0.f), 1);

		// 추첨 경로에서도 — 둘 다 때렸고 한쪽이 자격이 없으면 Roll 이 무엇이든 나머지
		const FAstralEnemyThreatCandidate OtherHitter = MakeEnemyThreatCandidate(FarLocation, 20.f);
		const TArray<FAstralEnemyThreatCandidate> ExcludedAndHitter = { ExcludedHitter, OtherHitter };
		const TArray<FAstralEnemyThreatCandidate> ZeroAndHitter = { ZeroHostility, OtherHitter };
		TestEqual(TEXT("excluded hitter never drawn (roll 0)"), SelectThreatIndex(Origin, ExcludedAndHitter, 2.f, 0.f), 1);
		TestEqual(TEXT("hostility 0 never drawn (roll 0)"), SelectThreatIndex(Origin, ZeroAndHitter, 2.f, 0.f), 1);

		// 후보 없음
		const TArray<FAstralEnemyThreatCandidate> NobodyEligible = { DeadHitter, ExcludedHitter, ZeroHostility };
		const TArray<FAstralEnemyThreatCandidate> NoCandidates;
		TestEqual(TEXT("nobody eligible"), SelectThreatIndex(Origin, NobodyEligible, 2.f, 0.5f), static_cast<int32>(INDEX_NONE));
		TestEqual(TEXT("empty"), SelectThreatIndex(Origin, NoCandidates, 2.f, 0.5f), static_cast<int32>(INDEX_NONE));
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
