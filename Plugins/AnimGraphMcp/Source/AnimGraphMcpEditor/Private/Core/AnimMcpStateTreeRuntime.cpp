#include "AnimMcpStateTreeRuntime.h"

#include "AIController.h"
#include "AnimMcpRuntimeScenario.h"
#include "AnimMcpStateTreeAsset.h"
#include "Bridge/AnimMcpTypes.h"
#include "Components/StateTreeComponent.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameplayTagContainer.h"
#include "Misc/AutomationTest.h"
#include "Misc/OutputDevice.h"
#include "Misc/OutputDeviceNull.h"
#include "Misc/OutputDeviceRedirector.h"
#include "PlayInEditorDataTypes.h"
#include "Settings/LevelEditorPlaySettings.h"
#include "StateTree.h"
#include "StateTreeExecutionTypes.h"
#include "StateTreeInstanceData.h"
#include "StateTreeReference.h"
#include "UObject/StrongObjectPtr.h"

namespace AnimMcpStateTreeRuntime
{
	namespace
	{
		constexpr int32 MaxLogLines = 40;

		/** 인스턴스가 사라진 뒤 더 보는 초 — 파괴가 클라이언트까지 복제된 뒤의 월드 기록을 남긴다 */
		constexpr double GoneGraceSeconds = 0.5;

		/** 프로브 Task 는 트리 실행 안에서 부르므로 시나리오 상태에 닿을 길이 없다 */
		TArray<TSharedPtr<FJsonObject>> ProbeRecords;

		FAnimMcpError Bad(const TCHAR* Reason, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), Reason);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		bool ReadVector(const FJsonObject& Object, const TCHAR* Field, TOptional<FVector>& Out, FAnimMcpError& OutError)
		{
			const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
			if (!Object.HasField(Field))
			{
				return true;
			}
			double X = 0.0, Y = 0.0, Z = 0.0;
			if (!Object.TryGetArrayField(Field, Values) || Values->Num() != 3
				|| !(*Values)[0]->TryGetNumber(X) || !(*Values)[1]->TryGetNumber(Y) || !(*Values)[2]->TryGetNumber(Z))
			{
				OutError = Bad(TEXT("BAD_VECTOR"), FString::Printf(TEXT("'%s' must be [x, y, z]"), Field));
				return false;
			}
			Out = FVector(X, Y, Z);
			return true;
		}

