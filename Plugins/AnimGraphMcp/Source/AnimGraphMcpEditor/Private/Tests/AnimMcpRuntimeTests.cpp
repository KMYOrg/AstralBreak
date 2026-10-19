// Phase 7-5 — PIE 런타임 검증. "구조가 말이 되는가"(6-5 스모크) 다음의 "실제로 그 상태로 가는가".
// run_anim_scenario Tool 이 "<클래스 이름> <JSON>" 명령으로 시작한다(Core/AnimMcpRuntimeScenario.h). 직접 필터로 돌리면 시나리오가 없어 경고만 남기고 통과.
//
// 지연 명령 흐름(프레임마다 러너의 FTSTicker 가 ExecuteLatentCommands 를 부른다 — 엔진 루프에서 코어 티커는 에디터 Tick 앞):
//   ① PIE 요청(GEditor->RequestPlaySession, 엔진 FStartPIECommand 와 같은 경로 AutomationEditorCommon.cpp:859-878)
//   ② PlayWorld 가 BeginPlay 될 때까지 대기(요청이 버려지면 오류)
//   ③ PIE 월드에 ASkeletalMeshActor 스폰 → 메시 → SetAnimInstanceClass(즉시 InitAnim, SkeletalMeshComponent.cpp:3458-3480) → 변수(리플렉션 ImportText) → 몽타주 재생
//   ④ wait_frames 대기
//   ⑤ 모든 상태머신의 현재 상태(GetStateMachineIndex + GetCurrentStateName) · 슬롯 활성(IsSlotActive) 관측 → 기대값과 비교(불일치 = AddError)
//   ⑥ 관측을 AnimMcpRuntimeScenario 슬롯에 기록 → RequestEndPlayMap
//   ⑦ PlayWorld 소멸 대기
// 러너의 테스트별 타임아웃이 걸리면 러너가 PIE 를 끝낸다(AnimMcpAutomationRunner::FinishCurrent).

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimClassInterface.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimStateMachineTypes.h"
#include "Animation/SkeletalMeshActor.h"
#include "Bridge/AnimMcpTypes.h"
#include "Components/SkeletalMeshComponent.h"
#include "Core/AnimMcpPropertyRules.h"
#include "Core/AnimMcpRuntimeScenario.h"
#include "Editor.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "PlayInEditorDataTypes.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UnrealType.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpRuntimeAnimBlueprintTest, "AnimGraphMcp.Runtime.AnimBlueprint", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

namespace
{
	struct FRunState
	{
		FString AssetPath;
		FString MeshPath;
		FString MontagePath;
		FString Map;
		TSharedPtr<FJsonObject> SetVariables;
		int32 WaitFrames = 10;
		TMap<FString, FString> ExpectStates;
		TArray<FString> ExpectSlots;

		// PIE 기동 중 GC 에 대비해 강참조
		TStrongObjectPtr<UAnimBlueprint> Blueprint;
		TStrongObjectPtr<USkeletalMesh> Mesh;
		TStrongObjectPtr<UAnimMontage> Montage;
		TWeakObjectPtr<UAnimInstance> Instance;

		int32 FramesWaitingPie = 0;
		int32 FramesWaited = 0;
		bool bAborted = false;
		TSharedRef<FJsonObject> Observed = AnimMcpJson::MakeObject();
	};

	/** ADD_LATENT_AUTOMATION_COMMAND 매크로는 람다 본문의 쉼표에 취약하다 → 직접 큐잉 */
	void Step(TFunction<bool()> Fn)
	{
		FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(MoveTemp(Fn)));
	}
}

