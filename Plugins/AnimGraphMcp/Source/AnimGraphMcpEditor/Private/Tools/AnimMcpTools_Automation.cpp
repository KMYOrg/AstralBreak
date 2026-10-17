#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAutomationRunner.h"

namespace AnimMcpTools
{
	void RegisterAutomationTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("run_automation_tests"),
			TEXT("Run Unreal Automation tests inside this editor (FAutomationTestFramework driven directly, no Session Frontend). Params: filter (test path prefix/substring, e.g. \"AstralBreak.\" or \"AnimGraphMcp.Smoke\"), timeout? (seconds per test, default 120), dry_run? (default false; only list the matching tests). Tests without latent commands finish synchronously (done=true with results); otherwise poll with poll_automation_tests(job_id)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const FString Filter = Context.Request.GetOptionalString(TEXT("filter"));
				const double Timeout = Context.Request.GetOptionalNumber(TEXT("timeout"), 120.0);
				const bool bDryRun = Context.Request.GetOptionalBool(TEXT("dry_run"), false);
				if (Filter.TrimStartAndEnd().IsEmpty())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'filter' is required (use \".\" to match every test)"));
					return nullptr;
				}
				if (bDryRun)
				{
					TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
					TArray<TSharedPtr<FJsonValue>> Tests;
					for (const FAutomationTestInfo& Info : AnimMcpAutomationRunner::FindTests(Filter))
					{
						Tests.Add(MakeShared<FJsonValueObject>(AnimMcpAutomationRunner::DescribeTestInfo(Info)));
					}
					Result->SetStringField(TEXT("filter"), Filter);
					Result->SetNumberField(TEXT("total"), Tests.Num());
					Result->SetArrayField(TEXT("tests"), Tests);
					Result->SetBoolField(TEXT("dry_run"), true);
					return Result;
				}
				TSharedPtr<AnimMcpAutomationRunner::FJob> Job = AnimMcpAutomationRunner::StartJob(Filter, Timeout, OutError);
				if (!Job.IsValid()) { return nullptr; }
				if (Job->Tests.Num() == 0)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("NO_TESTS"), FString::Printf(TEXT("No automation test matches '%s'"), *Filter));
				}
				return AnimMcpAutomationRunner::DescribeJob(*Job);
			});

		Dispatcher.RegisterTool(TEXT("poll_automation_tests"),
			TEXT("Progress and results of an automation job started by run_automation_tests. Params: job_id."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString JobId;
				if (!Context.Request.GetRequiredString(TEXT("job_id"), JobId, OutError)) { return nullptr; }
				TSharedPtr<AnimMcpAutomationRunner::FJob> Job = AnimMcpAutomationRunner::FindJob(JobId);
				if (!Job.IsValid())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Unknown automation job '%s' (jobs are kept for the editor session, last 16)"), *JobId));
					return nullptr;
				}
				return AnimMcpAutomationRunner::DescribeJob(*Job);
			});
	}
}
