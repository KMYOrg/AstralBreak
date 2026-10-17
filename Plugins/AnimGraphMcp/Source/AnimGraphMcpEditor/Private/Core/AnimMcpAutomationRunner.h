#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"

struct FAnimMcpError;

/**
 * Automation 테스트 러너 (Phase 6-5) — 메시징 기반 AutomationController 를 거치지 않고 FAutomationTestFramework 를 직접 구동한다.
 * 경로 = RunSmokeTests 와 같다 (AutomationTest.cpp:526-601): SetRequestedTestFilter(전 필터) → GetValidTestNames → 이름 필터 →
 *   StartTestByName(name, 0, full_path) → (latent 명령이 남으면 프레임마다 ExecuteNetworkCommands/ExecuteLatentCommands,
 *   :674-730) → 큐가 비면 StopTest(ExecutionInfo) → 다음 테스트.
 * StartTestByName 은 GIsSlowTask·PIE 중이면 거부하고(:640), 존재하지 않는 이름은 로그만 남긴다(:652) — 둘 다 GIsAutomationTesting 으로 감지.
 *
 * 잡(job): HTTP 핸들러 안에서 동기로 돌 수 있는 만큼(latent 명령이 없는 테스트) 바로 끝내고, latent 명령이 남으면 FTSTicker 로 이어간다.
 * 호출자는 응답의 done 을 보고 poll 한다. 동시에 한 잡만 돈다(프레임워크가 단일 상태).
 */
namespace AnimMcpAutomationRunner
{
	struct FTestResult
	{
		FString FullPath;
		FString Command;
		FString State;          // passed | failed | not_started | timeout
		double Duration = 0.0;
		TArray<FString> Errors;
		TArray<FString> Warnings;
	};

	struct FJob
	{
		FString Id;
		FString Filter;
		double TimeoutSeconds = 120.0;
		double StartedAt = 0.0;
		TArray<FAutomationTestInfo> Tests;
		int32 Index = 0;
		bool bCurrentStarted = false;
		double CurrentStartedAt = 0.0;
		bool bDone = false;
		int32 Passed = 0;
		int32 Failed = 0;
		TArray<FTestResult> Results;
		FTSTicker::FDelegateHandle Ticker;
	};

	/** 등록된 테스트 중 FullTestPath 가 Filter 로 시작하거나 포함하는 것 (대소문자 무시). Filter 가 비면 전부 */
	TArray<FAutomationTestInfo> FindTests(const FString& Filter);

	/** 잡 시작 — 동기로 끝낼 수 있는 테스트는 즉시 돌린다. 다른 잡이 돌고 있으면 BAD_REQUEST. 테스트 0개면 done 잡 */
	TSharedPtr<FJob> StartJob(const FString& Filter, double TimeoutSeconds, FAnimMcpError& OutError);

	TSharedPtr<FJob> FindJob(const FString& JobId);

	/** {job_id, filter, total, completed, passed, failed, done, elapsed, tests[{name, command, state, duration, errors[], warnings[]}]} */
	TSharedRef<FJsonObject> DescribeJob(const FJob& Job);

	TSharedRef<FJsonObject> DescribeTestInfo(const FAutomationTestInfo& Info);
}
