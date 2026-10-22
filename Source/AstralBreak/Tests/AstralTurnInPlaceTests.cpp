// 제자리 회전 순수 계산 테스트 — 누적·클램프 · 스프링 복귀 · 턴 커브 처리 · 클립 선택 래치.
// 월드 의존이 없어 run_automation_tests {"filter": "AstralBreak.TurnInPlace"} 로 돈다. 그래프 배선·실제 회전은 PIE (hero-combat-abp.md)

#include "Misc/AutomationTest.h"
#include "Animation/AstralTurnInPlace.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FAstralTurnInPlaceInput MakeInput(float YawDelta, bool bAccumulate, float Weight = 0.f, float Remaining = 0.f, float Dt = 1.f / 60.f)
	{
		FAstralTurnInPlaceInput In;
		In.DeltaSeconds = Dt;
		In.YawDeltaSinceLastUpdate = YawDelta;
		In.bAccumulate = bAccumulate;
		In.TurnYawWeightCurve = Weight;
		In.RemainingTurnYawCurve = Remaining;
		return In;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTurnInPlaceAccumulateTest, "AstralBreak.TurnInPlace.Accumulate", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTurnInPlaceAccumulateTest::RunTest(const FString& Parameters)
{
	FAstralTurnInPlaceSettings S;
	FAstralTurnInPlaceState State;

	// 액터가 오른쪽(+)으로 30도 돌면 루트는 −30 (발 고정)
	State.Update(S, MakeInput(30.f, true));
	TestEqual(TEXT("counter-rotate"), State.RootYawOffset, -30.f);
	State.Update(S, MakeInput(30.f, true));
	TestEqual(TEXT("accumulates"), State.RootYawOffset, -60.f);

	// 델타는 정규화(−300 ≡ +60), 합은 클램프 안 — 부호 뒤집힘 없음
	State.Update(S, MakeInput(-300.f, true));
	TestEqual(TEXT("delta normalized, no wrap"), State.RootYawOffset, -120.f);

	// 클램프
	State.Reset();
	for (int32 i = 0; i < 10; ++i) { State.Update(S, MakeInput(30.f, true)); }
	TestEqual(TEXT("clamped at -Clamp"), State.RootYawOffset, -S.RootYawOffsetClamp);

	// 누적 중엔 요청 플래그 — 임계 초과
	TestTrue(TEXT("wants turn beyond threshold"), State.bWantsTurn);
	// 클립 종류는 요청이 켜진 순간(−60)에 고정 — 그 뒤 더 돌아 클램프에 닿아도 바뀌지 않는다 (Lyra 도 상태 진입 때 한 번 고른다)
	TestEqual(TEXT("kind latched at rising edge (-60) → Right90"), State.Kind, EAstralTurnInPlaceKind::Right90);
	{
		// 기본 클램프(120) < 180 임계(135) — 한 프레임에 160 을 돌아도 −120 에서 요청 → 90 클립 (180 클립은 클램프를 올려야 나온다)
		FAstralTurnInPlaceState Fast;
		Fast.Update(S, MakeInput(160.f, true));
		TestEqual(TEXT("default clamp → Right90"), Fast.Kind, EAstralTurnInPlaceKind::Right90);

		FAstralTurnInPlaceSettings Wide = S;
		Wide.RootYawOffsetClamp = 150.f;
		FAstralTurnInPlaceState FastWide;
		FastWide.Update(Wide, MakeInput(160.f, true));   // 클램프 −150 에서 요청 → 180 클립
		TestEqual(TEXT("clamp 150 → Right180"), FastWide.Kind, EAstralTurnInPlaceKind::Right180);
	}

	// 클램프에서 더 돌아도 뒤집히지 않는다 (예전엔 120 + 100 → 220 → 정규화 −140 → 240° 점프)
	State.Update(S, MakeInput(100.f, true));
	TestEqual(TEXT("stays at clamp, no flip"), State.RootYawOffset, -S.RootYawOffsetClamp);

	// 누적이 아니면 요청하지 않는다 (복귀 중 턴 금지)
	State.Update(S, MakeInput(0.f, false));
	TestFalse(TEXT("no turn while blending out"), State.bWantsTurn);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTurnInPlaceBlendOutTest, "AstralBreak.TurnInPlace.BlendOut", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTurnInPlaceBlendOutTest::RunTest(const FString& Parameters)
{
	FAstralTurnInPlaceSettings S;
	FAstralTurnInPlaceState State;
	State.Update(S, MakeInput(90.f, true));
	TestEqual(TEXT("start"), State.RootYawOffset, -90.f);

	// 이동 시작 — 스프링으로 0 에 수렴, 단조 감소, 2초 안에 거의 0
	float Prev = FMath::Abs(State.RootYawOffset);
	bool bMonotonic = true;
	for (int32 i = 0; i < 120; ++i)
	{
		State.Update(S, MakeInput(0.f, false));
		const float Now = FMath::Abs(State.RootYawOffset);
		bMonotonic &= Now <= Prev + 0.01f;
		Prev = Now;
	}
	TestTrue(TEXT("monotonic decay"), bMonotonic);
	TestTrue(TEXT("near zero after 2s"), FMath::Abs(State.RootYawOffset) < 1.f);

	// 아주 작은 값은 정확히 0 으로 스냅
	for (int32 i = 0; i < 120; ++i) { State.Update(S, MakeInput(0.f, false)); }
	TestEqual(TEXT("snapped to zero"), State.RootYawOffset, 0.f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTurnInPlaceCurveTest, "AstralBreak.TurnInPlace.Curve", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTurnInPlaceCurveTest::RunTest(const FString& Parameters)
{
	FAstralTurnInPlaceSettings S;
	FAstralTurnInPlaceState State;
	State.Update(S, MakeInput(90.f, true));   // 오프셋 −90 → Right90 클립 (RemainingTurnYaw 90 → 0)
	TestEqual(TEXT("kind Right90"), State.Kind, EAstralTurnInPlaceKind::Right90);

	// 클립 첫 활성 프레임 — 이전 값 0 이라 델타를 적용하지 않는다 (가짜 0→90)
	State.Update(S, MakeInput(0.f, true, 1.f, 90.f));
	TestEqual(TEXT("first frame: no delta"), State.RootYawOffset, -90.f);
	TestTrue(TEXT("anim active"), State.bTurnAnimActive);
	TestFalse(TEXT("not finished"), State.bRotationFinished);

	// 이후 프레임 — 남은 각이 줄어든 만큼 오프셋이 0 쪽으로
	State.Update(S, MakeInput(0.f, true, 1.f, 60.f));
	TestEqual(TEXT("reduced by 30"), State.RootYawOffset, -60.f);
	// 블렌드 중(가중치 0.6) 에도 가중 해제로 온전한 각 — 남은 30 × 0.6 = 18 이 들어와도 30 으로 본다
	State.Update(S, MakeInput(0.f, true, 0.6f, 18.f));
	TestTrue(TEXT("unweighted"), FMath::IsNearlyEqual(State.RootYawOffset, -30.f, 0.01f));
	TestTrue(TEXT("anim time accumulates"), State.TurnAnimTime > 0.f);

	// 회전 끝 — 남은 각 ≤ 허용 → finished, 오프셋 ≈ 0
	State.Update(S, MakeInput(0.f, true, 1.f, 0.5f));
	TestTrue(TEXT("rotation finished"), State.bRotationFinished);
	TestTrue(TEXT("offset near zero"), FMath::Abs(State.RootYawOffset) < 1.f);
	TestFalse(TEXT("no longer wants turn"), State.bWantsTurn);
	TestEqual(TEXT("kind kept for recovery"), State.Kind, EAstralTurnInPlaceKind::Right90);

	// 연속 회전 — Recovery 꼬리값(0.5)에서 새 클립(90)으로 즉시 재진입: 커브가 "커졌다" → 델타(89.5)를 버린다 (2026-10-20 "180° 휙" 수정)
	const float Before = State.RootYawOffset;
	TestTrue(TEXT("anim time before re-entry"), State.TurnAnimTime > 0.f);
	State.Update(S, MakeInput(0.f, true, 1.f, 90.f));
	TestTrue(TEXT("new clip: delta skipped"), FMath::IsNearlyEqual(State.RootYawOffset, Before, 0.01f));
	// 커브 활성이 끊기지 않아도(관성 블렌드) 새 클립이면 클립 시간은 처음부터 — Recovery StartPosition 이 다음 클립에 이월되지 않는다
	TestEqual(TEXT("new clip: anim time restarts"), State.TurnAnimTime, 0.f);
	// 반대 방향 클립(−90)으로 바뀌어도(부호 반전) 마찬가지
	State.Update(S, MakeInput(0.f, true, 1.f, 60.f));
	const float Mid = State.RootYawOffset;
	State.Update(S, MakeInput(0.f, true, 1.f, -90.f));
	TestTrue(TEXT("flipped clip: delta skipped"), FMath::IsNearlyEqual(State.RootYawOffset, Mid, 0.01f));
	State.Update(S, MakeInput(0.f, true, 1.f, -60.f));
	TestTrue(TEXT("left clip reduces offset"), FMath::IsNearlyEqual(State.RootYawOffset, Mid - 30.f, 0.01f));

	// 클립 종료(가중치 0) — 커브 상태 리셋
	State.Update(S, MakeInput(0.f, true, 0.f, 0.f));
	TestFalse(TEXT("inactive"), State.bTurnAnimActive);
	TestEqual(TEXT("anim time reset"), State.TurnAnimTime, 0.f);
	TestFalse(TEXT("finished cleared"), State.bRotationFinished);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTurnInPlaceKindTest, "AstralBreak.TurnInPlace.Kind", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTurnInPlaceKindTest::RunTest(const FString& Parameters)
{
	FAstralTurnInPlaceSettings S;
	TestEqual(TEXT("-60 → Right90"), FAstralTurnInPlaceState::SelectKind(-60.f, S), EAstralTurnInPlaceKind::Right90);
	TestEqual(TEXT("-135 → Right180"), FAstralTurnInPlaceState::SelectKind(-135.f, S), EAstralTurnInPlaceKind::Right180);
	TestEqual(TEXT("60 → Left90"), FAstralTurnInPlaceState::SelectKind(60.f, S), EAstralTurnInPlaceKind::Left90);
	TestEqual(TEXT("170 → Left180"), FAstralTurnInPlaceState::SelectKind(170.f, S), EAstralTurnInPlaceKind::Left180);

	// 래치 — 임계를 넘는 순간의 값으로 고정, 그 뒤 반대쪽으로 더 돌아도 임계 아래로 내려가기 전엔 유지
	FAstralTurnInPlaceState State;
	State.Update(S, MakeInput(60.f, true));          // −60 → Right90
	TestEqual(TEXT("latched Right90"), State.Kind, EAstralTurnInPlaceKind::Right90);
	State.Update(S, MakeInput(-170.f, true));        // 오프셋 +110 이지만 여전히 > 임계 → 래치 유지
	TestEqual(TEXT("kept while wanting"), State.Kind, EAstralTurnInPlaceKind::Right90);
	State.Update(S, MakeInput(100.f, true));         // +110 − 100 = +10 → 요청 해제 (−100 이면 210 → −150 → 클램프 −120 으로 여전히 요청)
	TestFalse(TEXT("released"), State.bWantsTurn);
	State.Update(S, MakeInput(-80.f, true));         // +90 → 새 래치 Left90
	TestEqual(TEXT("re-latched Left90"), State.Kind, EAstralTurnInPlaceKind::Left90);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTurnInPlaceKindDuringRotationTest, "AstralBreak.TurnInPlace.KindDuringRotation", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTurnInPlaceKindDuringRotationTest::RunTest(const FString& Parameters)
{
	// 회전 중 반대로 돌려 오프셋이 임계 아래로 내려갔다가 반대편으로 넘어도 클립은 그대로 — 예전엔 상승 에지에서 Left90 으로 바뀌어
	// Rotation 상태 안에서 BlendListByEnum 이 클립을 갈아 끼웠다(표준 크로스페이드라 두 클립 커브가 합산)
	FAstralTurnInPlaceSettings S;
	FAstralTurnInPlaceState State;
	State.Update(S, MakeInput(60.f, true));                 // −60 → Right90 진입
	TestEqual(TEXT("entered Right90"), State.Kind, EAstralTurnInPlaceKind::Right90);
	State.Update(S, MakeInput(0.f, true, 1.f, 90.f));       // 클립 첫 활성 프레임
	TestTrue(TEXT("in rotation"), State.IsInRotation());
	TestFalse(TEXT("no request inside rotation"), State.bWantsTurn);
	State.Update(S, MakeInput(0.f, true, 1.f, 50.f));       // 커브가 오프셋을 −20 으로
	State.Update(S, MakeInput(-80.f, true, 1.f, 40.f));     // 반대로 80 → +70 (임계 위, 반대편)
	TestTrue(TEXT("offset crossed to the other side"), State.RootYawOffset > S.TurnThreshold);
	TestFalse(TEXT("still no request"), State.bWantsTurn);
	TestEqual(TEXT("kind unchanged during rotation"), State.Kind, EAstralTurnInPlaceKind::Right90);

	// 회전 구간 종료 → 게이트 뒤 다음 진입에서 새 방향
	State.Update(S, MakeInput(0.f, true, 1.f, 0.5f));
	TestTrue(TEXT("rotation finished"), State.bRotationFinished);
	for (int32 i = 0; i < 60 && !State.bWantsTurn; ++i) { State.Update(S, MakeInput(0.f, true)); }
	TestTrue(TEXT("wants after gate"), State.bWantsTurn);
	TestEqual(TEXT("new direction latched at next entry"), State.Kind, EAstralTurnInPlaceKind::Left90);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTurnInPlaceReentryTest, "AstralBreak.TurnInPlace.Reentry", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTurnInPlaceReentryTest::RunTest(const FString& Parameters)
{
	constexpr float Dt = 1.f / 60.f;
	auto RunTurnThenRecover = [this](const FAstralTurnInPlaceSettings& S, float& OutElapsedAtWant) -> FAstralTurnInPlaceState
	{
		FAstralTurnInPlaceState State;
		State.Update(S, MakeInput(60.f, true));             // 첫 턴은 게이트 없음 (회전 이력 없음)
		TestTrue(TEXT("first turn not gated"), State.bWantsTurn);
		State.Update(S, MakeInput(0.f, true, 1.f, 90.f));
		State.Update(S, MakeInput(0.f, true, 1.f, 45.f));
		State.Update(S, MakeInput(0.f, true, 1.f, 0.5f));   // 회전 구간 끝 (Rotation → Recovery)
		TestTrue(TEXT("rotation finished"), State.bRotationFinished);
		float Elapsed = Dt;                                  // 종료 프레임부터 게이트 시계가 흐른다

		// Recovery 첫 프레임에 다시 크게 돈다 — 오프셋은 바로 임계를 넘지만 게이트 동안은 요청하지 않는다
		State.Update(S, MakeInput(90.f, true));
		Elapsed += Dt;
		TestTrue(TEXT("offset beyond threshold in recovery"), FMath::Abs(State.RootYawOffset) > S.TurnThreshold);
		OutElapsedAtWant = -1.f;
		for (int32 i = 0; i < 60; ++i)
		{
			if (State.bWantsTurn)
			{
				OutElapsedAtWant = Elapsed;
				break;
			}
			State.Update(S, MakeInput(0.f, true));
			Elapsed += Dt;
		}
		return State;
	};

	FAstralTurnInPlaceSettings S;
	float ElapsedAtWant = 0.f;
	const FAstralTurnInPlaceState Gated = RunTurnThenRecover(S, ElapsedAtWant);
	TestTrue(TEXT("re-entry waits for the gate"), ElapsedAtWant >= S.ReentryMinRecoveryTime - KINDA_SMALL_NUMBER);
	TestTrue(TEXT("re-entry right after the gate"), ElapsedAtWant <= S.ReentryMinRecoveryTime + 2.f * Dt);
	TestEqual(TEXT("re-entry kind from offset at entry"), Gated.Kind, EAstralTurnInPlaceKind::Right90);

	// 게이트 0 = Lyra 식 즉시 재진입
	FAstralTurnInPlaceSettings Immediate;
	Immediate.ReentryMinRecoveryTime = 0.f;
	RunTurnThenRecover(Immediate, ElapsedAtWant);
	TestTrue(TEXT("gate 0 → immediate re-entry"), ElapsedAtWant >= 0.f && ElapsedAtWant <= 2.f * Dt + KINDA_SMALL_NUMBER);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
