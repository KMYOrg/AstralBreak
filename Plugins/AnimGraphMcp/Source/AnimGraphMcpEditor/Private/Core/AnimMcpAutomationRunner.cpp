#include "AnimMcpAutomationRunner.h"

#include "AnimMcpLog.h"
#include "Bridge/AnimMcpTypes.h"
#include "Editor.h"
#include "Misc/AutomationEvent.h"
#include "Misc/Guid.h"

namespace AnimMcpAutomationRunner
{
	namespace
	{
		TMap<FString, TSharedPtr<FJob>> Jobs;
		TArray<FString> JobOrder;
		constexpr int32 MaxJobs = 16;
		TSharedPtr<FJob> ActiveJob;

		void Record(FJob& Job, const FAutomationTestInfo& Info, const FString& State, const FAutomationTestExecutionInfo* Exec)
		{
			FTestResult R;
			R.FullPath = Info.GetFullTestPath();
			R.Command = Info.GetTestName();
			R.State = State;
			if (Exec)
			{
				R.Duration = Exec->Duration;
				for (const FAutomationExecutionEntry& Entry : Exec->GetEntries())
				{
					const FString Line = Entry.Filename.IsEmpty() ? Entry.Event.Message : FString::Printf(TEXT("%s (%s:%d)"), *Entry.Event.Message, *Entry.Filename, Entry.LineNumber);
					if (Entry.Event.Type == EAutomationEventType::Error) { R.Errors.Add(Line); }
					else if (Entry.Event.Type == EAutomationEventType::Warning) { R.Warnings.Add(Line); }
				}
			}
			(State == TEXT("passed") ? Job.Passed : Job.Failed)++;
			Job.Results.Add(R);
		}

		/** 현재 테스트 종료·기록 */
		void FinishCurrent(FJob& Job, const TCHAR* ForcedState = nullptr)
		{
			FAutomationTestFramework& Framework = FAutomationTestFramework::Get();
			const FAutomationTestInfo& Info = Job.Tests[Job.Index];
			FAutomationTestExecutionInfo Exec;
			bool bOk = false;
			if (GIsAutomationTesting)
			{
				if (ForcedState)
				{
					Framework.DequeueAllCommands();
				}
				bOk = Framework.StopTest(Exec);
			}
			Record(Job, Info, ForcedState ? ForcedState : (bOk ? TEXT("passed") : TEXT("failed")), &Exec);
			Job.bCurrentStarted = false;
			++Job.Index;
		}

		/**
		 * 잡을 가능한 만큼 진행 — 동기 테스트는 연달아, latent 명령이 남은 테스트는 프레임을 넘긴다.
		 * @return true = 잡 완료
		 */
		bool Advance(FJob& Job)
		{
			FAutomationTestFramework& Framework = FAutomationTestFramework::Get();
			while (Job.Index < Job.Tests.Num())
			{
				const FAutomationTestInfo& Info = Job.Tests[Job.Index];
				if (!Job.bCurrentStarted)
				{
					if (GIsSlowTask || (GEditor && GEditor->PlayWorld))
					{
						Record(Job, Info, TEXT("not_started"), nullptr);
						Job.Results.Last().Errors.Add(TEXT("StartTestByName refuses to run while a slow task or PIE is active"));
						++Job.Index;
						continue;
					}
					Framework.StartTestByName(Info.GetTestName(), /*RoleIndex*/ 0, Info.GetFullTestPath());
					if (!GIsAutomationTesting)
					{
						Record(Job, Info, TEXT("not_started"), nullptr);
						Job.Results.Last().Errors.Add(TEXT("Test could not be started (unknown name or framework refused — see LogAutomationTest)"));
						++Job.Index;
						continue;
					}
					Job.bCurrentStarted = true;
					Job.CurrentStartedAt = FPlatformTime::Seconds();
				}
				// latent 명령 처리 — 비어 있으면 종료
				Framework.ExecuteNetworkCommands();
				if (Framework.ExecuteLatentCommands())
				{
					FinishCurrent(Job);
					continue;
				}
				if (FPlatformTime::Seconds() - Job.CurrentStartedAt > Job.TimeoutSeconds)
				{
					FinishCurrent(Job, TEXT("timeout"));
					continue;
				}
				return false; // 다음 프레임
			}
			Job.bDone = true;
			if (Job.Ticker.IsValid())
			{
				FTSTicker::GetCoreTicker().RemoveTicker(Job.Ticker);
				Job.Ticker.Reset();
			}
			if (ActiveJob.Get() == &Job)
			{
				ActiveJob.Reset();
			}
			UE_LOG(LogAnimGraphMcp, Log, TEXT("Automation job %s done: %d passed, %d failed of %d"), *Job.Id, Job.Passed, Job.Failed, Job.Tests.Num());
			return true;
		}
	}

