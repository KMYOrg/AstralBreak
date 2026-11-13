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

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyThreatDistanceSpreadTest, "AstralBreak.Enemy.ThreatDistanceSpread", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralEnemyThreatDistanceSpreadTest::RunTest(const FString& Parameters)
{
	using namespace AstralEnemyTargeting;

	constexpr float Tol = 0.001f;
	const FVector Origin(0.0, 0.0, 0.0);
	const FVector Near(400.0, 0.0, 0.0);
	const FVector Far(0.0, 800.0, 0.0);

	// 배수 — 거리: 가장 가까운 후보 (1 + 값)배, 두 배 멀면 (1 + 값 ÷ 2)배. 0 이면 1. 겹쳐 있으면(거리 0) 가장 가까운 것으로 본다
	TestEqual(TEXT("distance factor: nearest"), ComputeDistanceFactor(2.f, 400.0, 400.0), 3.f, Tol);
	TestEqual(TEXT("distance factor: twice as far"), ComputeDistanceFactor(2.f, 400.0, 800.0), 2.f, Tol);
	TestEqual(TEXT("distance factor: weight 0"), ComputeDistanceFactor(0.f, 400.0, 800.0), 1.f, Tol);
	TestEqual(TEXT("distance factor: distance 0"), ComputeDistanceFactor(2.f, 0.0, 0.0), 3.f, Tol);

	// 배수 — 분산: 다른 적 K 마리가 노리면 1 ÷ (1 + 값 × K)
	TestEqual(TEXT("spread factor: nobody else"), ComputeSpreadFactor(1.f, 0), 1.f, Tol);
	TestEqual(TEXT("spread factor: one other"), ComputeSpreadFactor(1.f, 1), 0.5f, Tol);
	TestEqual(TEXT("spread factor: two others"), ComputeSpreadFactor(1.f, 2), 1.f / 3.f, Tol);
	TestEqual(TEXT("spread factor: weight 0"), ComputeSpreadFactor(0.f, 3), 1.f, Tol);

	const TArray<FAstralEnemyThreatCandidate> NoDamage = { MakeEnemyThreatCandidate(Far), MakeEnemyThreatCandidate(Near) };

	// 값이 기본이면 예전 함수와 같다 — 아무도 안 때렸으면 추첨 값과 무관하게 가장 가까운 후보
	{
		FAstralEnemyThreatSettings Defaults;
		Defaults.DamageWeight = 2.f;
		TestEqual(TEXT("defaults, no damage, roll 0 -> nearest"), SelectThreatIndex(Origin, NoDamage, Defaults, 0.f), 1);
		TestEqual(TEXT("defaults, no damage, roll 1 -> nearest"), SelectThreatIndex(Origin, NoDamage, Defaults, 1.f), 1);
		TestEqual(TEXT("defaults match the old overload"), SelectThreatIndex(Origin, NoDamage, Defaults, 0.3f), SelectThreatIndex(Origin, NoDamage, 2.f, 0.3f));
	}

	// 안 맞아도 추첨(거리 가중 없음) — 반반
	{
		FAstralEnemyThreatSettings Draw;
		Draw.DamageWeight = 2.f;
		Draw.bDrawWithoutDamage = true;
		TestEqual(TEXT("draw without damage: roll 0.49 -> first"), SelectThreatIndex(Origin, NoDamage, Draw, 0.49f), 0);
		TestEqual(TEXT("draw without damage: roll 0.51 -> second"), SelectThreatIndex(Origin, NoDamage, Draw, 0.51f), 1);
	}

	// 거리 가중 2 — 먼 쪽(두 배 거리) 2 : 가까운 쪽 3 → 경계 0.4
	{
		FAstralEnemyThreatSettings Distance;
		Distance.DamageWeight = 2.f;
		Distance.bDrawWithoutDamage = true;
		Distance.DistanceWeight = 2.f;
		TestEqual(TEXT("distance weight: roll 0.39 -> the far one (40 %)"), SelectThreatIndex(Origin, NoDamage, Distance, 0.39f), 0);
		TestEqual(TEXT("distance weight: roll 0.41 -> the near one (60 %)"), SelectThreatIndex(Origin, NoDamage, Distance, 0.41f), 1);

		// 죽은 후보는 거리의 기준이 되지 않는다 — 남은 한 명이 '가장 가까운 후보' 다
		TArray<FAstralEnemyThreatCandidate> NearIsDead = NoDamage;
		NearIsDead[1].bDeadOrDying = true;
		TestEqual(TEXT("distance weight: dead nearest is skipped"), SelectThreatIndex(Origin, NearIsDead, Distance, 0.9f), 0);
	}

	// 분산 1 — 같은 거리의 두 후보, 앞 후보를 다른 적 한 마리가 노린다 → 0.5 : 1 → 경계 1/3
	{
		FAstralEnemyThreatSettings Spread;
		Spread.DamageWeight = 2.f;
		Spread.bDrawWithoutDamage = true;
		Spread.SpreadWeight = 1.f;
		TArray<FAstralEnemyThreatCandidate> SameDistance = { MakeEnemyThreatCandidate(Near), MakeEnemyThreatCandidate(FVector(0.0, 400.0, 0.0)) };
		SameDistance[0].NumOtherAttackers = 1;
		TestEqual(TEXT("spread: roll 0.32 -> the one already targeted (33 %)"), SelectThreatIndex(Origin, SameDistance, Spread, 0.32f), 0);
		TestEqual(TEXT("spread: roll 0.35 -> the free one (67 %)"), SelectThreatIndex(Origin, SameDistance, Spread, 0.35f), 1);

		// 분산은 피해 가중과 곱해진다 — 앞 후보가 혼자 때렸다: 3 × 0.5 = 1.5 : 1 → 경계 0.6
		SameDistance[0].RecentDamage = 50.f;
		TestEqual(TEXT("spread x damage: roll 0.59 -> the hitter"), SelectThreatIndex(Origin, SameDistance, Spread, 0.59f), 0);
		TestEqual(TEXT("spread x damage: roll 0.61 -> the other"), SelectThreatIndex(Origin, SameDistance, Spread, 0.61f), 1);

		// 혼자면 분산이 있어도 그 사람이다
		TArray<FAstralEnemyThreatCandidate> Alone = { MakeEnemyThreatCandidate(Near) };
		Alone[0].NumOtherAttackers = 2;
		TestEqual(TEXT("spread: a single candidate is still drawn"), SelectThreatIndex(Origin, Alone, Spread, 0.5f), 0);
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemySelectEngageBearingTest, "AstralBreak.Enemy.SelectEngageBearing", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralEnemySelectEngageBearingTest::RunTest(const FString& Parameters)
{
	using namespace AstralEnemyTargeting;

	constexpr float Sep = 60.f;
	constexpr float Tol = 0.05f;

	// 잡힌 자리가 없다 — 내 쪽 그대로 (−180 ~ 180 으로 접는다)
	{
		const TArray<float> None;
		TestEqual(TEXT("empty ring -> preferred"), SelectEngageBearing(35.f, None, Sep), 35.f, Tol);
		TestEqual(TEXT("empty ring -> preferred, normalized"), SelectEngageBearing(270.f, None, Sep), -90.f, Tol);
	}

	// 내 쪽이 충분히 떨어져 있다 — 그대로. 정확히 MinSeparation 이면 빈 자리다
	{
		const TArray<float> One = { 0.f };
		TestEqual(TEXT("preferred is free"), SelectEngageBearing(100.f, One, Sep), 100.f, Tol);
		TestEqual(TEXT("exactly MinSeparation away counts as free"), SelectEngageBearing(60.f, One, Sep), 60.f, Tol);
		TestEqual(TEXT("separation 0 -> preferred even on top of another"), SelectEngageBearing(0.f, One, 0.f), 0.f, Tol);
	}

	// 내 쪽이 잡혀 있다 — 가장 가까운 빈 가장자리
	{
		const TArray<float> One = { 0.f };
		TestEqual(TEXT("pushed to the nearer edge (+)"), SelectEngageBearing(20.f, One, Sep), 60.f, Tol);
		TestEqual(TEXT("pushed to the nearer edge (-)"), SelectEngageBearing(-20.f, One, Sep), -60.f, Tol);
		// 한 줄 배치 — 둘째는 동률이라 + 쪽, 셋째는 남은 − 쪽
		TestEqual(TEXT("tie -> + side"), SelectEngageBearing(0.f, One, Sep), 60.f, Tol);
		const TArray<float> Two = { 0.f, 60.f };
		TestEqual(TEXT("third in a column takes the other side"), SelectEngageBearing(0.f, Two, Sep), -60.f, Tol);
	}

	// 가장자리가 다른 자리에 걸리면 건너뛴다
	{
		const TArray<float> Two = { 0.f, 90.f };
		// 0 의 +60 은 90 에서 30 — 못 쓴다. 남은 가장자리 −60 · 150 가운데 40 에 가까운 −60(100) vs 150(110)
		TestEqual(TEXT("edge blocked by a neighbour is skipped"), SelectEngageBearing(40.f, Two, Sep), -60.f, Tol);
	}

	// ±180 을 넘는 경계
	{
		const TArray<float> One = { 170.f };
		TestEqual(TEXT("wraps across 180"), SelectEngageBearing(-175.f, One, Sep), -130.f, Tol);
	}

	// 가득 참 — 가장 넓은 틈의 한가운데
	{
		const TArray<float> Full = { 0.f, 60.f, 120.f, 180.f, -120.f, -60.f };
		const float Picked = SelectEngageBearing(10.f, Full, Sep);
		TestEqual(TEXT("full ring -> middle of a gap"), FMath::Abs(FMath::FindDeltaAngleDegrees(0.f, FMath::Fmod(Picked + 360.f, 60.f))), 30.f, Tol);

		const TArray<float> Uneven = { 0.f, 50.f, 100.f, 150.f, -160.f, -110.f, -50.f };
		// 틈: −110 → −50 이 60 으로 가장 넓다(나머지 50). 빈 가장자리는 없다(−110 + 60 = −50 은 잡힌 자리)
		TestEqual(TEXT("full ring -> middle of the widest gap"), SelectEngageBearing(0.f, Uneven, Sep), -80.f, Tol);
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
