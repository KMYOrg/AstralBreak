// 타겟 전환 입력 기계 특성화 테스트 — 스틱 전이표 · 마우스 창/재무장 경계.
// 월드 의존이 없어 Session Frontend / -ExecCmds="Automation RunTests AstralBreak.Targeting"로 돈다.
// stage-3 완료 기준 2·3·7·10·11·12(손으로 재현하기 번거로운 것들)를 코드로 고정한다

#include "Misc/AutomationTest.h"
#include "Character/Hero/Input/AstralTargetSwitchInput.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FAstralTargetSwitchInputParams MakeParams(float MouseThreshold = 18.f)
	{
		FAstralTargetSwitchInputParams Params;
		Params.StickEngageThreshold = 0.6f;
		Params.StickReleaseThreshold = 0.3f;
		Params.MouseAccumulationThreshold = MouseThreshold;
		Params.MouseAccumulationWindow = 0.15f;
		Params.MouseRearmPause = 0.15f;
		return Params;
	}

	bool IsRight(const FAstralTargetSwitchResult& R) { return R.IsSet() && *R == EAstralTargetSwitchDirection::Right; }
	bool IsLeft(const FAstralTargetSwitchResult& R) { return R.IsSet() && *R == EAstralTargetSwitchDirection::Left; }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTargetSwitchStickTest, "AstralBreak.Targeting.SwitchInput.Stick", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTargetSwitchStickTest::RunTest(const FString& Parameters)
{
	const FAstralTargetSwitchInputParams P = MakeParams();

	// 걸림 — Engage 미만은 무반응, 이상이면 1회 전환
	{
		FAstralTargetSwitchInputProcessor In;
		TestFalse(TEXT("0.5 < engage: none"), In.ConsumeStick(0.5f, P).IsSet());
		TestTrue(TEXT("0.7 >= engage: right"), IsRight(In.ConsumeStick(0.7f, P)));

		// 유지 중 무반응 (latch) — 완료 기준 2·10
		TestFalse(TEXT("held 1.0: none"), In.ConsumeStick(1.0f, P).IsSet());
		TestFalse(TEXT("held 1.0 again: none"), In.ConsumeStick(1.0f, P).IsSet());
		TestFalse(TEXT("0.5 (> release, still latched): none"), In.ConsumeStick(0.5f, P).IsSet());
		TestFalse(TEXT("0.7 while latched: none"), In.ConsumeStick(0.7f, P).IsSet());

		// 해제 임계 — Release 이하로 내려오면 Neutral, 다시 기울이면 전환 — 완료 기준 3
		TestFalse(TEXT("0.3 <= release: none (unlatched)"), In.ConsumeStick(0.3f, P).IsSet());
		TestTrue(TEXT("0.7 after release: right again"), IsRight(In.ConsumeStick(0.7f, P)));
	}

	// 왼쪽 대칭
	{
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("-0.7: left"), IsLeft(In.ConsumeStick(-0.7f, P)));
		TestFalse(TEXT("held -1.0: none"), In.ConsumeStick(-1.0f, P).IsSet());
		TestFalse(TEXT("-0.2 <= release: none"), In.ConsumeStick(-0.2f, P).IsSet());
		TestTrue(TEXT("-0.7 again: left"), IsLeft(In.ConsumeStick(-0.7f, P)));
	}

	// 반대쪽 직접 전이 — 완료 기준 11 (중립 경유 없이 새 명시 입력으로 인정)
	{
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("right"), IsRight(In.ConsumeStick(0.8f, P)));
		TestTrue(TEXT("-0.8 while latched right: left immediately"), IsLeft(In.ConsumeStick(-0.8f, P)));
		TestFalse(TEXT("held -0.8: none"), In.ConsumeStick(-0.8f, P).IsSet());
		TestTrue(TEXT("0.8 while latched left: right immediately"), IsRight(In.ConsumeStick(0.8f, P)));
	}

	// Completed — 어느 상태에서든 Neutral (데드존이 있어 값 0으로 놓으면 Triggered 대신 이것이 온다)
	{
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("right"), IsRight(In.ConsumeStick(0.8f, P)));
		In.CompleteStick();
		TestTrue(TEXT("after completed: right again"), IsRight(In.ConsumeStick(0.8f, P)));
	}

	// Reset — 세션 경계(재락온) 후 첫 전환이 즉시 먹는다 — 완료 기준 8
	{
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("right"), IsRight(In.ConsumeStick(0.8f, P)));
		In.Reset();
		TestTrue(TEXT("after reset: right again"), IsRight(In.ConsumeStick(0.8f, P)));
	}

	// 데이터 오류 — Release > Engage여도 Engage로 보정돼 동작한다
	{
		FAstralTargetSwitchInputParams Bad = P;
		Bad.StickReleaseThreshold = 0.9f;
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("right"), IsRight(In.ConsumeStick(0.8f, Bad)));
		TestFalse(TEXT("0.7 (> engage-as-release): still latched"), In.ConsumeStick(0.7f, Bad).IsSet());
		TestFalse(TEXT("0.6 (<= engage-as-release): unlatched"), In.ConsumeStick(0.6f, Bad).IsSet());
		TestTrue(TEXT("0.8: right again"), IsRight(In.ConsumeStick(0.8f, Bad)));
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralTargetSwitchMouseTest, "AstralBreak.Targeting.SwitchInput.Mouse", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralTargetSwitchMouseTest::RunTest(const FString& Parameters)
{
	const FAstralTargetSwitchInputParams P = MakeParams(18.f);
	constexpr double Frame = 1.0 / 60.0;

	// 빠른 플릭 — 창 안에 임계 도달 시 정확히 1회. 꼬리는 폐기, 멈춘 뒤 재무장 — 완료 기준 7
	{
		FAstralTargetSwitchInputProcessor In;
		double T = 0.0;
		TestFalse(TEXT("7: none"), In.ConsumeMouse(7.f, T, P).IsSet());
		T += Frame; TestFalse(TEXT("15: none"), In.ConsumeMouse(8.f, T, P).IsSet());
		T += Frame; TestTrue(TEXT("24 >= 18: right"), IsRight(In.ConsumeMouse(9.f, T, P)));
		T += Frame; TestFalse(TEXT("tail 6 while waiting: discarded"), In.ConsumeMouse(6.f, T, P).IsSet());
		T += Frame; TestFalse(TEXT("tail 20 while waiting: discarded even above threshold"), In.ConsumeMouse(20.f, T, P).IsSet());

		// 멈춤(≥ RearmPause) 후 첫 입력에서 재무장 + 새 창
		T += 0.4; TestFalse(TEXT("after pause, 7: rearmed, accumulating"), In.ConsumeMouse(7.f, T, P).IsSet());
		T += Frame; TestTrue(TEXT("19 >= 18: right again"), IsRight(In.ConsumeMouse(12.f, T, P)));
	}

	// 느린 드래그 — 끊김 없이 밀어도 창(첫 입력 기준) 안에 임계에 못 닿으면 영원히 전환되지 않는다 — 완료 기준 7
	{
		FAstralTargetSwitchInputProcessor In;
		int32 Switches = 0;
		for (int32 Index = 0; Index < 120; ++Index)   // 2초, 초당 90단위 (창 0.15초에 약 13.5)
		{
			if (In.ConsumeMouse(1.5f, Index * Frame, P).IsSet()) { ++Switches; }
		}
		TestEqual(TEXT("slow continuous drag never switches"), Switches, 0);
	}

	// 한 방향으로 계속 밀기 — 한 번만 넘어가고 멈출 때까지 잠긴다 — 완료 기준 7
	{
		FAstralTargetSwitchInputProcessor In;
		int32 Switches = 0;
		for (int32 Index = 0; Index < 60; ++Index)   // 1초, 프레임당 10 (창 안에 곧 도달)
		{
			if (In.ConsumeMouse(10.f, Index * Frame, P).IsSet()) { ++Switches; }
		}
		TestEqual(TEXT("continuous fast push switches exactly once"), Switches, 1);
	}

	// 창 안 누적 — 0.10초 간격은 RearmPause(0.15) 미만이라 '멈춤'이 아니고 창(0.15)도 안 지났다 → 같은 창에 누적
	{
		FAstralTargetSwitchInputProcessor In;
		TestFalse(TEXT("10 at t=0"), In.ConsumeMouse(10.f, 0.0, P).IsSet());
		TestTrue(TEXT("10 at t=0.10 inside window: 20 -> right"), IsRight(In.ConsumeMouse(10.f, 0.10, P)));
	}
	// 창 만료 — 첫 입력에서 Window가 지나면 누적을 버리고 새 창
	{
		FAstralTargetSwitchInputProcessor In;
		TestFalse(TEXT("10 at t=0"), In.ConsumeMouse(10.f, 0.0, P).IsSet());
		TestFalse(TEXT("5 at t=0.10: 15, none"), In.ConsumeMouse(5.f, 0.10, P).IsSet());
		// t=0.20: 첫 입력에서 0.20 > 0.15 → 창 만료 → 새 창 (누적 10)
		TestFalse(TEXT("10 at t=0.20: window expired -> new window (10)"), In.ConsumeMouse(10.f, 0.20, P).IsSet());
		TestTrue(TEXT("8 at t=0.21: 18 -> right"), IsRight(In.ConsumeMouse(8.f, 0.21, P)));
	}

	// 왼쪽
	{
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("-20: left"), IsLeft(In.ConsumeMouse(-20.f, 0.0, P)));
	}

	// 임계 0 이하 = 비활성 — 누적은 되지만 전환하지 않는다 (실측 전 첫 플레이 보호)
	{
		const FAstralTargetSwitchInputParams Off = MakeParams(0.f);
		FAstralTargetSwitchInputProcessor In;
		TestFalse(TEXT("threshold off: 100 -> none"), In.ConsumeMouse(100.f, 0.0, Off).IsSet());
#if !UE_BUILD_SHIPPING
		TestEqual(TEXT("threshold off: accumulation still visible"), In.MakeDebugSnapshot(0.0, Off).MouseAccumulation, 100.f);
#endif
	}

	// Reset — 전환 직후 잠금 상태에서 세션 경계 리셋이 오면 첫 플릭이 즉시 먹는다 — 완료 기준 12
	{
		FAstralTargetSwitchInputProcessor In;
		TestTrue(TEXT("20: right"), IsRight(In.ConsumeMouse(20.f, 0.0, P)));
		In.Reset();
		TestTrue(TEXT("20 right after reset (no pause): right"), IsRight(In.ConsumeMouse(20.f, 0.01, P)));
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
