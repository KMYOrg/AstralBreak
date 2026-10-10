// 락온 후보 선정 순수 함수 테스트 — 월드 의존이 없어 Session Frontend / -ExecCmds="Automation RunTests AstralBreak.Targeting"로 돈다

#include "Misc/AutomationTest.h"
#include "Combat/AstralTargetingStatics.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FAstralTargetCandidate MakeCandidate(float YawDeg, float Score = 0.f, float Distance = 0.f, bool bIsCurrentTarget = false)
	{
		FAstralTargetCandidate Candidate;
		Candidate.YawDeg = YawDeg;
		Candidate.Score = Score;
		Candidate.Distance = Distance;
		Candidate.bIsCurrentTarget = bIsCurrentTarget;
		return Candidate;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTargetingSelectCycleCandidateTest, "AstralBreak.Targeting.SelectCycleCandidate", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTargetingSelectCycleCandidateTest::RunTest(const FString& Parameters)
{
	using namespace AstralTargeting;

	// 기본 좌우 — 현재 타겟(0°) 기준 가장 가까운 후보. 현재 타겟은 제외
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(-30.f), MakeCandidate(0.f, 0.f, 0.f, /*bIsCurrentTarget=*/true), MakeCandidate(20.f), MakeCandidate(45.f) };
		TestEqual(TEXT("right -> nearest right (20)"), SelectCycleCandidate(Candidates, 0.f, +1.f), 2);
		TestEqual(TEXT("left -> nearest left (-30)"), SelectCycleCandidate(Candidates, 0.f, -1.f), 0);
	}

	// 그 방향에 후보 없음 → INDEX_NONE (현재 타겟 유지)
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(-30.f), MakeCandidate(-10.f) };
		TestEqual(TEXT("no candidate on the right"), SelectCycleCandidate(Candidates, 0.f, +1.f), INDEX_NONE);
	}

	// Direction 0 → INDEX_NONE
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(20.f) };
		TestEqual(TEXT("direction 0"), SelectCycleCandidate(Candidates, 0.f, 0.f), INDEX_NONE);
	}

	// ±180 래핑 — 현재 +170 · 후보 −70: 단순 차 −240(왼쪽)이 아니라 최단 각 +120(오른쪽)
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(-70.f) };
		TestEqual(TEXT("wrap: +170 -> -70 is to the right"), SelectCycleCandidate(Candidates, 170.f, +1.f), 0);
		TestEqual(TEXT("wrap: +170 -> -70 is not to the left"), SelectCycleCandidate(Candidates, 170.f, -1.f), INDEX_NONE);
	}

	// 현재 타겟이 후보 밖(등 뒤, 유지 조건에 각도 제한 없음) — 기준 각만 넘겨도 동작
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(-60.f), MakeCandidate(60.f) };
		TestEqual(TEXT("current behind (-150): right picks -60 (step +90)"), SelectCycleCandidate(Candidates, -150.f, +1.f), 0);
		TestEqual(TEXT("current behind (-150): left picks 60 (step -150)"), SelectCycleCandidate(Candidates, -150.f, -1.f), 1);
	}

	// 히스테리시스 없음 — 각도 차가 아무리 작아도 그 방향이면 넘어간다
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(0.f, 1.f, 0.f, true), MakeCandidate(0.2f, 0.f) };
		TestEqual(TEXT("no threshold: 0.2 deg to the right still switches"), SelectCycleCandidate(Candidates, 0.f, +1.f), 1);
	}

	// 타이브레이커 — 각도 동률(허용 0.5°) → Score 높음 → Distance 가까움. 배열 순서에 의존하지 않는다
	{
		const TArray<FAstralTargetCandidate> Candidates = { MakeCandidate(30.f, 0.2f, 500.f), MakeCandidate(30.3f, 0.8f, 900.f) };
		TestEqual(TEXT("tie -> higher score"), SelectCycleCandidate(Candidates, 0.f, +1.f), 1);

		const TArray<FAstralTargetCandidate> Reversed = { MakeCandidate(30.3f, 0.8f, 900.f), MakeCandidate(30.f, 0.2f, 500.f) };
		TestEqual(TEXT("tie -> higher score (reversed order)"), SelectCycleCandidate(Reversed, 0.f, +1.f), 0);

		const TArray<FAstralTargetCandidate> SameScore = { MakeCandidate(30.f, 0.5f, 900.f), MakeCandidate(30.2f, 0.5f, 400.f) };
		TestEqual(TEXT("tie + same score -> nearer"), SelectCycleCandidate(SameScore, 0.f, +1.f), 1);

		// 허용 밖(1°)이면 각도가 우선 — Score가 낮아도 가까운 쪽
		const TArray<FAstralTargetCandidate> OutsideTolerance = { MakeCandidate(30.f, 0.1f), MakeCandidate(31.f, 0.9f) };
		TestEqual(TEXT("outside tolerance -> angle wins"), SelectCycleCandidate(OutsideTolerance, 0.f, +1.f), 0);
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTargetingClampFacingYawTest, "AstralBreak.Targeting.ClampFacingYaw", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTargetingClampFacingYawTest::RunTest(const FString& Parameters)
{
	using namespace AstralTargeting;
	constexpr float Tolerance = 0.01f;

	// 상한 안 — 원하는 각 그대로
	TestNearlyEqual(TEXT("within: 0 -> 45 (max 90)"), ClampFacingYaw(0.f, 45.f, 90.f), 45.f, Tolerance);
	TestNearlyEqual(TEXT("within: 0 -> -45 (max 90)"), ClampFacingYaw(0.f, -45.f, 90.f), -45.f, Tolerance);

	// 상한 밖 — 폴백이 아니라 클램프 (락온 4단계 완료 기준 3)
	TestNearlyEqual(TEXT("clamp: 0 -> 170 (max 90) = 90"), ClampFacingYaw(0.f, 170.f, 90.f), 90.f, Tolerance);
	TestNearlyEqual(TEXT("clamp: 0 -> -170 (max 90) = -90"), ClampFacingYaw(0.f, -170.f, 90.f), -90.f, Tolerance);

	// ±180 래핑 — 현재 +170 · 원하는 -70: 단순 차 −240이 아니라 최단 +120 → 우측 90만큼 = -100
	TestNearlyEqual(TEXT("wrap: +170 -> -70 (max 90) = -100"), ClampFacingYaw(170.f, -70.f, 90.f), -100.f, Tolerance);
	// 현재 -170 · 원하는 +170: 최단 -20 (좌측) → 그대로 +170
	TestNearlyEqual(TEXT("wrap: -170 -> +170 (max 90) = 170"), ClampFacingYaw(-170.f, 170.f, 90.f), 170.f, Tolerance);

	// 정확히 뒤(180) — 어느 쪽이든 상한만큼만
	TestNearlyEqual(TEXT("behind: |0 -> 180| (max 90) = 90"), FMath::Abs(ClampFacingYaw(0.f, 180.f, 90.f)), 90.f, Tolerance);

	// 상한 0 — 회전 없음
	TestNearlyEqual(TEXT("max 0: no change"), ClampFacingYaw(30.f, 120.f, 0.f), 30.f, Tolerance);

	// 결과는 정규화 (-180, 180]
	TestNearlyEqual(TEXT("normalized: 170 + 30 = -160"), ClampFacingYaw(170.f, -160.f, 90.f), -160.f, Tolerance);

	// ComputeFacingYaw — 수평 겹침은 폴백
	TestNearlyEqual(TEXT("facing yaw: +X = 0"), ComputeFacingYaw(FVector::ZeroVector, FVector(100.f, 0.f, 0.f), 55.f), 0.f, Tolerance);
	TestNearlyEqual(TEXT("facing yaw: +Y = 90"), ComputeFacingYaw(FVector::ZeroVector, FVector(0.f, 100.f, 0.f), 55.f), 90.f, Tolerance);
	TestNearlyEqual(TEXT("facing yaw: overlap -> fallback"), ComputeFacingYaw(FVector::ZeroVector, FVector(0.f, 0.f, 300.f), 55.f), 55.f, Tolerance);

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