bool FAnimMcpRuntimeAnimBlueprintTest::RunTest(const FString& Parameters)
{
	if (Parameters.TrimStartAndEnd().IsEmpty())
	{
		AddWarning(TEXT("No scenario given — this test is driven by the run_anim_scenario tool (nothing checked)"));
		return true;
	}

	TSharedPtr<FJsonObject> Json;
	FString ParseError;
	if (!AnimMcpJson::Parse(Parameters, Json, ParseError) || !Json.IsValid())
	{
		AddError(FString::Printf(TEXT("Scenario is not a JSON object: %s"), *ParseError));
		return false;
	}

	TSharedRef<FRunState> S = MakeShared<FRunState>();
	Json->TryGetStringField(TEXT("asset_path"), S->AssetPath);
	Json->TryGetStringField(TEXT("mesh"), S->MeshPath);
	Json->TryGetStringField(TEXT("montage"), S->MontagePath);
	Json->TryGetStringField(TEXT("map"), S->Map);
	double WaitFrames = 10.0;
	if (Json->TryGetNumberField(TEXT("wait_frames"), WaitFrames))
	{
		S->WaitFrames = FMath::Max(1, FMath::RoundToInt32(WaitFrames));
	}
	const TSharedPtr<FJsonObject>* Vars = nullptr;
	if (Json->TryGetObjectField(TEXT("set_variables"), Vars) && Vars->IsValid())
	{
		S->SetVariables = *Vars;
	}
	const TSharedPtr<FJsonObject>* Expect = nullptr;
	if (Json->TryGetObjectField(TEXT("expect"), Expect) && Expect->IsValid())
	{
		const TSharedPtr<FJsonObject>* Machines = nullptr;
		if ((*Expect)->TryGetObjectField(TEXT("state_machines"), Machines) && Machines->IsValid())
		{
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Machines)->Values)
			{
				S->ExpectStates.Add(Pair.Key, Pair.Value.IsValid() ? Pair.Value->AsString() : FString());
			}
		}
		const TArray<TSharedPtr<FJsonValue>>* Slots = nullptr;
		if ((*Expect)->TryGetArrayField(TEXT("slots_active"), Slots))
		{
			for (const TSharedPtr<FJsonValue>& V : *Slots)
			{
				if (V.IsValid()) { S->ExpectSlots.Add(V->AsString()); }
			}
		}
	}

	// 로드는 PIE 전에 에디터 월드에서
	S->Blueprint.Reset(LoadObject<UAnimBlueprint>(nullptr, *S->AssetPath));
	if (!S->Blueprint.IsValid() || !S->Blueprint->GeneratedClass)
	{
		AddError(FString::Printf(TEXT("Animation Blueprint '%s' could not be loaded or has no generated class (compile it first)"), *S->AssetPath));
		return false;
	}
	S->Mesh.Reset(LoadObject<USkeletalMesh>(nullptr, *S->MeshPath));
	if (!S->Mesh.IsValid())
	{
		AddError(FString::Printf(TEXT("Skeletal mesh '%s' could not be loaded"), *S->MeshPath));
		return false;
	}
	if (!S->MontagePath.IsEmpty())
	{
		S->Montage.Reset(LoadObject<UAnimMontage>(nullptr, *S->MontagePath));
		if (!S->Montage.IsValid())
		{
			AddError(FString::Printf(TEXT("Montage '%s' could not be loaded"), *S->MontagePath));
			return false;
		}
	}
	if (!GEditor || GEditor->PlayWorld)
	{
		AddError(TEXT("PIE is already active — end it before running a runtime scenario"));
		return false;
	}

	// ① PIE 요청
	Step([S]() -> bool
	{
		FRequestPlaySessionParams Params;
		if (!S->Map.IsEmpty())
		{
			Params.GlobalMapOverride = S->Map;
		}
		GEditor->RequestPlaySession(Params);
		return true;
	});

	// ② PlayWorld BeginPlay 대기
	Step([S, this]() -> bool
	{
		UWorld* World = GEditor->PlayWorld;
		if (World && World->HasBegunPlay())
		{
			return true;
		}
		++S->FramesWaitingPie;
		// 요청은 다음 에디터 Tick 에 동기로 시작된다(StartQueuedPlaySessionRequest) — 몇 프레임 뒤에도 세션이 없으면 버려진 것
		if (S->FramesWaitingPie > 5 && !World && !GEditor->IsPlaySessionInProgress())
		{
			AddError(TEXT("PIE did not start (the play session request was dropped — see LogPlayLevel)"));
			S->bAborted = true;
			return true;
		}
		return false;
	});

	// ③ 스폰 · ABP · 변수 · 몽타주
	Step([S, this]() -> bool
	{
		if (S->bAborted) { return true; }
		UWorld* World = GEditor->PlayWorld;
		if (!World)
		{
			AddError(TEXT("PIE world disappeared before the actor could be spawned"));
			S->bAborted = true;
			return true;
		}
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		SpawnParams.ObjectFlags |= RF_Transient;
		ASkeletalMeshActor* Actor = World->SpawnActor<ASkeletalMeshActor>(ASkeletalMeshActor::StaticClass(), FTransform::Identity, SpawnParams);
		if (!Actor || !Actor->GetSkeletalMeshComponent())
		{
			AddError(TEXT("Could not spawn ASkeletalMeshActor in the PIE world"));
			S->bAborted = true;
			return true;
		}
		USkeletalMeshComponent* Component = Actor->GetSkeletalMeshComponent();
		// 화면에 안 보여도 매 프레임 포즈를 평가하게
		Component->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
		Component->bEnableUpdateRateOptimizations = false;
		Component->SetSkeletalMesh(S->Mesh.Get());
		Component->SetAnimInstanceClass(S->Blueprint->GeneratedClass);
		UAnimInstance* Instance = Component->GetAnimInstance();
		if (!Instance)
		{
			AddError(FString::Printf(TEXT("No AnimInstance was created for '%s' on mesh '%s' (skeleton mismatch?)"), *S->AssetPath, *S->MeshPath));
			S->bAborted = true;
			return true;
		}
		S->Instance = Instance;
		S->Observed->SetStringField(TEXT("anim_instance_class"), Instance->GetClass()->GetPathName());

		if (S->SetVariables.IsValid())
		{
			TSharedRef<FJsonObject> Applied = AnimMcpJson::MakeObject();
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : S->SetVariables->Values)
			{
				FProperty* Property = Instance->GetClass()->FindPropertyByName(FName(*Pair.Key));
				if (!Property)
				{
					AddError(FString::Printf(TEXT("Variable '%s' does not exist on %s"), *Pair.Key, *Instance->GetClass()->GetName()));
					continue;
				}
				FString Text;
				FAnimMcpError Error;
				if (!AnimMcpPropertyRules::JsonToImportText(Property, Pair.Value, Text, Error))
				{
					AddError(FString::Printf(TEXT("Variable '%s': %s"), *Pair.Key, *Error.Message));
					continue;
				}
				void* ValuePtr = Property->ContainerPtrToValuePtr<void>(Instance);
				if (!Property->ImportText_Direct(*Text, ValuePtr, Instance, PPF_None))
				{
					AddError(FString::Printf(TEXT("Variable '%s': ImportText rejected '%s'"), *Pair.Key, *Text));
					continue;
				}
				Applied->SetStringField(Pair.Key, Text);
			}
			S->Observed->SetObjectField(TEXT("variables_applied"), Applied);
		}

		if (S->Montage.IsValid())
		{
			const float Length = Instance->Montage_Play(S->Montage.Get());
			S->Observed->SetNumberField(TEXT("montage_length"), Length);
			if (Length <= 0.f)
			{
				AddError(FString::Printf(TEXT("Montage_Play('%s') returned %g — the montage did not start (skeleton/slot mismatch?)"), *S->MontagePath, Length));
			}
		}
		return true;
	});

	// ④ 프레임 대기
	Step([S]() -> bool
	{
		if (S->bAborted) { return true; }
		return ++S->FramesWaited >= S->WaitFrames;
	});

	// ⑤ 관측 · 비교
	Step([S, this]() -> bool
	{
		if (S->bAborted) { return true; }
		UAnimInstance* Instance = S->Instance.Get();
		if (!Instance)
		{
			AddError(TEXT("AnimInstance was destroyed while waiting"));
			S->bAborted = true;
			return true;
		}

		TSharedRef<FJsonObject> Machines = AnimMcpJson::MakeObject();
		if (IAnimClassInterface* ClassInterface = IAnimClassInterface::GetFromClass(Instance->GetClass()))
		{
			for (const FBakedAnimationStateMachine& Machine : ClassInterface->GetBakedStateMachines())
			{
				TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
				const int32 Index = Instance->GetStateMachineIndex(Machine.MachineName);
				if (Index == INDEX_NONE)
				{
					O->SetStringField(TEXT("state"), FString());
					O->SetBoolField(TEXT("found"), false);
				}
				else
				{
					O->SetStringField(TEXT("state"), Instance->GetCurrentStateName(Index).ToString());
					O->SetNumberField(TEXT("elapsed"), Instance->GetInstanceCurrentStateElapsedTime(Index));
				}
				Machines->SetObjectField(Machine.MachineName.ToString(), O);
			}
		}
		S->Observed->SetObjectField(TEXT("state_machines"), Machines);
		for (const TPair<FString, FString>& Expected : S->ExpectStates)
		{
			const TSharedPtr<FJsonObject>* Found = nullptr;
			if (!Machines->TryGetObjectField(Expected.Key, Found) || !Found->IsValid())
			{
				AddError(FString::Printf(TEXT("State machine '%s' not found in the running instance"), *Expected.Key));
				continue;
			}
			const FString Actual = (*Found)->GetStringField(TEXT("state"));
			if (Actual != Expected.Value)
			{
				AddError(FString::Printf(TEXT("State machine '%s': expected state '%s' but it is in '%s' after %d frames"), *Expected.Key, *Expected.Value, *Actual, S->FramesWaited));
			}
		}

		TSet<FString> SlotNames(S->ExpectSlots);
		if (S->Montage.IsValid())
		{
			for (const FSlotAnimationTrack& Track : S->Montage->SlotAnimTracks)
			{
				SlotNames.Add(Track.SlotName.ToString());
			}
		}
		TSharedRef<FJsonObject> Slots = AnimMcpJson::MakeObject();
		for (const FString& Slot : SlotNames)
		{
			Slots->SetBoolField(Slot, Instance->IsSlotActive(FName(*Slot)));
		}
		S->Observed->SetObjectField(TEXT("slots"), Slots);
		for (const FString& Slot : S->ExpectSlots)
		{
			if (!Slots->GetBoolField(Slot))
			{
				AddError(FString::Printf(TEXT("Slot '%s' is not active after %d frames"), *Slot, S->FramesWaited));
			}
		}
		if (S->Montage.IsValid())
		{
			S->Observed->SetBoolField(TEXT("montage_playing"), Instance->Montage_IsPlaying(S->Montage.Get()));
		}
		S->Observed->SetNumberField(TEXT("frames_waited"), S->FramesWaited);
		return true;
	});

	// ⑥ 관측 기록 · PIE 종료
	Step([S]() -> bool
	{
		S->Observed->SetBoolField(TEXT("aborted"), S->bAborted);
		AnimMcpRuntimeScenario::SetObservation(AnimMcpJson::ToString(S->Observed));
		if (GEditor->PlayWorld)
		{
			GEditor->RequestEndPlayMap();
		}
		return true;
	});

	// ⑦ PlayWorld 소멸 대기 (RequestEndPlayMap 은 다음 Tick 에 EndPlayMap)
	Step([]() -> bool
	{
		return GEditor->PlayWorld == nullptr;
	});

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