		TSharedPtr<FJsonValue> VectorJson(const FVector& V)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			Out.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.X * 10.0) / 10.0));
			Out.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Y * 10.0) / 10.0));
			Out.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Z * 10.0) / 10.0));
			return MakeShared<FJsonValueArray>(Out);
		}

		TArray<TSharedPtr<FJsonValue>> StringsJson(TConstArrayView<FString> Values)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FString& Value : Values)
			{
				Out.Add(MakeShared<FJsonValueString>(Value));
			}
			return Out;
		}

		double Rounded(const double Seconds)
		{
			return FMath::RoundToDouble(Seconds * 1000.0) / 1000.0;
		}

		const TCHAR* NetModeName(const ENetMode Mode)
		{
			switch (Mode)
			{
			case NM_Standalone: return TEXT("Standalone");
			case NM_DedicatedServer: return TEXT("DedicatedServer");
			case NM_ListenServer: return TEXT("ListenServer");
			case NM_Client: return TEXT("Client");
			default: return TEXT("Unknown");
			}
		}

		/** StateTreeRef 는 protected 이고 getter 가 없다 */
		const UStateTree* GetComponentTree(const UStateTreeComponent& Component)
		{
			const FStructProperty* Property = CastField<FStructProperty>(UStateTreeComponent::StaticClass()->FindPropertyByName(TEXT("StateTreeRef")));
			const FStateTreeReference* Reference = Property ? Property->ContainerPtrToValuePtr<FStateTreeReference>(&Component) : nullptr;
			return Reference ? Reference->GetStateTree() : nullptr;
		}

		TArray<UWorld*> GetPieWorlds()
		{
			TArray<UWorld*> Out;
			for (const FWorldContext& Context : GEngine->GetWorldContexts())
			{
				if (Context.WorldType == EWorldType::PIE && Context.World())
				{
					Out.Add(Context.World());
				}
			}
			return Out;
		}

		UWorld* FindServerWorld()
		{
			for (UWorld* World : GetPieWorlds())
			{
				if (World->GetNetMode() != NM_Client && World->HasBegunPlay())
				{
					return World;
				}
			}
			return nullptr;
		}

		int32 CountReadyClients()
		{
			int32 Count = 0;
			for (const UWorld* World : GetPieWorlds())
			{
				if (World->GetNetMode() == NM_Client && World->HasBegunPlay())
				{
					++Count;
				}
			}
			return Count;
		}

		/** 이 트리를 쓰는 컴포넌트 — 이름 순 */
		TArray<UStateTreeComponent*> FindComponents(UWorld& World, const UStateTree& Tree, const UClass* PawnClass)
		{
			TArray<UStateTreeComponent*> Out;
			for (TActorIterator<AActor> It(&World); It; ++It)
			{
				UStateTreeComponent* Component = It->FindComponentByClass<UStateTreeComponent>();
				if (!Component || GetComponentTree(*Component) != &Tree)
				{
					continue;
				}
				if (PawnClass)
				{
					const AAIController* Controller = Cast<AAIController>(*It);
					const APawn* Pawn = Controller ? Controller->GetPawn().Get() : Cast<APawn>(*It);
					if (!Pawn || !Pawn->IsA(PawnClass))
					{
						continue;
					}
				}
				Out.Add(Component);
			}
			Out.Sort([](const UStateTreeComponent& A, const UStateTreeComponent& B) { return A.GetOwner()->GetName() < B.GetOwner()->GetName(); });
			return Out;
		}

		TArray<FString> ReadActiveStates(const UStateTreeComponent& Component)
		{
			TArray<FString> Out;
#if WITH_GAMEPLAY_DEBUGGER
			for (const FName& Name : Component.GetActiveStateNames())
			{
				Out.Add(Name.ToString());
			}
#endif
			return Out;
		}

		FString ReadRunStatus(const UStateTreeComponent& Component)
		{
			return StaticEnum<EStateTreeRunStatus>()->GetNameStringByValue(static_cast<int64>(Component.GetStateTreeRunStatus()));
		}

		/** InstanceData 도 protected 다. 컨텍스트의 GetStateChangeCount 는 WITH_STATETREE_DEBUG 전용이라 실행 상태를 직접 읽는다 */
		int32 ReadStateChanges(const UStateTreeComponent& Component)
		{
			const FStructProperty* Property = CastField<FStructProperty>(UStateTreeComponent::StaticClass()->FindPropertyByName(TEXT("InstanceData")));
			const FStateTreeInstanceData* Data = Property ? Property->ContainerPtrToValuePtr<FStateTreeInstanceData>(&Component) : nullptr;
			const FStateTreeExecutionState* Exec = Data ? Data->GetExecutionState() : nullptr;
			return Exec ? Exec->StateChangeCount : 0;
		}

		/**
		 * 트리가 왜 시작하지 않았는지 · 왜 움직이지 않았는지는 로그에만 있다. 시험은 로그 오류로 실패시키지 않으므로 여기서 모아 관측에 싣는다.
		 * FRunState 가 소유한다 — 러너가 시간 초과로 지연 명령을 버려도 소멸자가 등록을 푼다.
		 */
		class FLogCapture : public FOutputDevice
		{
		public:
			FLogCapture() { GLog->AddOutputDevice(this); }
			virtual ~FLogCapture() override { GLog->RemoveOutputDevice(this); }

			virtual void Serialize(const TCHAR* Message, const ELogVerbosity::Type Verbosity, const FName& Category) override
			{
				if (!bActive || (Verbosity & ELogVerbosity::VerbosityMask) > ELogVerbosity::Warning)
				{
					return;
				}
				const FString Name = Category.ToString();
				if ((Name.Contains(TEXT("StateTree")) || Name.Contains(TEXT("Navigation")) || Name.Contains(TEXT("PathFollowing"))) && Lines.Num() < MaxLogLines)
				{
					Lines.Add(FString::Printf(TEXT("%s: %s"), *Name, Message));
				}
			}

			/** PIE 가 뜬 뒤에 켠다 — PreBeginPIE 가 메모리의 모든 트리를 컴파일해 다른 애셋의 실패가 섞인다 */
			bool bActive = false;
			TArray<FString> Lines;
		};

		enum class EFinish : uint8
		{
			None,
			Expected,
			TreeEnded,
			Duration,
			/** 시작한 뒤 인스턴스가 사라졌다 — 폰 · 컨트롤러 파괴. 오류가 아니다 */
			InstanceGone,
			NotFound,
			NotStarted,
			WorldLost,
			PieNotStarted,
		};

		const TCHAR* FinishName(const EFinish Reason)
		{
			switch (Reason)
			{
			case EFinish::Expected: return TEXT("expected");
			case EFinish::TreeEnded: return TEXT("tree_ended");
			case EFinish::Duration: return TEXT("duration");
			case EFinish::InstanceGone: return TEXT("instance_gone");
			case EFinish::NotFound: return TEXT("instance_not_found");
			case EFinish::NotStarted: return TEXT("tree_not_started");
			case EFinish::WorldLost: return TEXT("world_lost");
			case EFinish::PieNotStarted: return TEXT("pie_not_started");
			default: return TEXT("none");
			}
		}

		struct FRunState
		{
			FScenario Scenario;
			FPrepare Prepare;
			TUniquePtr<FLogCapture> Log = MakeUnique<FLogCapture>();

			// PIE 기동 중 GC 에 대비해 강참조
			TStrongObjectPtr<UStateTree> Tree;
			TStrongObjectPtr<UClass> PawnClass;

			TWeakObjectPtr<UStateTreeComponent> Component;
			TWeakObjectPtr<APawn> Pawn;
			bool bSpawned = false;
			bool bStarted = false;
			bool bPlayerMoved = false;
			int32 InstanceCount = 0;

			int32 FramesWaitingPie = 0;
			int32 Frames = 0;
			double FirstFrameT = -1.0;
			double StartedT = -1.0;
			double EventClock = 0.0;

			TArray<FSample> Timeline;
			TArray<TSharedPtr<FJsonValue>> TimelineJson;
			int32 NextEvent = 0;
			TArray<FEventResult> EventResults;

			int32 NextAction = 0;
			TArray<FActionResult> ActionResults;
			/** 앞 동작이 끝난 시각. 첫 동작 전에는 음수 */
			double ActionClock = -1.0;
			/** 시작한 인스턴스가 사라진 시각. 없으면 음수 */
			double GoneT = -1.0;

			TOptional<FVector> PawnStart;
			FVector PawnLast = FVector::ZeroVector;
			double PawnTravel = 0.0;

			EFinish Finish = EFinish::None;
			TSharedPtr<FJsonObject> Instance;
			TSharedPtr<FJsonObject> Player;

			const FSample* LastSample() const { return Timeline.IsEmpty() ? nullptr : &Timeline.Last(); }
		};

		void RecordSample(FRunState& S, const double T)
		{
			const UStateTreeComponent* Component = S.Component.Get();
			if (!Component)
			{
				return;
			}
			const APawn* Pawn = S.Pawn.Get();
			if (Pawn)
			{
				const FVector Location = Pawn->GetActorLocation();
				if (!S.PawnStart.IsSet())
				{
					S.PawnStart = Location;
					S.PawnLast = Location;
				}
				S.PawnTravel += FVector::Dist(S.PawnLast, Location);
				S.PawnLast = Location;
			}

			FSample Sample;
			Sample.T = Rounded(T);
			Sample.ActiveStates = ReadActiveStates(*Component);
			Sample.RunStatus = ReadRunStatus(*Component);
			Sample.StateChanges = ReadStateChanges(*Component);
			const FSample* Last = S.LastSample();
			if (Last && Last->ActiveStates == Sample.ActiveStates && Last->RunStatus == Sample.RunStatus && Last->StateChanges == Sample.StateChanges)
			{
				return;
			}
			TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
			Entry->SetNumberField(TEXT("t"), Sample.T);
			Entry->SetArrayField(TEXT("active_states"), StringsJson(Sample.ActiveStates));
			Entry->SetStringField(TEXT("run_status"), Sample.RunStatus);
			Entry->SetNumberField(TEXT("state_changes"), Sample.StateChanges);
			if (Pawn)
			{
				Entry->SetField(TEXT("pawn_location"), VectorJson(S.PawnLast));
			}
			S.TimelineJson.Add(MakeShared<FJsonValueObject>(Entry));
			S.Timeline.Add(MoveTemp(Sample));
		}

		void MovePlayerIfPending(FRunState& S, UWorld& World)
		{
			if (!S.Scenario.PlayerLocation.IsSet() || S.bPlayerMoved)
			{
				return;
			}
			const APlayerController* Controller = World.GetFirstPlayerController();
			APawn* Player = Controller ? Controller->GetPawn() : nullptr;
			if (!Player)
			{
				return;
			}
			S.bPlayerMoved = true;
			const bool bMoved = Player->SetActorLocation(*S.Scenario.PlayerLocation, /*bSweep*/ false, nullptr, ETeleportType::TeleportPhysics);
			S.Player = AnimMcpJson::MakeObject();
			S.Player->SetStringField(TEXT("pawn"), Player->GetName());
			S.Player->SetBoolField(TEXT("moved"), bMoved);
			S.Player->SetField(TEXT("location"), VectorJson(Player->GetActorLocation()));
		}

		void ResolveEvent(FRunState& S, const double Now)
		{
			S.EventClock = Now;
			++S.NextEvent;
		}

		void StepEvents(FRunState& S, UStateTreeComponent& Component, const double Now)
		{
			if (S.NextEvent >= S.Scenario.Events.Num() || !S.LastSample())
			{
				return;
			}
			const FEventSpec& Spec = S.Scenario.Events[S.NextEvent];
			FEventResult& Result = S.EventResults[S.NextEvent];
			const TArray<FString>& Active = S.LastSample()->ActiveStates;
			const int32 StateChanges = S.LastSample()->StateChanges;

			if (!Result.bAttempted)
			{
				if ((!Spec.WhenState.IsEmpty() && !Active.Contains(Spec.WhenState)) || Now < S.EventClock + Spec.After)
				{
					return;
				}
				Result.bAttempted = true;
				Result.TSent = Rounded(Now);
				Result.StatesBefore = Active;
				Result.ChangesBefore = StateChanges;
				// SendStateTreeEvent 는 void 다 — 실행 중이 아니면 경고만 남기고 돌아오므로 여기서 미리 본다. '보냈다'는 큐에 넣는 호출까지 갔다는 뜻이다
				if (!Component.IsRunning())
				{
					Result.SendFailure = TEXT("not_running");
					Result.StatesAfter = Active;
					ResolveEvent(S, Now);
					return;
				}
				Component.SendStateTreeEvent(FGameplayTag::RequestGameplayTag(FName(*Spec.Tag), /*ErrorIfNotFound*/ false));
				Result.bSent = true;
				return;
			}

			// 활성 목록 비교로는 한 프레임 안에 나간 상태를 놓친다 — 전환은 진입 횟수로 본다
			Result.StateChanges = StateChanges - Result.ChangesBefore;
			if (Result.StateChanges > 0 && !Result.bTransitioned)
			{
				Result.bTransitioned = true;
				Result.TTransition = Rounded(Now);
			}
			Result.bReachedExpected = Result.bReachedExpected || (!Spec.ExpectState.IsEmpty() && Active.Contains(Spec.ExpectState));
			Result.StatesAfter = Active;

			const bool bSettled = Spec.ExpectState.IsEmpty() ? Result.bTransitioned : Result.bReachedExpected;
			if (bSettled || Now - Result.TSent >= Spec.Window)
			{
				ResolveEvent(S, Now);
			}
		}

		/** 실패하면 Detail 에 이유를 남긴다 */
		void RunAction(const FRunState& S, const FActionSpec& Spec, FActionResult& Result)
		{
			APawn* Pawn = S.Pawn.Get();
			AAIController* Controller = S.Component.IsValid() ? Cast<AAIController>(S.Component->GetOwner()) : nullptr;
			switch (Spec.Kind)
			{
			case EActionKind::Damage:
				if (Pawn)
				{
					// DamageSelf 는 프로젝트 함수다. FOutputDeviceNull 에는 찾지 못했다는 메시지가 버려지고 반환값만 남는다
					FOutputDeviceNull Output;
					Result.bOk = Pawn->CallFunctionByNameWithArguments(*FString::Printf(TEXT("DamageSelf %f"), Spec.Amount), Output, nullptr, /*bForceCallWithNonExec*/ true);
					Result.Detail = Result.bOk ? FString() : FString::Printf(TEXT("%s has no DamageSelf function"), *Pawn->GetClass()->GetName());
				}
				break;
			case EActionKind::Unpossess:
				if (Controller)
				{
					Controller->UnPossess();
					Result.bOk = Controller->GetPawn() == nullptr;
				}
				break;
			case EActionKind::Repossess:
				if (Controller && Pawn)
				{
					Controller->Possess(Pawn);
					Result.bOk = Pawn->GetController() == Controller;
				}
				break;
			case EActionKind::Destroy:
				if (Pawn)
				{
					Result.bOk = Pawn->Destroy();
				}
				break;
			case EActionKind::SpawnController:
				if (Pawn)
				{
					Pawn->SpawnDefaultController();
					Result.bOk = Pawn->GetController() != nullptr;
				}
				break;
			}
			if (!Result.bOk && Result.Detail.IsEmpty())
			{
				Result.Detail = FString::Printf(TEXT("pawn %s, controller %s"), Pawn ? TEXT("present") : TEXT("gone"), Controller ? TEXT("present") : TEXT("gone"));
			}
		}

		void StepActions(FRunState& S, const double Now)
		{
			if (S.NextAction >= S.Scenario.Actions.Num())
			{
				return;
			}
			const FActionSpec& Spec = S.Scenario.Actions[S.NextAction];
			const double Clock = S.ActionClock >= 0.0 ? S.ActionClock : (Spec.Kind == EActionKind::SpawnController ? S.FirstFrameT : S.StartedT);
			if (Clock < 0.0 || Now < Clock + Spec.After)
			{
				return;
			}
			const FSample* Last = S.LastSample();
			if (!Spec.WhenState.IsEmpty() && !(Last && Last->ActiveStates.Contains(Spec.WhenState)))
			{
				return;
			}
			FActionResult& Result = S.ActionResults[S.NextAction];
			Result.bDone = true;
			Result.T = Rounded(Now);
			Result.StatesBefore = Last ? Last->ActiveStates : TArray<FString>();
			RunAction(S, Spec, Result);
			S.ActionClock = Now;
			++S.NextAction;
		}

		/** 끝나는 프레임의 인스턴스 기록 — 멀티 PIE 판정은 클라이언트 월드가 다 붙은 뒤의 값이어야 한다 */
		TArray<TSharedPtr<FJsonValue>> DescribeWorlds(const FRunState& S)
		{
			const UWorld* ObservedWorld = S.Component.IsValid() ? S.Component->GetWorld() : nullptr;
			const UClass* PawnClass = S.Pawn.IsValid() ? S.Pawn->GetClass() : S.PawnClass.Get();
			TArray<TSharedPtr<FJsonValue>> Out;
			for (UWorld* World : GetPieWorlds())
			{
				TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
				Entry->SetStringField(TEXT("name"), World->GetName());
				Entry->SetStringField(TEXT("net_mode"), NetModeName(World->GetNetMode()));
				Entry->SetBoolField(TEXT("observed"), World == ObservedWorld);
				Entry->SetNumberField(TEXT("instances"), S.Tree.IsValid() ? FindComponents(*World, *S.Tree, nullptr).Num() : 0);
				int32 Pawns = 0;
				if (PawnClass)
				{
					for (TActorIterator<APawn> It(World, const_cast<UClass*>(PawnClass)); It; ++It)
					{
						++Pawns;
					}
				}
				Entry->SetNumberField(TEXT("pawns"), Pawns);
				Out.Add(MakeShared<FJsonValueObject>(Entry));
			}
			return Out;
		}

		/** 인스턴스를 못 찾았을 때 원인을 좁힌다 — 폰에 컨트롤러가 붙었는지, 다른 트리를 쓰는 컴포넌트가 있는지 */
		TSharedRef<FJsonObject> DescribeCandidates(const FRunState& S)
		{
			TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
			UWorld* World = FindServerWorld();
			if (!World)
			{
				return Out;
			}
			TArray<TSharedPtr<FJsonValue>> Pawns;
			for (TActorIterator<APawn> It(World, S.PawnClass.IsValid() ? S.PawnClass.Get() : APawn::StaticClass()); It; ++It)
			{
				const AController* Controller = It->GetController();
				TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
				Entry->SetStringField(TEXT("name"), It->GetName());
				Entry->SetStringField(TEXT("class"), It->GetClass()->GetPathName());
				Entry->SetStringField(TEXT("controller"), Controller ? Controller->GetClass()->GetPathName() : FString());
				Entry->SetStringField(TEXT("ai_controller_class"), GetPathNameSafe(It->AIControllerClass.Get()));
				Entry->SetStringField(TEXT("auto_possess_ai"), StaticEnum<EAutoPossessAI>()->GetNameStringByValue(static_cast<int64>(It->AutoPossessAI)));
				Pawns.Add(MakeShared<FJsonValueObject>(Entry));
			}
			Out->SetArrayField(TEXT("pawns"), Pawns);

			TArray<TSharedPtr<FJsonValue>> Components;
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (const UStateTreeComponent* Component = It->FindComponentByClass<UStateTreeComponent>())
				{
					TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
					Entry->SetStringField(TEXT("owner"), It->GetName());
					Entry->SetStringField(TEXT("tree"), GetPathNameSafe(GetComponentTree(*Component)));
					Components.Add(MakeShared<FJsonValueObject>(Entry));
				}
			}
			Out->SetArrayField(TEXT("components"), Components);
			return Out;
		}

		TSharedRef<FJsonObject> DescribeInstance(const FRunState& S)
		{
			TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
			const UStateTreeComponent* Component = S.Component.Get();
			if (!Component)
			{
				return Out;
			}
			const AActor* Owner = Component->GetOwner();
			const AAIController* Controller = Component->GetAIOwner();
			const APawn* Pawn = S.Pawn.Get();
			Out->SetStringField(TEXT("owner"), Owner ? Owner->GetName() : FString());
			Out->SetStringField(TEXT("owner_class"), Owner ? Owner->GetClass()->GetPathName() : FString());
			Out->SetStringField(TEXT("component_class"), Component->GetClass()->GetName());
			Out->SetBoolField(TEXT("ai_controller"), Controller != nullptr);
			Out->SetStringField(TEXT("pawn"), Pawn ? Pawn->GetName() : FString());
			Out->SetStringField(TEXT("pawn_class"), Pawn ? Pawn->GetClass()->GetPathName() : FString());
			Out->SetStringField(TEXT("source"), S.bSpawned ? TEXT("spawned") : TEXT("placed"));
			Out->SetBoolField(TEXT("running"), Component->IsRunning());
			return Out;
		}

		TSharedRef<FJsonObject> BuildObservation(FRunState& S, FAutomationTestBase& Test, const bool bAborted)
		{
			TSharedRef<FJsonObject> Observed = AnimMcpJson::MakeObject();
			Observed->SetStringField(TEXT("tree"), S.Scenario.TreePath);
			if (S.Tree.IsValid())
			{
				Observed->SetStringField(TEXT("revision"), AnimMcpStateTreeAsset::GetRevision(*S.Tree));
			}
			Observed->SetStringField(TEXT("finished_because"), FinishName(S.Finish));
			Observed->SetArrayField(TEXT("worlds"), DescribeWorlds(S));
			Observed->SetObjectField(TEXT("instance"), DescribeInstance(S));
			Observed->SetNumberField(TEXT("instances_found"), S.InstanceCount);
			if (S.Finish == EFinish::NotFound)
			{
				Observed->SetObjectField(TEXT("candidates"), DescribeCandidates(S));
			}
			Observed->SetBoolField(TEXT("started"), S.bStarted);
			if (S.StartedT >= 0.0)
			{
				Observed->SetNumberField(TEXT("started_at"), Rounded(S.StartedT));
			}
			Observed->SetNumberField(TEXT("frames"), S.Frames);
			Observed->SetArrayField(TEXT("timeline"), S.TimelineJson);

			if (S.PawnStart.IsSet())
			{
				Observed->SetField(TEXT("pawn_start"), VectorJson(*S.PawnStart));
				Observed->SetField(TEXT("pawn_end"), VectorJson(S.PawnLast));
				Observed->SetNumberField(TEXT("pawn_travel"), FMath::RoundToDouble(S.PawnTravel * 10.0) / 10.0);
			}
			if (S.Player.IsValid())
			{
				Observed->SetObjectField(TEXT("player"), S.Player);
			}

			// 이벤트 — 전송과 전환을 따로 싣는다
			TArray<TSharedPtr<FJsonValue>> EventsJson;
			for (int32 Index = 0; Index < S.Scenario.Events.Num(); ++Index)
			{
				const FEventSpec& Spec = S.Scenario.Events[Index];
				FEventResult& Result = S.EventResults[Index];
				if (!Result.bAttempted)
				{
					Result.SendFailure = TEXT("condition_not_met");
				}
				const FString Failure = JudgeEvent(Spec, Result);
				TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
				Entry->SetStringField(TEXT("tag"), Spec.Tag);
				Entry->SetBoolField(TEXT("sent"), Result.bSent);
				if (!Result.SendFailure.IsEmpty())
				{
					Entry->SetStringField(TEXT("send_failure"), Result.SendFailure);
				}
				Entry->SetBoolField(TEXT("transitioned"), Result.bTransitioned);
				Entry->SetNumberField(TEXT("state_changes"), Result.StateChanges);
				if (!Spec.ExpectState.IsEmpty())
				{
					Entry->SetStringField(TEXT("expect_state"), Spec.ExpectState);
					Entry->SetBoolField(TEXT("reached_expected"), Result.bReachedExpected);
				}
				Entry->SetBoolField(TEXT("expect_transition"), Spec.bExpectTransition);
				Entry->SetBoolField(TEXT("ok"), Failure.IsEmpty());
				if (Result.TSent >= 0.0) { Entry->SetNumberField(TEXT("t_sent"), Result.TSent); }
				if (Result.TTransition >= 0.0) { Entry->SetNumberField(TEXT("t_transition"), Result.TTransition); }
				Entry->SetArrayField(TEXT("states_before"), StringsJson(Result.StatesBefore));
				Entry->SetArrayField(TEXT("states_after"), StringsJson(Result.StatesAfter));
				EventsJson.Add(MakeShared<FJsonValueObject>(Entry));
				if (!Failure.IsEmpty() && !bAborted)
				{
					Test.AddError(Failure);
				}
			}
			Observed->SetArrayField(TEXT("events"), EventsJson);

			// 동작 — 실행 여부와 결과. 트리에 미친 영향은 timeline · probe 로 본다
			TArray<TSharedPtr<FJsonValue>> ActionsJson;
			for (int32 Index = 0; Index < S.Scenario.Actions.Num(); ++Index)
			{
				const FActionSpec& Spec = S.Scenario.Actions[Index];
				const FActionResult& Result = S.ActionResults[Index];
				TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
				Entry->SetStringField(TEXT("kind"), ActionName(Spec.Kind));
				Entry->SetBoolField(TEXT("done"), Result.bDone);
				Entry->SetBoolField(TEXT("ok"), Result.bOk);
				if (!Result.Detail.IsEmpty()) { Entry->SetStringField(TEXT("detail"), Result.Detail); }
				if (Result.T >= 0.0) { Entry->SetNumberField(TEXT("t"), Result.T); }
				Entry->SetArrayField(TEXT("states_before"), StringsJson(Result.StatesBefore));
				ActionsJson.Add(MakeShared<FJsonValueObject>(Entry));
				const FString Failure = JudgeAction(Spec, Result);
				if (!Failure.IsEmpty() && !bAborted)
				{
					Test.AddError(Failure);
				}
			}
			Observed->SetArrayField(TEXT("actions"), ActionsJson);
			if (S.GoneT >= 0.0)
			{
				Observed->SetNumberField(TEXT("instance_gone_at"), Rounded(S.GoneT));
			}

			TArray<TSharedPtr<FJsonValue>> ProbeJson;
			for (const TSharedPtr<FJsonObject>& Record : ProbeRecords)
			{
				ProbeJson.Add(MakeShared<FJsonValueObject>(Record));
			}
			Observed->SetArrayField(TEXT("probe"), ProbeJson);

			// 기대 순서
			if (!S.Scenario.ExpectStates.IsEmpty())
			{
				const int32 Matched = CountMatchedStates(S.Timeline, S.Scenario.ExpectStates);
				TSharedRef<FJsonObject> Expect = AnimMcpJson::MakeObject();
				Expect->SetArrayField(TEXT("states"), StringsJson(S.Scenario.ExpectStates));
				Expect->SetNumberField(TEXT("matched"), Matched);
				Expect->SetBoolField(TEXT("ok"), Matched == S.Scenario.ExpectStates.Num());
				Observed->SetObjectField(TEXT("expect"), Expect);
				if (Matched != S.Scenario.ExpectStates.Num() && !bAborted)
				{
					Test.AddError(FString::Printf(TEXT("Expected state order not observed: matched %d of %d (expected %s)"), Matched, S.Scenario.ExpectStates.Num(), *FString::Join(S.Scenario.ExpectStates, TEXT(" -> "))));
				}
			}
			GLog->Flush(); // 게임 스레드 전용 장치는 큐에서 늦게 받는다
			Observed->SetArrayField(TEXT("log"), StringsJson(S.Log->Lines));
			return Observed;
		}

		/** 한 프레임 관측. true = 끝 */
		bool TickObservation(FRunState& S, FAutomationTestBase& Test)
		{
			UWorld* World = FindServerWorld();
			if (!World)
			{
				Test.AddError(TEXT("The server PIE world disappeared during the scenario"));
				S.Finish = EFinish::WorldLost;
				return true;
			}
			const double Now = World->GetTimeSeconds();
			++S.Frames;
			if (S.FirstFrameT < 0.0)
			{
				S.FirstFrameT = Now;
			}
			MovePlayerIfPending(S, *World);

			// 인스턴스를 찾기 전에 돈다 — spawn_controller 가 있어야 인스턴스가 생기는 경우가 있다
			StepActions(S, Now);

			// 인스턴스 찾기 — 배치는 PIE 시작 때 이미 있고, 스폰은 앞 단계에서 만들었다
			if (!S.Component.IsValid())
			{
				// 시작한 뒤 사라졌으면 다시 찾지 않는다. 폰이 파괴되면 컨트롤러도 함께 파괴되는 것이 정상 경로다
				if (S.bStarted)
				{
					if (S.GoneT < 0.0)
					{
						S.GoneT = Now;
					}
					if (Now - S.GoneT >= GoneGraceSeconds)
					{
						S.Finish = EFinish::InstanceGone;
						return true;
					}
					return false;
				}
				const TArray<UStateTreeComponent*> Found = FindComponents(*World, *S.Tree, S.PawnClass.Get());
				S.InstanceCount = Found.Num();
				if (Found.IsEmpty())
				{
					if (Now - S.FirstFrameT > S.Scenario.StartTimeout)
					{
						Test.AddError(FString::Printf(TEXT("No StateTree component references '%s' in the server world after %.1f s"), *S.Scenario.TreePath, S.Scenario.StartTimeout));
						S.Finish = EFinish::NotFound;
						return true;
					}
					return false;
				}
				S.Component = Found[0];
				if (!S.Pawn.IsValid())
				{
					const AAIController* Controller = Found[0]->GetAIOwner();
					S.Pawn = Controller ? Controller->GetPawn().Get() : Cast<APawn>(Found[0]->GetOwner());
				}
			}

			UStateTreeComponent* Component = S.Component.Get();
			RecordSample(S, Now);

			if (!S.bStarted)
			{
				const FSample* Last = S.LastSample();
				if (Component->IsRunning() && Last && Last->RunStatus == TEXT("Running"))
				{
					S.bStarted = true;
					S.StartedT = Now;
					S.EventClock = Now;
				}
				else if (Now - S.FirstFrameT > S.Scenario.StartTimeout)
				{
					Test.AddError(FString::Printf(TEXT("The StateTree instance on '%s' did not start within %.1f s (run_status %s) — see observed.log"), *GetNameSafe(Component->GetOwner()), S.Scenario.StartTimeout, Last ? *Last->RunStatus : TEXT("unknown")));
					S.Finish = EFinish::NotStarted;
					return true;
				}
				else
				{
					return false;
				}
			}

			StepEvents(S, *Component, Now);

			// 기대 순서가 없으면 일찍 끝낼 근거가 없다 — duration 까지 본다
			const bool bEventsDone = S.NextEvent >= S.Scenario.Events.Num() && S.NextAction >= S.Scenario.Actions.Num();
			const bool bHasExpectation = !S.Scenario.ExpectStates.IsEmpty();
			const FSample* Last = S.LastSample();
			if (bEventsDone && bHasExpectation && CountMatchedStates(S.Timeline, S.Scenario.ExpectStates) == S.Scenario.ExpectStates.Num())
			{
				S.Finish = EFinish::Expected;
			}
			// 동작이 있으면 정지 뒤를 보려는 시나리오다 — 재빙의 · 제거까지 계속 본다
			else if (S.Scenario.Actions.IsEmpty() && Last && Last->RunStatus != TEXT("Running"))
			{
				S.Finish = EFinish::TreeEnded;
			}
			else if (Now - S.StartedT >= S.Scenario.Duration)
			{
				S.Finish = EFinish::Duration;
			}
			return S.Finish != EFinish::None;
		}

		/** ADD_LATENT_AUTOMATION_COMMAND 매크로는 람다 본문의 쉼표에 취약하다 → 직접 큐잉 */
		void Step(TFunction<bool()> Fn)
		{
			FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(MoveTemp(Fn)));
		}
	}

	bool ParseScenario(const FJsonObject& Params, FScenario& Out, FAnimMcpError& OutError)
	{
		Params.TryGetStringField(TEXT("asset_path"), Out.TreePath);
		Params.TryGetStringField(TEXT("map"), Out.Map);
		Params.TryGetStringField(TEXT("pawn_class"), Out.PawnClass);
		if (!ReadVector(Params, TEXT("spawn_location"), Out.SpawnLocation, OutError) || !ReadVector(Params, TEXT("player_location"), Out.PlayerLocation, OutError))
		{
			return false;
		}
		if (Out.SpawnLocation.IsSet() && Out.PawnClass.IsEmpty())
		{
			OutError = Bad(TEXT("SPAWN_WITHOUT_CLASS"), TEXT("'spawn_location' needs 'pawn_class'"));
			return false;
		}
		Params.TryGetNumberField(TEXT("duration"), Out.Duration);
		Params.TryGetNumberField(TEXT("start_timeout"), Out.StartTimeout);
		Params.TryGetNumberField(TEXT("clients"), Out.Clients);
		if (!(Out.Duration > 0.0 && Out.Duration <= 3600.0) || !(Out.StartTimeout > 0.0 && Out.StartTimeout <= 600.0) || Out.Clients < 0 || Out.Clients > 3)
		{
			OutError = Bad(TEXT("BAD_RANGE"), TEXT("'duration' must be in (0, 3600], 'start_timeout' in (0, 600], 'clients' in [0, 3]"));
			return false;
		}

		const TArray<TSharedPtr<FJsonValue>>* States = nullptr;
		if (Params.TryGetArrayField(TEXT("expect_states"), States))
		{
			for (const TSharedPtr<FJsonValue>& Value : *States)
			{
				FString Name;
				if (!Value->TryGetString(Name) || Name.IsEmpty())
				{
					OutError = Bad(TEXT("BAD_STATE"), TEXT("'expect_states' must be an array of non-empty state names"));
					return false;
				}
				Out.ExpectStates.Add(Name);
			}
		}

		const TArray<TSharedPtr<FJsonValue>>* Events = nullptr;
		if (Params.TryGetArrayField(TEXT("events"), Events))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Events)
			{
				const TSharedPtr<FJsonObject>* Object = nullptr;
				FEventSpec Spec;
				if (!Value->TryGetObject(Object) || !(*Object)->TryGetStringField(TEXT("tag"), Spec.Tag) || Spec.Tag.IsEmpty())
				{
					OutError = Bad(TEXT("BAD_EVENT"), TEXT("Each entry of 'events' must be an object with 'tag'"));
					return false;
				}
				(*Object)->TryGetNumberField(TEXT("after"), Spec.After);
				(*Object)->TryGetStringField(TEXT("when_state"), Spec.WhenState);
				(*Object)->TryGetStringField(TEXT("expect_state"), Spec.ExpectState);
				(*Object)->TryGetBoolField(TEXT("expect_transition"), Spec.bExpectTransition);
				(*Object)->TryGetNumberField(TEXT("window"), Spec.Window);
				if (Spec.After < 0.0 || !(Spec.Window > 0.0))
				{
					OutError = Bad(TEXT("BAD_EVENT"), TEXT("Event 'after' must be >= 0 and 'window' > 0"));
					return false;
				}
				if (!Spec.bExpectTransition && !Spec.ExpectState.IsEmpty())
				{
					OutError = Bad(TEXT("BAD_EVENT"), TEXT("Event with expect_transition=false cannot name an expect_state"));
					return false;
				}
				Out.Events.Add(MoveTemp(Spec));
			}
		}

		const TArray<TSharedPtr<FJsonValue>>* Actions = nullptr;
		if (Params.TryGetArrayField(TEXT("actions"), Actions))
		{
			for (const TSharedPtr<FJsonValue>& Value : *Actions)
			{
				const TSharedPtr<FJsonObject>* Object = nullptr;
				FString Kind;
				if (!Value->TryGetObject(Object) || !(*Object)->TryGetStringField(TEXT("kind"), Kind))
				{
					OutError = Bad(TEXT("BAD_ACTION"), TEXT("Each entry of 'actions' must be an object with 'kind'"));
					return false;
				}
				FActionSpec Spec;
				bool bKnown = false;
				for (const EActionKind Candidate : { EActionKind::Damage, EActionKind::Unpossess, EActionKind::Repossess, EActionKind::Destroy, EActionKind::SpawnController })
				{
					if (Kind == ActionName(Candidate))
					{
						Spec.Kind = Candidate;
						bKnown = true;
					}
				}
				if (!bKnown)
				{
					OutError = Bad(TEXT("BAD_ACTION"), FString::Printf(TEXT("Unknown action kind '%s' (damage, unpossess, repossess, destroy, spawn_controller)"), *Kind));
					return false;
				}
				(*Object)->TryGetNumberField(TEXT("after"), Spec.After);
				(*Object)->TryGetStringField(TEXT("when_state"), Spec.WhenState);
				(*Object)->TryGetNumberField(TEXT("amount"), Spec.Amount);
				if (Spec.After < 0.0)
				{
					OutError = Bad(TEXT("BAD_ACTION"), TEXT("Action 'after' must be >= 0"));
					return false;
				}
				if (Spec.Kind == EActionKind::Damage && !(Spec.Amount > 0.0))
				{
					OutError = Bad(TEXT("BAD_ACTION"), TEXT("Action 'damage' needs 'amount' > 0"));
					return false;
				}
				if (Spec.Kind == EActionKind::SpawnController && (!Out.Actions.IsEmpty() || !Out.SpawnLocation.IsSet() || !Spec.WhenState.IsEmpty()))
				{
					OutError = Bad(TEXT("BAD_ACTION"), TEXT("'spawn_controller' must be the first action of a scenario with 'spawn_location', and it cannot have 'when_state' — the tree is not running yet"));
					return false;
				}
				Out.Actions.Add(MoveTemp(Spec));
			}
		}
		return true;
	}

	TSharedRef<FJsonObject> ScenarioToJson(const FScenario& Scenario)
	{
		TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
		Out->SetStringField(TEXT("asset_path"), Scenario.TreePath);
		if (!Scenario.Map.IsEmpty()) { Out->SetStringField(TEXT("map"), Scenario.Map); }
		if (!Scenario.PawnClass.IsEmpty()) { Out->SetStringField(TEXT("pawn_class"), Scenario.PawnClass); }
		const auto SetVector = [&Out](const TCHAR* Field, const FVector& V)
		{
			TArray<TSharedPtr<FJsonValue>> Values;
			Values.Add(MakeShared<FJsonValueNumber>(V.X));
			Values.Add(MakeShared<FJsonValueNumber>(V.Y));
			Values.Add(MakeShared<FJsonValueNumber>(V.Z));
			Out->SetArrayField(Field, Values);
		};
		if (Scenario.SpawnLocation.IsSet()) { SetVector(TEXT("spawn_location"), *Scenario.SpawnLocation); }
		if (Scenario.PlayerLocation.IsSet()) { SetVector(TEXT("player_location"), *Scenario.PlayerLocation); }
		Out->SetNumberField(TEXT("duration"), Scenario.Duration);
		Out->SetNumberField(TEXT("start_timeout"), Scenario.StartTimeout);
		Out->SetNumberField(TEXT("clients"), Scenario.Clients);
		Out->SetArrayField(TEXT("expect_states"), StringsJson(Scenario.ExpectStates));
		TArray<TSharedPtr<FJsonValue>> Events;
		for (const FEventSpec& Spec : Scenario.Events)
		{
			TSharedRef<FJsonObject> Event = AnimMcpJson::MakeObject();
			Event->SetStringField(TEXT("tag"), Spec.Tag);
			Event->SetNumberField(TEXT("after"), Spec.After);
			if (!Spec.WhenState.IsEmpty()) { Event->SetStringField(TEXT("when_state"), Spec.WhenState); }
			if (!Spec.ExpectState.IsEmpty()) { Event->SetStringField(TEXT("expect_state"), Spec.ExpectState); }
			Event->SetBoolField(TEXT("expect_transition"), Spec.bExpectTransition);
			Event->SetNumberField(TEXT("window"), Spec.Window);
			Events.Add(MakeShared<FJsonValueObject>(Event));
		}
		Out->SetArrayField(TEXT("events"), Events);
		TArray<TSharedPtr<FJsonValue>> Actions;
		for (const FActionSpec& Spec : Scenario.Actions)
		{
			TSharedRef<FJsonObject> Action = AnimMcpJson::MakeObject();
			Action->SetStringField(TEXT("kind"), ActionName(Spec.Kind));
			Action->SetNumberField(TEXT("after"), Spec.After);
			if (!Spec.WhenState.IsEmpty()) { Action->SetStringField(TEXT("when_state"), Spec.WhenState); }
			if (Spec.Kind == EActionKind::Damage) { Action->SetNumberField(TEXT("amount"), Spec.Amount); }
			Actions.Add(MakeShared<FJsonValueObject>(Action));
		}
		Out->SetArrayField(TEXT("actions"), Actions);
		return Out;
	}

	FString MakeTestCommand(const FString& ScenarioJson)
	{
		return FString::Printf(TEXT("%s %s"), TestClassName, *ScenarioJson);
	}

	int32 CountMatchedStates(const TConstArrayView<FSample> Timeline, const TConstArrayView<FString> Expected)
	{
		int32 Matched = 0;
		for (const FSample& Sample : Timeline)
		{
			if (Matched < Expected.Num() && Sample.ActiveStates.Contains(Expected[Matched]))
			{
				++Matched;
			}
		}
		return Matched;
	}

	FString JudgeEvent(const FEventSpec& Spec, const FEventResult& Result)
	{
		if (!Result.bSent)
		{
			return FString::Printf(TEXT("Event '%s' was not sent (%s)"), *Spec.Tag, Result.SendFailure.IsEmpty() ? TEXT("condition_not_met") : *Result.SendFailure);
		}
		if (Spec.bExpectTransition && !Result.bTransitioned)
		{
			return FString::Printf(TEXT("Event '%s' was sent but no transition followed within %.1f s (expected %s, active: %s)"),
				*Spec.Tag, Spec.Window, Spec.ExpectState.IsEmpty() ? TEXT("any change") : *Spec.ExpectState, *FString::Join(Result.StatesAfter, TEXT(", ")));
		}
		if (Spec.bExpectTransition && !Spec.ExpectState.IsEmpty() && !Result.bReachedExpected)
		{
			return FString::Printf(TEXT("Event '%s' was sent and the tree entered %d state(s), but '%s' was never seen active within %.1f s (active: %s). A state entered and left within one frame is not visible — a task failing in EnterState does this"),
				*Spec.Tag, Result.StateChanges, *Spec.ExpectState, Spec.Window, *FString::Join(Result.StatesAfter, TEXT(", ")));
		}
		if (!Spec.bExpectTransition && Result.bTransitioned)
		{
			return FString::Printf(TEXT("Event '%s' must not cause a transition but the tree entered %d state(s) (active: %s)"), *Spec.Tag, Result.StateChanges, *FString::Join(Result.StatesAfter, TEXT(", ")));
		}
		return FString();
	}

	const TCHAR* ActionName(const EActionKind Kind)
	{
		switch (Kind)
		{
		case EActionKind::Damage: return TEXT("damage");
		case EActionKind::Unpossess: return TEXT("unpossess");
		case EActionKind::Repossess: return TEXT("repossess");
		case EActionKind::Destroy: return TEXT("destroy");
		case EActionKind::SpawnController: return TEXT("spawn_controller");
		default: return TEXT("unknown");
		}
	}

	FString JudgeAction(const FActionSpec& Spec, const FActionResult& Result)
	{
		if (!Result.bDone)
		{
			return FString::Printf(TEXT("Action '%s' did not run%s"), ActionName(Spec.Kind), Spec.WhenState.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (when_state '%s' was never active)"), *Spec.WhenState));
		}
		if (!Result.bOk)
		{
			return FString::Printf(TEXT("Action '%s' failed: %s"), ActionName(Spec.Kind), *Result.Detail);
		}
		return FString();
	}

	void AddProbeRecord(const TSharedRef<FJsonObject>& Record)
	{
		ProbeRecords.Add(Record);
	}

	void ResetProbeRecords()
	{
		ProbeRecords.Reset();
	}

	const TArray<TSharedPtr<FJsonObject>>& GetProbeRecords()
	{
		return ProbeRecords;
	}

	bool Enqueue(FAutomationTestBase& Test, const FScenario& Scenario, FPrepare Prepare)
	{
		TSharedRef<FRunState> S = MakeShared<FRunState>();
		S->Scenario = Scenario;
		S->Prepare = MoveTemp(Prepare);
		S->EventResults.SetNum(Scenario.Events.Num());
		S->ActionResults.SetNum(Scenario.Actions.Num());
		ResetProbeRecords();

		S->Tree.Reset(LoadObject<UStateTree>(nullptr, *Scenario.TreePath));
		if (!S->Tree.IsValid())
		{
			Test.AddError(FString::Printf(TEXT("StateTree '%s' could not be loaded"), *Scenario.TreePath));
			return false;
		}
		if (!Scenario.PawnClass.IsEmpty())
		{
			S->PawnClass.Reset(LoadObject<UClass>(nullptr, *Scenario.PawnClass));
			if (!S->PawnClass.IsValid())
			{
				Test.AddError(FString::Printf(TEXT("Pawn class '%s' could not be loaded"), *Scenario.PawnClass));
				return false;
			}
		}
		if (!GEditor || GEditor->PlayWorld || GEditor->IsPlaySessionInProgress())
		{
			Test.AddError(TEXT("PIE is already active — end it before running a runtime scenario"));
			return false;
		}

		// ① PIE 요청. 사용자 플레이 설정에 끌려가지 않게 네트 모드와 인원을 항상 명시한다
		Step([S]() -> bool
		{
			FRequestPlaySessionParams Params;
			if (!S->Scenario.Map.IsEmpty())
			{
				Params.GlobalMapOverride = S->Scenario.Map;
			}
			ULevelEditorPlaySettings* Settings = NewObject<ULevelEditorPlaySettings>(GetTransientPackage()); // RequestPlaySession 이 복제해 쥔다
			Settings->SetPlayNetMode(S->Scenario.Clients > 0 ? PIE_ListenServer : PIE_Standalone);
			Settings->SetPlayNumberOfClients(1 + S->Scenario.Clients);
			Settings->SetRunUnderOneProcess(true);
			Params.EditorPlaySettings = Settings;
			GEditor->RequestPlaySession(Params);
			return true;
		});

		// ② 서버 월드 BeginPlay · 클라이언트 접속 대기
		Step([S, &Test]() -> bool
		{
			if (FindServerWorld() && CountReadyClients() >= S->Scenario.Clients)
			{
				return true;
			}
			++S->FramesWaitingPie;
			const bool bDropped = S->FramesWaitingPie > 5 && !GEditor->PlayWorld && !GEditor->IsPlaySessionInProgress();
			// 프레임으로 잰다 — 맵 로드 프레임이 길어 시계로 재면 접속 전에 끝난다
			const bool bGaveUp = S->FramesWaitingPie > 3000;
			if (bDropped || bGaveUp)
			{
				Test.AddError(bDropped ? TEXT("PIE did not start (the play session request was dropped — see LogPlayLevel)")
					: *FString::Printf(TEXT("PIE did not reach %d connected client(s)"), S->Scenario.Clients));
				S->Finish = EFinish::PieNotStarted;
				return true;
			}
			return false;
		});

		// ③ 고정물 · 런타임 스폰
		Step([S, &Test]() -> bool
		{
			if (S->Finish != EFinish::None)
			{
				return true;
			}
			S->Log->bActive = true;
			UWorld* World = FindServerWorld();
			if (!World)
			{
				Test.AddError(TEXT("The server PIE world disappeared before the scenario began"));
				S->Finish = EFinish::WorldLost;
				return true;
			}
			if (S->Prepare)
			{
				S->Prepare(*World);
			}
			if (S->Scenario.SpawnLocation.IsSet())
			{
				FActorSpawnParameters Params;
				Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
				Params.ObjectFlags |= RF_Transient;
				APawn* Pawn = World->SpawnActor<APawn>(S->PawnClass.Get(), FTransform(*S->Scenario.SpawnLocation), Params);
				if (!Pawn)
				{
					Test.AddError(FString::Printf(TEXT("Could not spawn '%s'"), *S->Scenario.PawnClass));
					S->Finish = EFinish::NotFound;
					return true;
				}
				S->Pawn = Pawn;
				S->bSpawned = true;
				const bool bControllerComesLater = !S->Scenario.Actions.IsEmpty() && S->Scenario.Actions[0].Kind == EActionKind::SpawnController;
				if (!Pawn->GetController() && !bControllerComesLater)
				{
					Test.AddError(FString::Printf(TEXT("'%s' has no controller after spawning — its AutoPossessAI must be Spawned or PlacedInWorldOrSpawned and AIControllerClass must be set"), *Pawn->GetClass()->GetName()));
					S->Finish = EFinish::NotFound;
				}
			}
			return true;
		});

		// ④ 관측
		Step([S, &Test]() -> bool
		{
			return S->Finish != EFinish::None || TickObservation(*S, Test);
		});

		// ⑤ 판정 · 관측 기록 · PIE 종료. 관측 전에 끝난 경우는 원인 오류가 이미 있으므로 이벤트 · 기대 오류를 겹쳐 내지 않는다
		Step([S, &Test]() -> bool
		{
			const bool bAborted = S->Finish == EFinish::PieNotStarted || S->Finish == EFinish::WorldLost || S->Finish == EFinish::NotFound || S->Finish == EFinish::NotStarted;
			AnimMcpRuntimeScenario::SetObservation(AnimMcpJson::ToString(BuildObservation(*S, Test, bAborted)));
			if (GEditor->PlayWorld)
			{
				GEditor->RequestEndPlayMap();
			}
			return true;
		});

		// ⑥ PlayWorld 소멸 대기 (RequestEndPlayMap 은 다음 Tick 에 EndPlayMap)
		Step([]() -> bool
		{
			return GEditor->PlayWorld == nullptr;
		});
		return true;
	}
}