	TArray<FAutomationTestInfo> FindTests(const FString& Filter)
	{
		FAutomationTestFramework& Framework = FAutomationTestFramework::Get();
		// 기본 RequestedTestFilter 는 스모크/엔진만일 수 있다 — 프로젝트(ProductFilter) 테스트까지 보이게 전 필터
		Framework.SetRequestedTestFilter(EAutomationTestFlags_FilterMask);
		Framework.LoadTestModules();
		TArray<FAutomationTestInfo> All;
		Framework.GetValidTestNames(All);
		TArray<FAutomationTestInfo> Out;
		const FString Trimmed = Filter.TrimStartAndEnd();
		for (const FAutomationTestInfo& Info : All)
		{
			if (Trimmed.IsEmpty() || Info.GetFullTestPath().StartsWith(Trimmed, ESearchCase::IgnoreCase) || Info.GetFullTestPath().Contains(Trimmed, ESearchCase::IgnoreCase))
			{
				Out.Add(Info);
			}
		}
		Out.Sort([](const FAutomationTestInfo& A, const FAutomationTestInfo& B) { return A.GetFullTestPath() < B.GetFullTestPath(); });
		return Out;
	}

	TSharedPtr<FJob> StartJob(const FString& Filter, double TimeoutSeconds, FAnimMcpError& OutError)
	{
		check(IsInGameThread());
		if (ActiveJob.IsValid() && !ActiveJob->bDone)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("job_id"), ActiveJob->Id);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Automation job %s is still running; poll it or wait"), *ActiveJob->Id), Details);
			return nullptr;
		}
		if (GIsAutomationTesting)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("The automation framework is already running a test (Session Frontend?)"));
			return nullptr;
		}

		TSharedPtr<FJob> Job = MakeShared<FJob>();
		Job->Id = FGuid::NewGuid().ToString(EGuidFormats::Digits).Left(12);
		Job->Filter = Filter;
		Job->TimeoutSeconds = FMath::Clamp(TimeoutSeconds, 1.0, 3600.0);
		Job->StartedAt = FPlatformTime::Seconds();
		Job->Tests = FindTests(Filter);

		if (JobOrder.Num() >= MaxJobs)
		{
			Jobs.Remove(JobOrder[0]);
			JobOrder.RemoveAt(0);
		}
		Jobs.Add(Job->Id, Job);
		JobOrder.Add(Job->Id);

		ActiveJob = Job;
		if (!Advance(*Job))
		{
			TWeakPtr<FJob> WeakJob = Job;
			Job->Ticker = FTSTicker::GetCoreTicker().AddTicker(TEXT("AnimGraphMcp.AutomationJob"), 0.0f, [WeakJob](float) -> bool
			{
				TSharedPtr<FJob> Pinned = WeakJob.Pin();
				if (!Pinned.IsValid() || Pinned->bDone)
				{
					return false;
				}
				return !Advance(*Pinned);
			});
		}
		return Job;
	}

	TSharedPtr<FJob> FindJob(const FString& JobId)
	{
		const TSharedPtr<FJob>* Found = Jobs.Find(JobId);
		return Found ? *Found : nullptr;
	}

	TSharedRef<FJsonObject> DescribeTestInfo(const FAutomationTestInfo& Info)
	{
		TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
		O->SetStringField(TEXT("name"), Info.GetFullTestPath());
		O->SetStringField(TEXT("display_name"), Info.GetDisplayName());
		O->SetStringField(TEXT("command"), Info.GetTestName());
		O->SetStringField(TEXT("source_file"), Info.GetSourceFile());
		O->SetNumberField(TEXT("source_line"), Info.GetSourceFileLine());
		return O;
	}

	TSharedRef<FJsonObject> DescribeJob(const FJob& Job)
	{
		TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
		O->SetStringField(TEXT("job_id"), Job.Id);
		O->SetStringField(TEXT("filter"), Job.Filter);
		O->SetNumberField(TEXT("total"), Job.Tests.Num());
		O->SetNumberField(TEXT("completed"), Job.Results.Num());
		O->SetNumberField(TEXT("passed"), Job.Passed);
		O->SetNumberField(TEXT("failed"), Job.Failed);
		O->SetBoolField(TEXT("done"), Job.bDone);
		O->SetBoolField(TEXT("ok"), Job.bDone && Job.Failed == 0);
		O->SetNumberField(TEXT("elapsed"), FPlatformTime::Seconds() - Job.StartedAt);
		if (!Job.bDone && Job.Index < Job.Tests.Num())
		{
			O->SetStringField(TEXT("running"), Job.Tests[Job.Index].GetFullTestPath());
		}
		TArray<TSharedPtr<FJsonValue>> Tests;
		for (const FTestResult& R : Job.Results)
		{
			TSharedRef<FJsonObject> T = AnimMcpJson::MakeObject();
			T->SetStringField(TEXT("name"), R.FullPath);
			T->SetStringField(TEXT("command"), R.Command);
			T->SetStringField(TEXT("state"), R.State);
			T->SetNumberField(TEXT("duration"), R.Duration);
			TArray<TSharedPtr<FJsonValue>> Errors, Warnings;
			for (const FString& E : R.Errors) { Errors.Add(MakeShared<FJsonValueString>(E)); }
			for (const FString& W : R.Warnings) { Warnings.Add(MakeShared<FJsonValueString>(W)); }
			T->SetArrayField(TEXT("errors"), Errors);
			T->SetArrayField(TEXT("warnings"), Warnings);
			Tests.Add(MakeShared<FJsonValueObject>(T));
		}
		O->SetArrayField(TEXT("tests"), Tests);
		return O;
	}
}
