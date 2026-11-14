#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class FAutomationTestBase;
class UWorld;
struct FAnimMcpError;

/**
 * StateTree 런타임 관측 — run_state_tree_scenario (Docs/StateTree/DevelopmentGuide.md §6).
 *
 * run_anim_scenario 와 같은 계약이다: Tool 이 시나리오를 검증 · 정규화해 테스트 명령 "<클래스 이름> <JSON>" 에 실어 잡 하나로 돌리고,
 * 관측은 AnimMcpRuntimeScenario 슬롯을 거쳐 결과의 observed 로 나온다. 테스트는 Tests/AnimMcpStateTreeTests.cpp.
 *
 * 타임라인은 활성 상태 폴링이다. 러너가 프레임마다 한 번 읽으므로 한 프레임 안에 들어갔다 나온 상태는 이름이 보이지 않고, 전환 사유는 다루지 않는다(§0-8).
 * 대신 엔진의 상태 진입 횟수(StateChangeCount)를 같이 읽어 이름이 안 보인 전환도 있었다는 사실은 놓치지 않는다 — EnterState 에서 실패하는 작업이 이 경우다.
 * AIController 는 서버에만 있으므로 관측은 서버 월드 인스턴스만 한다 — 다른 PIE 월드는 끝에 개수만 센다.
 */
namespace AnimMcpStateTreeRuntime
{
	/** IMPLEMENT_*_AUTOMATION_TEST 의 클래스 이름 — StartTestByName 이 이 이름으로 찾는다 */
	inline const TCHAR* const TestClassName = TEXT("FAnimMcpStateTreeScenarioTest");
	inline const TCHAR* const TestPath = TEXT("StateTreeMcp.16_RuntimeScenario");

	struct FEventSpec
	{
		FString Tag;
		/** 앞 이벤트가 끝난 뒤(첫 이벤트는 트리 시작 뒤) 기다릴 초 */
		double After = 0.0;
		/** 이 상태가 활성일 때만 보낸다. 비면 조건 없음 */
		FString WhenState;
		/** 전환 뒤 이 상태가 활성으로 보여야 한다. 비면 전환만 본다 */
		FString ExpectState;
		/** false = 전환이 일어나지 않아야 통과 (무관한 이벤트의 대조 시험) */
		bool bExpectTransition = true;
		/** 전송 뒤 전환을 기다릴 초 */
		double Window = 2.0;
	};

	/** 시나리오가 폰 · 컨트롤러에 직접 하는 일. 사망 · 언포제션 · 파괴 경로를 시험할 때 쓴다 */
	enum class EActionKind : uint8
	{
		/** 폰의 DamageSelf(Exec)를 이름으로 부른다 — 플러그인이 프로젝트 모듈에 의존하지 않게 */
		Damage,
		Unpossess,
		/** 처음 쓰던 컨트롤러가 같은 폰을 다시 빙의한다 */
		Repossess,
		Destroy,
		/** 컨트롤러 없이 스폰한 폰에 SpawnDefaultController. 트리 시작 전에 쓰는 동작이라 시나리오의 첫 동작이어야 한다 */
		SpawnController,
	};

	const TCHAR* ActionName(EActionKind Kind);

	struct FActionSpec
	{
		EActionKind Kind = EActionKind::Damage;
		/** 앞 동작 뒤(첫 동작은 트리 시작 뒤, spawn_controller 는 관측 시작 뒤) 기다릴 초 */
		double After = 0.0;
		/** 이 상태가 활성일 때만 실행한다. 비면 조건 없음 */
		FString WhenState;
		/** Damage 의 양 */
		double Amount = 0.0;
	};

