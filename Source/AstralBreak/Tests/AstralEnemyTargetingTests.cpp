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

#endif // WITH_DEV_AUTOMATION_TESTS
