#pragma once

#include "CoreMinimal.h"

/**
 * Phase 7-5 — PIE 런타임 시나리오: Tool(run_anim_scenario) 과 Automation 테스트(Tests/AnimMcpRuntimeTests.cpp) 사이의 계약.
 *
 * 시나리오는 테스트 명령 문자열 "<테스트 클래스 이름> <JSON>" 으로 전달된다(사용자 확정 ①, 2026-10-17).
 * FAutomationTestFramework::StartTestByName 은 첫 공백 앞을 등록된 테스트 이름(= IMPLEMENT_SIMPLE_AUTOMATION_TEST 의 클래스 이름,
 * AutomationTest.h:4104-4118)으로, 뒤를 RunTest(Parameters) 로 넘긴다(AutomationTest.cpp:631, :1273-1292). 전역 상태 없이 시나리오가
 * 결과의 command 에 그대로 남는다.
 *
 * 테스트가 관측한 값(상태머신 현재 상태·슬롯 활성)은 여기 슬롯에 JSON 문자열로 남기고, 러너가 테스트를 끝낼 때 꺼내(TakeObservation)
 * 결과의 `observed` 로 붙인다. 문자열로 두는 이유: 같은 FJsonObject 를 여러 응답(run · poll)에 넣지 않기 위해(직렬화 때마다 파싱).
 */
namespace AnimMcpRuntimeScenario
{
	inline const TCHAR* const TestClassName = TEXT("FAnimMcpRuntimeAnimBlueprintTest");
	inline const TCHAR* const TestPath = TEXT("AnimGraphMcp.Runtime.AnimBlueprint");

	/** "<클래스 이름> <JSON>" */
	FString MakeTestCommand(const FString& ScenarioJson);

	void SetObservation(const FString& Json);

	/** 마지막 관측을 꺼내고 비운다. 없으면 빈 문자열 */
	FString TakeObservation();
}