	struct FScenario
	{
		/** 정규화된 오브젝트 경로 */
		FString TreePath;
		FString Map;
		/** 정규화된 클래스 경로. SpawnLocation 이 있으면 스폰, 없으면 배치된 인스턴스의 필터 */
		FString PawnClass;
		TOptional<FVector> SpawnLocation;
		TOptional<FVector> PlayerLocation;
		TArray<FEventSpec> Events;
		/** 있으면 트리가 멈춰도 끝내지 않는다 — duration 까지, 또는 인스턴스가 사라질 때까지 본다 */
		TArray<FActionSpec> Actions;
		TArray<FString> ExpectStates;
		/** 트리 시작 뒤 관측 상한(초) */
		double Duration = 30.0;
		/** 인스턴스 발견 · 트리 시작을 기다릴 상한(초) */
		double StartTimeout = 10.0;
		/** 0 = Standalone, 1 이상 = 리슨 서버 + 클라이언트 N */
		int32 Clients = 0;
	};

	/** 요청 → 시나리오. 존재 · 상태 이름 검사는 Tool 이 한다. BAD_REQUEST(details.reason) */
	bool ParseScenario(const FJsonObject& Params, FScenario& Out, FAnimMcpError& OutError);

	/** JSON 왕복 — 테스트 명령에 싣는 형식. ParseScenario 가 다시 읽는다 */
	TSharedRef<FJsonObject> ScenarioToJson(const FScenario& Scenario);

	/** "<클래스 이름> <JSON>" */
	FString MakeTestCommand(const FString& ScenarioJson);

	struct FSample
	{
		double T = 0.0;
		TArray<FString> ActiveStates;
		FString RunStatus;
		/** 엔진의 상태 진입 횟수. 앞 표본보다 2 이상 늘면 그 사이 이름이 안 보인 상태가 있었다 */
		int32 StateChanges = 0;
	};

	/**
	 * 기대 순서 판정. 기대 상태 하나당 타임라인 항목 하나를 소비하고, 다음 기대는 뒤 항목에서만 찾는다 — 사이에 다른 상태가 끼는 것은 허용한다.
	 * @return 앞에서부터 맞은 개수
	 */
	int32 CountMatchedStates(TConstArrayView<FSample> Timeline, TConstArrayView<FString> Expected);

	struct FEventResult
	{
		bool bAttempted = false;
		bool bSent = false;
		/** 보내지 못한 이유 — not_running · condition_not_met */
		FString SendFailure;
		/** 전송 뒤 상태 진입이 한 번이라도 있었다 */
		bool bTransitioned = false;
		/** ExpectState 가 활성으로 보였다 */
		bool bReachedExpected = false;
		int32 ChangesBefore = 0;
		/** 전송 뒤 늘어난 상태 진입 횟수 */
		int32 StateChanges = 0;
		double TSent = -1.0;
		double TTransition = -1.0;
		TArray<FString> StatesBefore;
		TArray<FString> StatesAfter;
	};

	/** 전송 · 전환 · 기대 상태 도달을 따로 본다. 실패 사유 문장, 통과면 빈 문자열 */
	FString JudgeEvent(const FEventSpec& Spec, const FEventResult& Result);

	struct FActionResult
	{
		bool bDone = false;
		bool bOk = false;
		/** 실패 이유 */
		FString Detail;
		double T = -1.0;
		TArray<FString> StatesBefore;
	};

	/** 실패 사유 문장, 통과면 빈 문자열 */
	FString JudgeAction(const FActionSpec& Spec, const FActionResult& Result);

	/** 프로브 Task 의 기록. 시나리오가 시작할 때 비우고 observed.probe 로 싣는다 */
	void AddProbeRecord(const TSharedRef<FJsonObject>& Record);
	void ResetProbeRecords();
	const TArray<TSharedPtr<FJsonObject>>& GetProbeRecords();

	/** PIE 가 뜬 뒤 인스턴스를 찾기 전에 부른다 — 시험 고정물용 */
	using FPrepare = TFunction<void(UWorld& ServerWorld)>;

	/** 지연 명령을 쌓는다. 호출 전에 PIE 가 없어야 한다. 트리 · 클래스 로드에 실패하면 Test 에 오류를 남기고 false */
	bool Enqueue(FAutomationTestBase& Test, const FScenario& Scenario, FPrepare Prepare = nullptr);
}
