#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimClassInterface.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimStateMachineTypes.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpAutomationRunner.h"
#include "Core/AnimMcpPropertyRules.h"
#include "Core/AnimMcpRuntimeScenario.h"
#include "Editor.h"
#include "Engine/SkeletalMesh.h"
#include "UObject/UnrealType.h"

namespace AnimMcpTools
{
	namespace
	{
		FAnimMcpError Bad(const TCHAR* Reason, const TCHAR* Field, const FString& Message, TSharedPtr<FJsonObject> Extra = nullptr)
		{
			TSharedRef<FJsonObject> Details = Extra.IsValid() ? Extra.ToSharedRef() : AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), Reason);
			if (Field) { Details->SetStringField(TEXT("field"), Field); }
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		TArray<TSharedPtr<FJsonValue>> NameArray(const TArray<FString>& Names)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FString& N : Names) { Out.Add(MakeShared<FJsonValueString>(N)); }
			return Out;
		}
	}

	void RegisterAutomationTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("run_automation_tests"),
			TEXT("Run Unreal Automation tests inside this editor (FAutomationTestFramework driven directly, no Session Frontend). Params: filter (test path prefix/substring, e.g. \"AnimGraphMcp.Smoke\" or your project's prefix such as \"MyGame.\"), timeout? (seconds per test, default 120), dry_run? (default false; only list the matching tests). Tests without latent commands finish synchronously (done=true with results); otherwise poll with poll_automation_tests(job_id)."),
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
			TEXT("Progress and results of an automation job started by run_automation_tests or run_anim_scenario. Params: job_id."),
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

		// Phase 7-5 — PIE 런타임 시나리오. 검증·정규화한 시나리오 JSON 을 테스트 명령 문자열에 실어 잡 하나로 돌린다(사용자 확정 ①)
		Dispatcher.RegisterTool(TEXT("run_anim_scenario"),
			TEXT("Run one Animation Blueprint inside PIE and check what it actually does (automation test AnimGraphMcp.Runtime.AnimBlueprint): spawns a SkeletalMeshActor with the AnimBP, sets variables, optionally plays a montage, waits N frames, then reads every state machine's current state and slot activity. Params: asset_path, mesh? (skeletal mesh path; default = the AnimBP's or skeleton's preview mesh), map? (PIE map override; default = current editor world), set_variables? ({name: value} on the anim instance, BlueprintVisible/BP variables), montage? (AnimMontage to Montage_Play after spawn), wait_frames? (default 10), expect? ({state_machines: {Machine: State}, slots_active: [SlotName]}), timeout? (seconds, default 120; on timeout PIE is ended). Expectations are validated against the compiled class before PIE starts. Returns the automation job (never synchronous) — poll_automation_tests(job_id) until done; the test result carries observed{state_machines{name: {state, elapsed}}, slots{name: bool}, montage_playing}."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				if (GEditor && GEditor->PlayWorld)
				{
					OutError = Bad(TEXT("PIE_ACTIVE"), nullptr, TEXT("PIE is already active — the runtime scenario must start PIE itself (end the current session first)"));
					return nullptr;
				}

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				if (Blueprint->BlueprintType == BPTYPE_Interface)
				{
					OutError = Bad(TEXT("NOT_ANIM_BLUEPRINT"), TEXT("asset_path"), TEXT("A layer interface cannot run — give an Animation Blueprint"));
					return nullptr;
				}
				UClass* GeneratedClass = Blueprint->GeneratedClass;
				IAnimClassInterface* ClassInterface = GeneratedClass ? IAnimClassInterface::GetFromClass(GeneratedClass) : nullptr;
				if (!ClassInterface)
				{
					OutError = Bad(TEXT("NOT_COMPILED"), TEXT("asset_path"), FString::Printf(TEXT("'%s' has no compiled anim class — compile it first"), *Blueprint->GetPathName()));
					return nullptr;
				}
				USkeleton* Skeleton = Blueprint->TargetSkeleton;

				// 메시 — 지정 > ABP 프리뷰 > 스켈레톤 프리뷰
				USkeletalMesh* Mesh = nullptr;
				const FString MeshPath = Context.Request.GetOptionalString(TEXT("mesh"));
				if (!MeshPath.IsEmpty())
				{
					Mesh = Cast<USkeletalMesh>(AnimMcpAssetResolver::LoadAssetOfClass(MeshPath, USkeletalMesh::StaticClass(), OutError));
					if (!Mesh) { return nullptr; }
				}
				else
				{
					Mesh = Blueprint->GetPreviewMesh(true);
					if (!Mesh && Skeleton)
					{
						Mesh = Skeleton->GetPreviewMesh(true);
					}
					if (!Mesh)
					{
						OutError = Bad(TEXT("NO_PREVIEW_MESH"), TEXT("mesh"), TEXT("Neither the Animation Blueprint nor its skeleton has a preview mesh — pass 'mesh'"));
						return nullptr;
					}
				}
				// 엔진이 인스턴스를 만들지 말지 보는 기준 그대로(SkeletalMeshComponent.cpp:883 — IsCompatibleMesh(Mesh, false): 본 이름 집합, 부모 사슬 검사 없음).
				// 본 이름이 같은 다른 스켈레톤(UE5 마네킹 계열)은 통과한다 — 실측
				if (Skeleton && !Skeleton->IsCompatibleMesh(Mesh, /*bDoParentChainCheck*/ false))
				{
					TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
					Extra->SetStringField(TEXT("skeleton"), Skeleton->GetPathName());
					Extra->SetStringField(TEXT("mesh"), Mesh->GetPathName());
					OutError = Bad(TEXT("SKELETON_MISMATCH"), TEXT("mesh"), FString::Printf(TEXT("Mesh '%s' is not compatible with the AnimBP skeleton '%s'"), *Mesh->GetName(), *Skeleton->GetName()), Extra);
					return nullptr;
				}

				// 몽타주
				UAnimMontage* Montage = nullptr;
				const FString MontagePath = Context.Request.GetOptionalString(TEXT("montage"));
				if (!MontagePath.IsEmpty())
				{
					Montage = Cast<UAnimMontage>(AnimMcpAssetResolver::LoadAssetOfClass(MontagePath, UAnimMontage::StaticClass(), OutError));
					if (!Montage) { return nullptr; }
					if (Skeleton && Montage->GetSkeleton() && !Skeleton->IsCompatibleForEditor(Montage->GetSkeleton()))
					{
						TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
						Extra->SetStringField(TEXT("skeleton"), Skeleton->GetPathName());
						Extra->SetStringField(TEXT("montage_skeleton"), Montage->GetSkeleton()->GetPathName());
						OutError = Bad(TEXT("SKELETON_MISMATCH"), TEXT("montage"), FString::Printf(TEXT("Montage '%s' uses a different skeleton than the AnimBP"), *Montage->GetName()), Extra);
						return nullptr;
					}
				}

				// 프레임 · 타임아웃 · 맵
				const double WaitFrames = Context.Request.GetOptionalNumber(TEXT("wait_frames"), 10.0);
				if (!(WaitFrames >= 1.0 && WaitFrames <= 100000.0) || !FMath::IsNearlyEqual(WaitFrames, FMath::RoundToDouble(WaitFrames)))
				{
					OutError = Bad(TEXT("BAD_WAIT_FRAMES"), TEXT("wait_frames"), TEXT("'wait_frames' must be an integer between 1 and 100000"));
					return nullptr;
				}
				const double Timeout = Context.Request.GetOptionalNumber(TEXT("timeout"), 120.0);
				const FString Map = Context.Request.GetOptionalString(TEXT("map"));

				TSharedRef<FJsonObject> Scenario = AnimMcpJson::MakeObject();
				Scenario->SetStringField(TEXT("asset_path"), Blueprint->GetPathName());
				Scenario->SetStringField(TEXT("mesh"), Mesh->GetPathName());
				if (Montage) { Scenario->SetStringField(TEXT("montage"), Montage->GetPathName()); }
				if (!Map.IsEmpty()) { Scenario->SetStringField(TEXT("map"), Map); }
				Scenario->SetNumberField(TEXT("wait_frames"), WaitFrames);

				// 변수 — 컴파일된 클래스의 프로퍼티여야 하고 값은 ImportText 로 변환 가능해야 한다 (적용은 PIE 안에서)
				TArray<FString> VariableNames;
				for (TFieldIterator<FProperty> It(GeneratedClass); It; ++It)
				{
					if (It->HasAnyPropertyFlags(CPF_BlueprintVisible)) { VariableNames.Add(It->GetName()); }
				}
				const TSharedPtr<FJsonObject>* Variables = nullptr;
				if (Context.Request.Params->TryGetObjectField(TEXT("set_variables"), Variables) && Variables->IsValid())
				{
					TSharedRef<FJsonObject> Copy = AnimMcpJson::MakeObject();
					for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Variables)->Values)
					{
						FProperty* Property = GeneratedClass->FindPropertyByName(FName(*Pair.Key));
						if (!Property)
						{
							TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
							Extra->SetArrayField(TEXT("variables"), NameArray(VariableNames));
							OutError = Bad(TEXT("VARIABLE_NOT_FOUND"), TEXT("set_variables"), FString::Printf(TEXT("'%s' is not a variable of %s"), *Pair.Key, *GeneratedClass->GetName()), Extra);
							return nullptr;
						}
						FString Text;
						FAnimMcpError ValueError;
						if (!AnimMcpPropertyRules::JsonToImportText(Property, Pair.Value, Text, ValueError))
						{
							OutError = Bad(TEXT("BAD_VALUE"), TEXT("set_variables"), FString::Printf(TEXT("'%s': %s"), *Pair.Key, *ValueError.Message));
							return nullptr;
						}
						Copy->SetField(Pair.Key, Pair.Value);
					}
					Scenario->SetObjectField(TEXT("set_variables"), Copy);
				}

				// 기대값 — 상태머신·상태 이름은 컴파일된 클래스의 BakedStateMachines 에 있어야 한다
				const TArray<FBakedAnimationStateMachine>& Machines = ClassInterface->GetBakedStateMachines();
				TArray<FString> MachineNames;
				for (const FBakedAnimationStateMachine& M : Machines) { MachineNames.Add(M.MachineName.ToString()); }
				TSharedRef<FJsonObject> ExpectStates = AnimMcpJson::MakeObject();
				TArray<TSharedPtr<FJsonValue>> ExpectSlots;
				const TSharedPtr<FJsonObject>* Expect = nullptr;
				if (Context.Request.Params->TryGetObjectField(TEXT("expect"), Expect) && Expect->IsValid())
				{
					const TSharedPtr<FJsonObject>* ExpectMachines = nullptr;
					if ((*Expect)->TryGetObjectField(TEXT("state_machines"), ExpectMachines) && ExpectMachines->IsValid())
					{
						for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*ExpectMachines)->Values)
						{
							const FBakedAnimationStateMachine* Machine = Machines.FindByPredicate([&Pair](const FBakedAnimationStateMachine& M) { return M.MachineName.ToString() == Pair.Key; });
							if (!Machine)
							{
								TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
								Extra->SetArrayField(TEXT("state_machines"), NameArray(MachineNames));
								OutError = Bad(TEXT("STATE_MACHINE_NOT_FOUND"), TEXT("expect.state_machines"), FString::Printf(TEXT("State machine '%s' does not exist in '%s'"), *Pair.Key, *Blueprint->GetName()), Extra);
								return nullptr;
							}
							FString State;
							if (!Pair.Value.IsValid() || !Pair.Value->TryGetString(State) || State.IsEmpty())
							{
								OutError = Bad(TEXT("BAD_STATE"), TEXT("expect.state_machines"), FString::Printf(TEXT("Expected state for '%s' must be a non-empty string"), *Pair.Key));
								return nullptr;
							}
							TArray<FString> StateNames;
							for (const FBakedAnimationState& St : Machine->States) { StateNames.Add(St.StateName.ToString()); }
							if (!StateNames.Contains(State))
							{
								TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
								Extra->SetArrayField(TEXT("states"), NameArray(StateNames));
								OutError = Bad(TEXT("STATE_NOT_FOUND"), TEXT("expect.state_machines"), FString::Printf(TEXT("State '%s' does not exist in state machine '%s'"), *State, *Pair.Key), Extra);
								return nullptr;
							}
							ExpectStates->SetStringField(Pair.Key, State);
						}
					}
					const TArray<TSharedPtr<FJsonValue>>* Slots = nullptr;
					if ((*Expect)->TryGetArrayField(TEXT("slots_active"), Slots))
					{
						for (const TSharedPtr<FJsonValue>& V : *Slots)
						{
							FString Slot;
							if (!V.IsValid() || !V->TryGetString(Slot) || Slot.IsEmpty())
							{
								OutError = Bad(TEXT("BAD_SLOT"), TEXT("expect.slots_active"), TEXT("'slots_active' must be an array of non-empty slot names"));
								return nullptr;
							}
							ExpectSlots.Add(MakeShared<FJsonValueString>(Slot));
						}
					}
				}
				if (ExpectSlots.Num() > 0 && !Montage)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("NO_MONTAGE"), TEXT("slots_active is expected but the scenario plays no montage — slots only become active while a montage plays"));
				}
				TSharedRef<FJsonObject> ExpectOut = AnimMcpJson::MakeObject();
				ExpectOut->SetObjectField(TEXT("state_machines"), ExpectStates);
				ExpectOut->SetArrayField(TEXT("slots_active"), ExpectSlots);
				Scenario->SetObjectField(TEXT("expect"), ExpectOut);

				const FString ScenarioJson = AnimMcpJson::ToString(Scenario);
				const FString Name = Blueprint->GetName();
				TArray<FAutomationTestInfo> Tests;
				Tests.Emplace(Name, FString::Printf(TEXT("%s.%s"), AnimMcpRuntimeScenario::TestPath, *Name), AnimMcpRuntimeScenario::MakeTestCommand(ScenarioJson),
					EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter, /*NumParticipants*/ 1, ScenarioJson);
				TSharedPtr<AnimMcpAutomationRunner::FJob> Job = AnimMcpAutomationRunner::StartJobWithTests(FString::Printf(TEXT("run_anim_scenario %s"), *Name), MoveTemp(Tests), Timeout, OutError);
				if (!Job.IsValid()) { return nullptr; }

				TSharedRef<FJsonObject> Result = AnimMcpAutomationRunner::DescribeJob(*Job);
				Result->SetObjectField(TEXT("scenario"), Scenario);
				Result->SetArrayField(TEXT("state_machines"), NameArray(MachineNames));
				return Result;
			});
	}
}
