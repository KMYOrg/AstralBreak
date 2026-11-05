// 러너와 엔진 Automation 워커의 경합 회귀 시험 (Core/AnimMcpAutomationRunner.cpp).
// 워커 Tick(LaunchEngineLoop.cpp:6012)과 코어 티커의 러너(:6072)가 프레임마다 같은 latent 큐를 돌린다 — 프레임의 첫 호출이 워커, 두 번째 호출이 러너다.
// 워커 모듈이 없으면 두 번째 호출이 오지 않아 LatentEndsInRunnerCall 이 타임아웃으로 드러난다.
//
// 실행: run_automation_tests {filter:"AnimGraphMcp.Runner"}

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	const TCHAR* const NestedCommandRan = TEXT("nested latent command ran");

	/** 시작 프레임을 넘긴 뒤, 그 프레임의 CallInFrame 번째 Update 에서 끝난다 */
	class FEndAtCallInFrame : public IAutomationLatentCommand
	{
	public:
		explicit FEndAtCallInFrame(const int32 InCallInFrame) : CallInFrame(InCallInFrame) {}

		virtual bool Update() override
		{
			if (StartFrame == MAX_uint64)
			{
				StartFrame = GFrameCounter;
			}
			CallsThisFrame = LastFrame == GFrameCounter ? CallsThisFrame + 1 : 1;
			LastFrame = GFrameCounter;
			return GFrameCounter > StartFrame && CallsThisFrame == CallInFrame;
		}

	private:
		int32 CallInFrame;
		int32 CallsThisFrame = 0;
		uint64 StartFrame = MAX_uint64;
		uint64 LastFrame = MAX_uint64;
	};

	void Step(TFunction<bool()> Fn)
	{
		FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(MoveTemp(Fn)));
	}
}

// 러너가 잡을 시작하는 그 호출에서 큐가 빈다
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpRunnerLatentEndsInFirstCallTest, "AnimGraphMcp.Runner.LatentEndsInFirstCall", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpRunnerLatentEndsInFirstCallTest::RunTest(const FString& Parameters)
{
	Step([]() -> bool { return true; });
	return true;
}

// 수정 전에는 다음 프레임에 워커가 빈 큐를 보고 테스트를 끝내 러너가 check(GIsAutomationTesting) 로 죽었다
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpRunnerLatentEndsInRunnerCallTest, "AnimGraphMcp.Runner.LatentEndsInRunnerCall", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpRunnerLatentEndsInRunnerCallTest::RunTest(const FString& Parameters)
{
	ADD_LATENT_AUTOMATION_COMMAND(FEndAtCallInFrame(2));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpRunnerLatentEndsInWorkerCallTest, "AnimGraphMcp.Runner.LatentEndsInWorkerCall", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpRunnerLatentEndsInWorkerCallTest::RunTest(const FString& Parameters)
{
	ADD_LATENT_AUTOMATION_COMMAND(FEndAtCallInFrame(1));
	return true;
}

// 명령 안에서 넣은 명령이 버려지면 기대 메시지가 나오지 않아 실패한다
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpRunnerNestedLatentCommandTest, "AnimGraphMcp.Runner.NestedLatentCommand", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpRunnerNestedLatentCommandTest::RunTest(const FString& Parameters)
{
	AddExpectedMessagePlain(NestedCommandRan, ELogVerbosity::Display);
	Step([this]() -> bool
	{
		Step([this]() -> bool
		{
			AddInfo(NestedCommandRan);
			return true;
		});
		return true;
	});
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
