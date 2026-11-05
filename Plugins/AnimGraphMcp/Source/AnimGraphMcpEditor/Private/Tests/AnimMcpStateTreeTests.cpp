// StateTree 자동화 Phase 1 — 저작 고리 시험 (Docs/StateTree/DevelopmentGuide.md §8).
// 실제 Tool 핸들러를 로컬 디스패처로 부른다. 애셋은 /Game/AI/Test/ 에만 만들고 이름에 시각이 붙어 재실행이 충돌하지 않는다.
// 컴파일 실패를 일부러 일으키므로 로그 오류로는 실패시키지 않는다 — 판정은 명시적 TestXxx 로만 한다.
//
// 실행: run_automation_tests {filter:"AnimGraphMcp.StateTree"}
// 화면 판정(트리 뷰 · 디테일 패널)은 없다 — 사람 눈 확인 항목은 Docs/StateTree/Feasibility.md §7.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpStateTreeAsset.h"
#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Editor/Transactor.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Internationalization/Regex.h"
#include "Misc/DateTime.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "PlayInEditorDataTypes.h"
#include "PropertyBindingPath.h"
#include "ScopedTransaction.h"
#include "StateTree.h"
#include "StateTreeEditingSubsystem.h"
#include "StateTreeEditorData.h"
#include "StateTreeEditorPropertyBindings.h"
#include "StateTreeState.h"
#include "StateTreeViewModel.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Tools/AnimMcpTools.h"
#include "UObject/Package.h"

namespace AnimMcpStateTreeTests
{
	const TCHAR* const Path_Delay = TEXT("/Script/StateTreeModule.StateTreeDelayTask");
	const TCHAR* const Path_MoveTo = TEXT("/Script/GameplayStateTreeModule.StateTreeMoveToTask");
	const TCHAR* const Path_Distance = TEXT("/Script/StateTreeModule.StateTreeCompareDistanceCondition");
	const TCHAR* const Path_Bool = TEXT("/Script/StateTreeModule.StateTreeCompareBoolCondition");
	const TCHAR* const Path_ActorLocation = TEXT("/Script/GameplayStateTreeModule.StateTreeGetActorLocationPropertyFunction");
	const TCHAR* const Path_Evaluator = TEXT("/Script/AnimGraphMcpEditor.AnimMcpTestEvaluator");
	const TCHAR* const Path_ProjectActor = TEXT("/Script/AstralBreak.AstralCombatCharacter");

	/** {Delay} 같은 자리표시자를 타입 경로로 바꾼다 — 시험 배치를 읽기 쉽게 */
	FString Expand(const FString& Text)
	{
		return Text
			.Replace(TEXT("{Delay}"), Path_Delay)
			.Replace(TEXT("{MoveTo}"), Path_MoveTo)
			.Replace(TEXT("{Distance}"), Path_Distance)
			.Replace(TEXT("{Bool}"), Path_Bool)
			.Replace(TEXT("{ActorLocation}"), Path_ActorLocation)
			.Replace(TEXT("{Evaluator}"), Path_Evaluator);
	}

	/** Idle → Chase → Attack. 거리 조건의 필수 입력은 Get Actor Location 으로 묶는다 */
	const TCHAR* const StandardBatch = TEXT(R"JSON([
		{"op":"add_state","ref":"idle","name":"Idle"},
		{"op":"add_state","ref":"chase","name":"Chase"},
		{"op":"add_state","ref":"attack","name":"Attack"},
		{"op":"add_task","ref":"wait","state":"idle","type":"{Delay}","values":{"Duration":1.5}},
		{"op":"add_task","ref":"move","state":"chase","type":"{MoveTo}","values":{"AcceptableRadius":120}},
		{"op":"add_task","ref":"swing","state":"attack","type":"{Delay}"},
		{"op":"add_transition","ref":"to_chase","state":"idle","trigger":"OnStateCompleted","target":"chase"},
		{"op":"add_transition","ref":"to_attack","state":"chase","trigger":"OnTick","target":"attack",
			"conditions":[{"ref":"near","type":"{Distance}","values":{"Distance":200,"Operator":"LessOrEqual"}}]},
		{"op":"add_transition","ref":"to_idle","state":"attack","trigger":"OnStateCompleted","target":"idle"},
		{"op":"bind_property_function","ref":"self","function":"{ActorLocation}","target":{"node":"near","path":"Source"}},
		{"op":"bind_property","source":{"struct":"Actor","path":""},"target":{"node":"self","path":"Input"}}
	])JSON");

	class FTestBase : public FAutomationTestBase
	{
	public:
		FTestBase(const FString& InName, const bool bInComplexTask) : FAutomationTestBase(InName, bInComplexTask) {}
		virtual bool SuppressLogErrors() override { return true; }
		virtual bool SuppressLogWarnings() override { return true; }
	};

	struct FCall
	{
		bool bOk = false;
		FString Code;
		FString Message;
		TSharedPtr<FJsonObject> Result;
		TSharedPtr<FJsonObject> Details;

		FString DetailString(const TCHAR* Field) const
		{
			FString Value;
			if (Details.IsValid())
			{
				Details->TryGetStringField(Field, Value);
			}
			return Value;
		}

		TSharedPtr<FJsonObject> Rollback() const
		{
			const TSharedPtr<FJsonObject>* Field = nullptr;
			return Details.IsValid() && Details->TryGetObjectField(TEXT("rollback"), Field) && Field ? *Field : nullptr;
		}

		FString RollbackMethod() const
		{
			FString Method;
			if (TSharedPtr<FJsonObject> Object = Rollback())
			{
				Object->TryGetStringField(TEXT("method"), Method);
			}
			return Method;
		}

		bool RollbackVerified() const
		{
			bool bVerified = false;
			if (TSharedPtr<FJsonObject> Object = Rollback())
			{
				Object->TryGetBoolField(TEXT("verified"), bVerified);
			}
			return bVerified;
		}

		FString Ref(const TCHAR* Name) const
		{
			FString Value;
			const TSharedPtr<FJsonObject>* Refs = nullptr;
			if (Result.IsValid() && Result->TryGetObjectField(TEXT("refs"), Refs) && Refs)
			{
				(*Refs)->TryGetStringField(Name, Value);
			}
			return Value;
		}
	};

	class FHarness
	{
	public:
		FHarness() { AnimMcpTools::RegisterStateTreeTools(Dispatcher); }

		FCall Call(const TCHAR* Tool, const FString& Body)
		{
			FCall Out;
			int32 Status = 0;
			const FString Text = Dispatcher.Dispatch(Tool, Body, Status);
			TSharedPtr<FJsonObject> Envelope;
			FString ParseError;
			if (!AnimMcpJson::Parse(Text, Envelope, ParseError) || !Envelope.IsValid())
			{
				Out.Code = TEXT("UNPARSED_ENVELOPE");
				return Out;
			}
			Envelope->TryGetBoolField(TEXT("ok"), Out.bOk);
			const TSharedPtr<FJsonObject>* Result = nullptr;
			if (Envelope->TryGetObjectField(TEXT("result"), Result) && Result)
			{
				Out.Result = *Result;
			}
			const TSharedPtr<FJsonObject>* Error = nullptr;
			if (Envelope->TryGetObjectField(TEXT("error"), Error) && Error)
			{
				(*Error)->TryGetStringField(TEXT("code"), Out.Code);
				(*Error)->TryGetStringField(TEXT("message"), Out.Message);
				const TSharedPtr<FJsonObject>* Details = nullptr;
				if ((*Error)->TryGetObjectField(TEXT("details"), Details) && Details)
				{
					Out.Details = *Details;
				}
			}
			return Out;
		}

		FCall Asset(const TCHAR* Tool, const FString& AssetPath, const FString& Extra = FString())
		{
			return Call(Tool, FString::Printf(TEXT("{\"asset_path\":\"%s\"%s}"), *AssetPath, *Extra));
		}

		FCall Apply(const FString& AssetPath, const FString& Operations, const FString& Extra = FString())
		{
			return Asset(TEXT("apply_state_tree_operations"), AssetPath, FString::Printf(TEXT(",\"operations\":%s%s"), *Expand(Operations), *Extra));
		}

		FCall Preview(const FString& AssetPath, const FString& Operations)
		{
			return Asset(TEXT("preview_state_tree_operations"), AssetPath, FString::Printf(TEXT(",\"operations\":%s"), *Expand(Operations)));
		}

		FCall Inspect(const FString& AssetPath) { return Asset(TEXT("inspect_state_tree"), AssetPath); }

		/** 새 트리 — 실패하면 빈 문자열 */
		FString NewTree(const TCHAR* Tag, const FString& Extra = FString())
		{
			static int32 Counter = 0;
			const FString Path = FString::Printf(TEXT("/Game/AI/Test/ST_P1_%s_%s_%d"), Tag, *FDateTime::Now().ToString(TEXT("%H%M%S")), ++Counter);
			return Asset(TEXT("create_state_tree"), Path, Extra).bOk ? Path : FString();
		}

		/** 표준 트리 — 새 트리에 StandardBatch 를 적용 */
		FString NewStandardTree(const TCHAR* Tag, FCall* OutApply = nullptr)
		{
			const FString Path = NewTree(Tag);
			if (Path.IsEmpty())
			{
				return Path;
			}
			FCall Applied = Apply(Path, StandardBatch);
			if (OutApply)
			{
				*OutApply = Applied;
			}
			return Applied.bOk ? Path : FString();
		}

	private:
		FAnimMcpDispatcher Dispatcher;
	};

	UStateTree* FindTree(const FString& AssetPath)
	{
		const FString Name = FPackageName::GetShortName(AssetPath);
		return FindObject<UStateTree>(nullptr, *(AssetPath + TEXT(".") + Name));
	}

	UStateTreeEditorData* FindData(const FString& AssetPath)
	{
		return AnimMcpStateTreeAsset::GetEditorData(FindTree(AssetPath));
	}

	FString FileMd5(const FString& AssetPath)
	{
		return LexToString(FMD5Hash::HashFile(*FPackageName::LongPackageNameToFilename(AssetPath, FPackageName::GetAssetPackageExtension())));
	}

	int32 CountBindings(const FString& AssetPath)
	{
		const UStateTreeEditorData* Data = FindData(AssetPath);
		return Data ? Data->GetPropertyEditorBindings()->GetNumBindings() : INDEX_NONE;
	}

	TSharedPtr<FJsonObject> ChildState(const FCall& Inspected, const TCHAR* Name)
	{
		const TArray<TSharedPtr<FJsonValue>>* Roots = nullptr;
		if (!Inspected.Result.IsValid() || !Inspected.Result->TryGetArrayField(TEXT("states"), Roots) || !Roots || Roots->IsEmpty())
		{
			return nullptr;
		}
		const TArray<TSharedPtr<FJsonValue>>* Children = nullptr;
		if ((*Roots)[0]->AsObject()->TryGetArrayField(TEXT("children"), Children) && Children)
		{
			for (const TSharedPtr<FJsonValue>& Child : *Children)
			{
				FString ChildName;
				if (Child->AsObject()->TryGetStringField(TEXT("name"), ChildName) && ChildName == Name)
				{
					return Child->AsObject();
				}
			}
		}
		return nullptr;
	}

	int32 ArrayLength(const TSharedPtr<FJsonObject>& Object, const TCHAR* Field)
	{
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		return Object.IsValid() && Object->TryGetArrayField(Field, Array) && Array ? Array->Num() : INDEX_NONE;
	}

	/** GUID 를 첫 등장 순서 번호로 바꾼다. 애셋 이름 · 리비전은 뺀다 — 리비전은 GUID 를 포함해 계산된다 */
	FString Normalize(const TSharedPtr<FJsonObject>& Inspected)
	{
		TSharedRef<FJsonObject> Copy = MakeShared<FJsonObject>(*Inspected);
		Copy->RemoveField(TEXT("asset_path"));
		Copy->RemoveField(TEXT("revision"));
		const FString Text = AnimMcpJson::ToString(Copy);

		TMap<FString, FString> Tokens;
		FString Out;
		int32 Cursor = 0;
		FRegexMatcher Matcher(FRegexPattern(TEXT("[0-9A-F]{32}")), Text);
		while (Matcher.FindNext())
		{
			Out += Text.Mid(Cursor, Matcher.GetMatchBeginning() - Cursor);
			const FString Guid = Text.Mid(Matcher.GetMatchBeginning(), Matcher.GetMatchEnding() - Matcher.GetMatchBeginning());
			FString& Token = Tokens.FindOrAdd(Guid);
			if (Token.IsEmpty())
			{
				Token = FString::Printf(TEXT("<guid%d>"), Tokens.Num());
			}
			Out += Token;
			Cursor = Matcher.GetMatchEnding();
		}
		return Out + Text.Mid(Cursor);
	}

	/** ADD_LATENT_AUTOMATION_COMMAND 매크로는 람다 본문의 쉼표에 취약하다 → 직접 큐잉 */
	void Step(TFunction<bool()> Fn)
	{
		FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(MoveTemp(Fn)));
	}
}

using namespace AnimMcpStateTreeTests;

// ─── 1 ─── 빈 트리 생성 · 잘못된 스키마 거부 · 덮어쓰기 거부
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeCreateTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.01_Create", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeCreateTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewTree(TEXT("Create"));
	if (!TestFalse(TEXT("created"), Path.IsEmpty()))
	{
		return false;
	}

	const FCall Inspected = Harness.Inspect(Path);
	TestTrue(TEXT("inspect ok"), Inspected.bOk);
	TestEqual(TEXT("compile_state"), Inspected.Result->GetStringField(TEXT("compile_state")), FString(TEXT("up_to_date")));
	TestFalse(TEXT("saved, not dirty"), Inspected.Result->GetBoolField(TEXT("package_dirty")));
	TestEqual(TEXT("one root"), ArrayLength(Inspected.Result, TEXT("states")), 1);
	TestTrue(TEXT("file on disk"), FPaths::FileExists(FPackageName::LongPackageNameToFilename(Path, FPackageName::GetAssetPackageExtension())));

	const FString Md5 = FileMd5(Path);
	TestEqual(TEXT("overwrite refused"), Harness.Asset(TEXT("create_state_tree"), Path).Code, FString(AnimMcpErrorCodes::AssetExists));
	TestEqual(TEXT("file untouched by refused overwrite"), FileMd5(Path), Md5);

	const FString Fresh = FString::Printf(TEXT("/Game/AI/Test/ST_P1_Refused_%s"), *FGuid::NewGuid().ToString());
	const auto Refused = [&](const TCHAR* Label, const FString& Extra, const TCHAR* Code)
	{
		TestEqual(Label, Harness.Asset(TEXT("create_state_tree"), Fresh, Extra).Code, FString(Code));
		TestNull(*(FString(Label) + TEXT(": no package left")), FindPackage(nullptr, *Fresh));
	};
	Refused(TEXT("missing schema"), TEXT(",\"schema_class\":\"/Script/StateTreeModule.NoSuchSchema\""), AnimMcpErrorCodes::TypeNotFound);
	Refused(TEXT("class that is not a schema"), TEXT(",\"schema_class\":\"/Script/Engine.Actor\""), AnimMcpErrorCodes::TypeNotAllowed);
	Refused(TEXT("abstract schema"), TEXT(",\"schema_class\":\"/Script/StateTreeModule.StateTreeSchema\""), AnimMcpErrorCodes::TypeNotAllowed);
	Refused(TEXT("wrong controller class"), TEXT(",\"schema_properties\":{\"AIControllerClass\":\"/Script/Engine.Actor\"}"), AnimMcpErrorCodes::TypeNotAllowed);
	Refused(TEXT("unknown schema property"), TEXT(",\"schema_properties\":{\"Nope\":\"/Script/Engine.Actor\"}"), AnimMcpErrorCodes::PropertyNotAllowed);
	TestEqual(TEXT("bad name"), Harness.Asset(TEXT("create_state_tree"), TEXT("/Game/AI/Test/Bad Name")).Code, FString(AnimMcpErrorCodes::BadRequest));

	// 프로젝트 클래스 — 컨텍스트와 컴파일 산출물에 들어간다(§2-2)
	const FString WithContext = Harness.NewTree(TEXT("Context"), FString::Printf(TEXT(",\"schema_properties\":{\"ContextActorClass\":\"%s\"}"), Path_ProjectActor));
	if (TestFalse(TEXT("created with context class"), WithContext.IsEmpty()))
	{
		bool bCompiledContext = false;
		for (const FStateTreeExternalDataDesc& Desc : FindTree(WithContext)->GetContextDataDescs())
		{
			bCompiledContext |= Desc.Name == FName(TEXT("Actor")) && GetPathNameSafe(Desc.Struct) == Path_ProjectActor;
		}
		TestTrue(TEXT("project class in compiled context"), bCompiledContext);
	}
	return true;
}

// ─── 2 ─── 부모/자식 상태 · 이름 중복 시 GUID 식별
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeStatesTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.02_States", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeStatesTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewTree(TEXT("States"));
	const FCall Applied = Harness.Apply(Path, TEXT(R"JSON([
		{"op":"add_state","ref":"a","name":"A","selection":"TrySelectChildrenInOrder"},
		{"op":"add_state","ref":"b","name":"B","type":"group"},
		{"op":"add_state","ref":"a_x","parent":"a","name":"Same"},
		{"op":"add_state","ref":"b_x","parent":"b","name":"Same"},
		{"op":"add_task","state":"a_x","type":"{Delay}"},
		{"op":"add_task","state":"b_x","type":"{Delay}"},
		{"op":"set_state_properties","state":"a","properties":{"Weight":2.5,"bEnabled":true,"CustomTickRate":0.25,"TasksCompletion":"All"}}
	])JSON"));
	if (!TestTrue(FString::Printf(TEXT("apply: %s %s"), *Applied.Code, *Applied.Message), Applied.bOk))
	{
		return false;
	}

	const FCall Inspected = Harness.Inspect(Path);
	const TSharedPtr<FJsonObject> A = ChildState(Inspected, TEXT("A"));
	const TSharedPtr<FJsonObject> B = ChildState(Inspected, TEXT("B"));
	if (!TestNotNull(TEXT("A"), A.Get()) || !TestNotNull(TEXT("B"), B.Get()))
	{
		return false;
	}
	TestEqual(TEXT("A has a child"), ArrayLength(A, TEXT("children")), 1);
	TestEqual(TEXT("group type"), B->GetStringField(TEXT("type")), FString(TEXT("Group")));
	TestEqual(TEXT("weight"), A->GetNumberField(TEXT("weight")), 2.5);
	TestEqual(TEXT("tick rate"), A->GetNumberField(TEXT("custom_tick_rate")), 0.25);
	TestEqual(TEXT("completion"), A->GetStringField(TEXT("tasks_completion")), FString(TEXT("All")));

	const FString Revision = Inspected.Result->GetStringField(TEXT("revision"));
	const FCall Ambiguous = Harness.Apply(Path, TEXT(R"JSON([{"op":"add_task","state":"Same","type":"{Delay}"}])JSON"));
	TestEqual(TEXT("duplicate name refused"), Ambiguous.Code, FString(AnimMcpErrorCodes::AmbiguousName));
	TestEqual(TEXT("stage"), Ambiguous.DetailString(TEXT("stage")), FString(TEXT("preflight")));
	TestEqual(TEXT("nothing changed"), Harness.Inspect(Path).Result->GetStringField(TEXT("revision")), Revision);

	// GUID 로는 같은 이름을 구분한다
	const FString ById = FString::Printf(TEXT(R"JSON([{"op":"add_task","state":"%s","type":"{Delay}"}])JSON"), *Applied.Ref(TEXT("b_x")));
	TestTrue(TEXT("GUID identifies the state"), Harness.Apply(Path, ById).bOk);
	const TSharedPtr<FJsonObject> BAfter = ChildState(Harness.Inspect(Path), TEXT("B"));
	TestEqual(TEXT("task went to B's child"), ArrayLength(BAfter->GetArrayField(TEXT("children"))[0]->AsObject(), TEXT("tasks")), 2);

	TestEqual(TEXT("unknown state"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_task","state":"Nope","type":"{Delay}"}])JSON")).Code, FString(AnimMcpErrorCodes::StateNotFound));
	TestEqual(TEXT("linked type refused"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_state","name":"L","type":"linked"}])JSON")).Code, FString(AnimMcpErrorCodes::PropertyNotAllowed));
	TestEqual(TEXT("disallowed state property"), Harness.Apply(Path, TEXT(R"JSON([{"op":"set_state_properties","state":"A","properties":{"Name":"X"}}])JSON")).Code, FString(AnimMcpErrorCodes::PropertyNotAllowed));
	TestEqual(TEXT("duplicate ref"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_state","ref":"r","name":"R1"},{"op":"add_state","ref":"r","name":"R2"}])JSON")).Code, FString(AnimMcpErrorCodes::BadRequest));
	return true;
}

// ─── 3 ─── 네이티브 Task · Enter Condition · Evaluator · Global Task 추가
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeNodesTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.03_Nodes", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeNodesTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewTree(TEXT("Nodes"));
	const FCall Applied = Harness.Apply(Path, TEXT(R"JSON([
		{"op":"add_evaluator","ref":"eval","type":"{Evaluator}","values":{"Scale":2.0}},
		{"op":"add_global_task","ref":"global","type":"{Delay}","values":{"Duration":9.0}},
		{"op":"add_state","ref":"s","name":"S"},
		{"op":"add_task","ref":"task","state":"s","type":"{Delay}","values":{"Duration":3.0}},
		{"op":"add_enter_condition","ref":"cond","state":"s","type":"{Bool}","values":{"bRight":true,"bInvert":true},"operand":"Or","indent":1},
		{"op":"bind_property","source":{"struct":"eval","path":"bOutFlag"},"target":{"node":"cond","path":"bLeft"}}
	])JSON"));
	if (!TestTrue(FString::Printf(TEXT("apply: %s %s"), *Applied.Code, *Applied.Message), Applied.bOk))
	{
		return false;
	}

	const FCall Inspected = Harness.Inspect(Path);
	TestEqual(TEXT("compile_state"), Inspected.Result->GetStringField(TEXT("compile_state")), FString(TEXT("up_to_date")));
	TestEqual(TEXT("evaluators"), ArrayLength(Inspected.Result, TEXT("evaluators")), 1);
	TestEqual(TEXT("global tasks"), ArrayLength(Inspected.Result, TEXT("global_tasks")), 1);
	const TSharedPtr<FJsonObject> State = ChildState(Inspected, TEXT("S"));
	if (!TestNotNull(TEXT("state"), State.Get()))
	{
		return false;
	}
	const TSharedPtr<FJsonObject> Condition = State->GetArrayField(TEXT("enter_conditions"))[0]->AsObject();
	const TSharedPtr<FJsonObject> Values = Condition->GetObjectField(TEXT("values"));
	TestEqual(TEXT("operand"), Condition->GetStringField(TEXT("operand")), FString(TEXT("Or")));
	TestEqual(TEXT("indent"), Condition->GetNumberField(TEXT("indent")), 1.0);
	TestTrue(TEXT("instance value"), Values->GetBoolField(TEXT("bRight")));
	TestTrue(TEXT("node struct value"), Values->GetBoolField(TEXT("bInvert")));
	const TSharedPtr<FJsonObject> Task = State->GetArrayField(TEXT("tasks"))[0]->AsObject();
	TestEqual(TEXT("task value"), Task->GetObjectField(TEXT("values"))->GetNumberField(TEXT("Duration")), 3.0);

	// set_node_values · 잘못된 값
	TestTrue(TEXT("set_node_values"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"set_node_values","node":"%s","values":{"Duration":4.0}}])JSON"), *Applied.Ref(TEXT("task")))).bOk);
	TestEqual(TEXT("value updated"), ChildState(Harness.Inspect(Path), TEXT("S"))->GetArrayField(TEXT("tasks"))[0]->AsObject()->GetObjectField(TEXT("values"))->GetNumberField(TEXT("Duration")), 4.0);

	const FString Task0 = Applied.Ref(TEXT("task"));
	TestEqual(TEXT("unknown property"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"set_node_values","node":"%s","values":{"Nope":1}}])JSON"), *Task0)).Code, FString(AnimMcpErrorCodes::PropertyNotAllowed));
	TestEqual(TEXT("wrong value type"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"set_node_values","node":"%s","values":{"Duration":"x"}}])JSON"), *Task0)).Code, FString(AnimMcpErrorCodes::BadRequest));
	TestEqual(TEXT("output property refused"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"set_node_values","node":"%s","values":{"bOutFlag":true}}])JSON"), *Applied.Ref(TEXT("eval")))).Code, FString(AnimMcpErrorCodes::PropertyNotAllowed));
	TestEqual(TEXT("unknown type"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_task","state":"S","type":"/Script/StateTreeModule.NoSuchTask"}])JSON")).Code, FString(AnimMcpErrorCodes::TypeNotFound));
	TestEqual(TEXT("short type name refused"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_task","state":"S","type":"StateTreeDelayTask"}])JSON")).Code, FString(AnimMcpErrorCodes::TypeNotFound));
	TestEqual(TEXT("condition is not a task"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_task","state":"S","type":"{Bool}"}])JSON")).Code, FString(AnimMcpErrorCodes::TypeNotAllowed));

	// 후보 목록 — 지침서 §4 의 타입 경로가 나온다
	const FCall Types = Harness.Call(TEXT("list_state_tree_node_types"), TEXT("{}"));
	TestTrue(TEXT("list types"), Types.bOk);
	const FString TypesText = AnimMcpJson::ToString(Types.Result.ToSharedRef());
	TestTrue(TEXT("MoveTo listed"), TypesText.Contains(Path_MoveTo));
	TestTrue(TEXT("function listed"), TypesText.Contains(Path_ActorLocation));
	TestFalse(TEXT("hidden test evaluator not listed"), TypesText.Contains(Path_Evaluator));
	return true;
}

// ─── 4 ─── 전환 연결 · 대상 삭제 거부와 cascade
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeTransitionsTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.04_Transitions", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeTransitionsTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	FCall Applied;
	const FString Path = Harness.NewStandardTree(TEXT("Transitions"), &Applied);
	if (!TestFalse(FString::Printf(TEXT("standard tree: %s %s"), *Applied.Code, *Applied.Message), Path.IsEmpty()))
	{
		return false;
	}

	const FCall Inspected = Harness.Inspect(Path);
	TestEqual(TEXT("states under root"), ArrayLength(Inspected.Result->GetArrayField(TEXT("states"))[0]->AsObject(), TEXT("children")), 3);
	const TSharedPtr<FJsonObject> Chase = ChildState(Inspected, TEXT("Chase"));
	const TSharedPtr<FJsonObject> ToAttack = Chase->GetArrayField(TEXT("transitions"))[0]->AsObject();
	TestEqual(TEXT("trigger"), ToAttack->GetStringField(TEXT("trigger")), FString(TEXT("OnTick")));
	TestEqual(TEXT("target"), ToAttack->GetObjectField(TEXT("target"))->GetStringField(TEXT("state_name")), FString(TEXT("Attack")));
	TestEqual(TEXT("condition"), ArrayLength(ToAttack, TEXT("conditions")), 1);

	// 특수 대상 · 우선순위 · 지연 · 이벤트 없는 OnEvent 거부
	TestTrue(TEXT("special target"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_transition","ref":"t","state":"Idle","trigger":"OnStateFailed","target":"failed","priority":"High","delay":0.5}])JSON")).bOk);
	const TSharedPtr<FJsonObject> Special = ChildState(Harness.Inspect(Path), TEXT("Idle"))->GetArrayField(TEXT("transitions")).Last()->AsObject();
	TestEqual(TEXT("failed target"), Special->GetObjectField(TEXT("target"))->GetStringField(TEXT("kind")), FString(TEXT("failed")));
	TestEqual(TEXT("priority"), Special->GetStringField(TEXT("priority")), FString(TEXT("High")));
	TestEqual(TEXT("delay"), Special->GetNumberField(TEXT("delay")), 0.5);
	TestEqual(TEXT("OnEvent needs a tag"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_transition","state":"Idle","trigger":"OnEvent","target":"Chase"}])JSON")).Code, FString(AnimMcpErrorCodes::BadRequest));
	TestEqual(TEXT("unknown trigger"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_transition","state":"Idle","trigger":"OnNope","target":"Chase"}])JSON")).Code, FString(AnimMcpErrorCodes::BadRequest));

	// 전환이 가리키는 상태는 cascade 없이 못 지운다
	const FString Revision = Harness.Inspect(Path).Result->GetStringField(TEXT("revision"));
	const FCall Refused = Harness.Apply(Path, TEXT(R"JSON([{"op":"remove_state","state":"Chase"}])JSON"));
	TestEqual(TEXT("referenced state refused"), Refused.Code, FString(AnimMcpErrorCodes::NodeReferenced));
	TestEqual(TEXT("nothing changed"), Harness.Inspect(Path).Result->GetStringField(TEXT("revision")), Revision);

	// 앞 op 가 지운 것을 뒤 op 가 참조하면 계획이 잡는다
	TestEqual(TEXT("reference to a state removed earlier in the batch"),
		Harness.Apply(Path, TEXT(R"JSON([{"op":"remove_state","state":"Chase","cascade":true},{"op":"add_transition","state":"Idle","trigger":"OnTick","target":"Chase"}])JSON")).Code,
		FString(AnimMcpErrorCodes::StateNotFound));

	TestEqual(TEXT("root refused"), Harness.Apply(Path, TEXT(R"JSON([{"op":"remove_state","state":"Root"}])JSON")).Code, FString(AnimMcpErrorCodes::BadRequest));

	// cascade — 참조 전환과 조건 · 함수 바인딩까지 함께 사라지고 fixups 는 없다
	const FCall Cascaded = Harness.Apply(Path, TEXT(R"JSON([{"op":"remove_state","state":"Chase","cascade":true}])JSON"));
	TestTrue(FString::Printf(TEXT("cascade: %s %s"), *Cascaded.Code, *Cascaded.Message), Cascaded.bOk);
	const FCall After = Harness.Inspect(Path);
	TestNull(TEXT("Chase gone"), ChildState(After, TEXT("Chase")).Get());
	TestEqual(TEXT("bindings gone"), ArrayLength(After.Result, TEXT("bindings")), 0);
	TestEqual(TEXT("compile_state"), After.Result->GetStringField(TEXT("compile_state")), FString(TEXT("up_to_date")));
	const TSharedPtr<FJsonObject> Idle = ChildState(After, TEXT("Idle"));
	TestEqual(TEXT("only the failed transition is left on Idle"), ArrayLength(Idle, TEXT("transitions")), 1);

	// remove_transition · remove_node
	const FString TransitionId = Idle->GetArrayField(TEXT("transitions"))[0]->AsObject()->GetStringField(TEXT("id"));
	TestTrue(TEXT("remove_transition"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"remove_transition","state":"Idle","transition":"%s"}])JSON"), *TransitionId)).bOk);
	TestEqual(TEXT("transition removed"), ArrayLength(ChildState(Harness.Inspect(Path), TEXT("Idle")), TEXT("transitions")), 0);
	const FString TaskId = Idle->GetArrayField(TEXT("tasks"))[0]->AsObject()->GetStringField(TEXT("id"));
	TestTrue(TEXT("remove_node"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"remove_node","node":"%s"}])JSON"), *TaskId)).bOk);
	TestEqual(TEXT("task removed"), ArrayLength(ChildState(Harness.Inspect(Path), TEXT("Idle")), TEXT("tasks")), 0);
	return true;
}

// ─── 5 ─── 바인딩 정상 · 소스 오타 · 타입 불일치 · 범위 밖 소스
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeBindingsTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.05_Bindings", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeBindingsTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewTree(TEXT("Bindings"));
	const FCall Setup = Harness.Apply(Path, TEXT(R"JSON([
		{"op":"add_evaluator","ref":"eval","type":"{Evaluator}"},
		{"op":"add_state","ref":"a","name":"A"},
		{"op":"add_state","ref":"b","name":"B"},
		{"op":"add_task","ref":"delay_a","state":"a","type":"{Delay}"},
		{"op":"add_task","ref":"move_b","state":"b","type":"{MoveTo}"},
		{"op":"add_task","ref":"delay_b","state":"b","type":"{Delay}"}
	])JSON"));
	if (!TestTrue(FString::Printf(TEXT("setup: %s %s"), *Setup.Code, *Setup.Message), Setup.bOk))
	{
		return false;
	}
	const FString Eval = Setup.Ref(TEXT("eval"));
	const FString DelayA = Setup.Ref(TEXT("delay_a"));
	const FString MoveB = Setup.Ref(TEXT("move_b"));
	const FString DelayB = Setup.Ref(TEXT("delay_b"));

	const auto Bind = [](const FString& SourceStruct, const TCHAR* SourcePath, const FString& TargetNode, const TCHAR* TargetPath)
	{
		return FString::Printf(TEXT(R"JSON([{"op":"bind_property","source":{"struct":"%s","path":"%s"},"target":{"node":"%s","path":"%s"}}])JSON"), *SourceStruct, SourcePath, *TargetNode, TargetPath);
	};
	const FString Revision = Harness.Inspect(Path).Result->GetStringField(TEXT("revision"));
	const FString Md5 = FileMd5(Path);
	const auto Refused = [&](const TCHAR* Label, const FString& Operations, const TCHAR* Code)
	{
		const FCall Previewed = Harness.Preview(Path, Operations);
		TestTrue(*(FString(Label) + TEXT(": preview runs")), Previewed.bOk);
		TestFalse(*(FString(Label) + TEXT(": preview invalid")), Previewed.Result->GetBoolField(TEXT("valid")));
		const FCall Applied = Harness.Apply(Path, Operations);
		TestEqual(*(FString(Label) + TEXT(": code")), Applied.Code, FString(Code));
		TestEqual(*(FString(Label) + TEXT(": stage")), Applied.DetailString(TEXT("stage")), FString(TEXT("preflight")));
	};

	Refused(TEXT("source typo"), Bind(Eval, TEXT("OutLocatoin"), MoveB, TEXT("Destination")), AnimMcpErrorCodes::BadSourcePath);
	Refused(TEXT("type mismatch"), Bind(Eval, TEXT("bOutFlag"), MoveB, TEXT("Destination")), AnimMcpErrorCodes::IncompatibleTypes);
	Refused(TEXT("out of scope"), Bind(DelayA, TEXT("Duration"), DelayB, TEXT("Duration")), AnimMcpErrorCodes::BindingOutOfScope);
	Refused(TEXT("unknown source"), Bind(FGuid::NewGuid().ToString(), TEXT("X"), MoveB, TEXT("Destination")), AnimMcpErrorCodes::NodeNotFound);
	TestEqual(TEXT("refused batches changed nothing"), Harness.Inspect(Path).Result->GetStringField(TEXT("revision")), Revision);
	TestEqual(TEXT("disk untouched"), FileMd5(Path), Md5);

	// 정상 — 프로모션 float → double 은 거부하면 안 된다. 같은 상태의 앞선 Task 는 범위 안
	const FCall Normal = Harness.Apply(Path, FString::Printf(TEXT(R"JSON([
		{"op":"bind_property","source":{"struct":"%s","path":"OutLocation"},"target":{"node":"%s","path":"Destination"}},
		{"op":"bind_property","source":{"struct":"%s","path":"AcceptableRadius"},"target":{"node":"%s","path":"Duration"}}
	])JSON"), *Eval, *MoveB, *MoveB, *DelayB));
	TestTrue(FString::Printf(TEXT("normal: %s %s"), *Normal.Code, *Normal.Message), Normal.bOk);
	TestEqual(TEXT("two bindings kept"), CountBindings(Path), 2);

	// 같은 배치의 노드는 범위를 데이터가 생긴 뒤에야 본다 — Preview 는 deferred, Apply 가 잡고 복구한다
	const TCHAR* const SameBatchOutOfScope = TEXT(R"JSON([
		{"op":"add_state","ref":"c","name":"C"},
		{"op":"add_task","ref":"delay_c","state":"c","type":"{Delay}"},
		{"op":"add_state","ref":"d","name":"D"},
		{"op":"add_task","ref":"delay_d","state":"d","type":"{Delay}"},
		{"op":"bind_property","source":{"struct":"delay_c","path":"Duration"},"target":{"node":"delay_d","path":"Duration"}}
	])JSON");
	const FCall Previewed = Harness.Preview(Path, SameBatchOutOfScope);
	TestTrue(TEXT("same batch: preview cannot judge scope"), Previewed.Result->GetBoolField(TEXT("valid")));
	const TSharedPtr<FJsonObject> Last = Previewed.Result->GetArrayField(TEXT("planned")).Last()->AsObject();
	TestEqual(TEXT("same batch: deferred"), ArrayLength(Last, TEXT("deferred")), 1);

	const FString Revision2 = Harness.Inspect(Path).Result->GetStringField(TEXT("revision"));
	const FString Md52 = FileMd5(Path);
	const FCall Rolled = Harness.Apply(Path, SameBatchOutOfScope);
	TestEqual(TEXT("same batch: apply refuses"), Rolled.Code, FString(AnimMcpErrorCodes::BindingOutOfScope));
	TestEqual(TEXT("same batch: stage"), Rolled.DetailString(TEXT("stage")), FString(TEXT("apply")));
	TestEqual(TEXT("same batch: rolled back by undo"), Rolled.RollbackMethod(), FString(TEXT("undo")));
	TestTrue(TEXT("same batch: verified"), Rolled.RollbackVerified());
	TestEqual(TEXT("same batch: revision restored"), Harness.Inspect(Path).Result->GetStringField(TEXT("revision")), Revision2);
	TestEqual(TEXT("same batch: disk untouched"), FileMd5(Path), Md52);
	TestNull(TEXT("same batch: state gone"), ChildState(Harness.Inspect(Path), TEXT("C")).Get());

	// 소스 후보 — GetBindableStructs 결과
	const FCall Sources = Harness.Asset(TEXT("list_state_tree_bindable_sources"), Path, FString::Printf(TEXT(",\"node\":\"%s\""), *DelayB));
	TestTrue(TEXT("list sources"), Sources.bOk);
	const FString SourcesText = AnimMcpJson::ToString(Sources.Result.ToSharedRef());
	TestTrue(TEXT("evaluator in sources"), SourcesText.Contains(Eval));
	TestTrue(TEXT("earlier task in sources"), SourcesText.Contains(MoveB));
	TestFalse(TEXT("sibling state's task not in sources"), SourcesText.Contains(DelayA));
	return true;
}

// ─── 6 ─── 컴파일 실패 시 자동 복구와 메시지 추출
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeCompileFailureTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.06_CompileFailure", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeCompileFailureTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewStandardTree(TEXT("CompileFail"));
	if (!TestFalse(TEXT("standard tree"), Path.IsEmpty()))
	{
		return false;
	}
	const FCall Before = Harness.Inspect(Path);
	const FString Revision = Before.Result->GetStringField(TEXT("revision"));
	const FString Md5 = FileMd5(Path);
	const int32 Queue = GEditor->Trans->GetQueueLength();

	// 필수 Input 미연결 — 컴파일만 잡을 수 있다
	const FCall Failed = Harness.Apply(Path, TEXT(R"JSON([
		{"op":"add_state","ref":"x","name":"Extra"},
		{"op":"add_enter_condition","state":"x","type":"{Distance}"}
	])JSON"));
	TestEqual(TEXT("code"), Failed.Code, FString(AnimMcpErrorCodes::CompileFailed));
	TestEqual(TEXT("stage"), Failed.DetailString(TEXT("stage")), FString(TEXT("compile")));
	if (!TestTrue(TEXT("messages"), ArrayLength(Failed.Details, TEXT("messages")) > 0))
	{
		return false;
	}
	const TSharedPtr<FJsonObject> Message = Failed.Details->GetArrayField(TEXT("messages"))[0]->AsObject();
	TestEqual(TEXT("severity"), Message->GetStringField(TEXT("severity")), FString(TEXT("error")));
	TestTrue(TEXT("engine text"), Message->GetStringField(TEXT("message")).Contains(TEXT("Source")));
	TestTrue(TEXT("state path"), Message->GetStringField(TEXT("state_path")).Contains(TEXT("Extra")));

	TestEqual(TEXT("rolled back by undo"), Failed.RollbackMethod(), FString(TEXT("undo")));
	TestTrue(TEXT("verified"), Failed.RollbackVerified());
	const FCall After = Harness.Inspect(Path);
	TestEqual(TEXT("revision restored"), After.Result->GetStringField(TEXT("revision")), Revision);
	TestEqual(TEXT("compiled again"), After.Result->GetStringField(TEXT("compile_state")), FString(TEXT("up_to_date")));
	TestTrue(TEXT("ready to run"), After.Result->GetBoolField(TEXT("ready_to_run")));
	TestFalse(TEXT("package clean"), After.Result->GetBoolField(TEXT("package_dirty")));
	TestEqual(TEXT("disk untouched"), FileMd5(Path), Md5);
	TestEqual(TEXT("undo queue back"), GEditor->Trans->GetQueueLength(), Queue);
	return true;
}

// ─── 7 ─── 조용한 바인딩 제거의 fixups 감지
// 도구 경로는 사전 검증이 막아 조용한 제거에 닿지 않는다 — 시험은 엔진 API 로 불량 바인딩을 직접 넣어 Compile · Recover 를 돌린다
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeFixupsTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.07_Fixups", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeFixupsTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	FCall Applied;
	const FString Path = Harness.NewStandardTree(TEXT("Fixups"), &Applied);
	if (!TestFalse(TEXT("standard tree"), Path.IsEmpty()))
	{
		return false;
	}
	FGuid Near, Wait;
	FGuid::Parse(Applied.Ref(TEXT("near")), Near);
	FGuid::Parse(Applied.Ref(TEXT("wait")), Wait);
	const FPropertyBindingPath BadSource(Wait, FName(TEXT("NoSuchProperty")));
	const FPropertyBindingPath OptionalTarget(Near, FName(TEXT("Target")));

	// compile_state_tree 가 보고한다
	UStateTree* Tree = FindTree(Path);
	const int32 BindingsBefore = CountBindings(Path);
	AnimMcpStateTreeAsset::GetEditorData(Tree)->AddPropertyBinding(BadSource, OptionalTarget);
	const FCall Compiled = Harness.Asset(TEXT("compile_state_tree"), Path);
	TestTrue(TEXT("compile tool ran"), Compiled.bOk);
	TestTrue(TEXT("compile succeeds anyway"), Compiled.Result->GetBoolField(TEXT("ok")));
	if (TestEqual(TEXT("one fixup"), ArrayLength(Compiled.Result, TEXT("fixups")), 1))
	{
		const TSharedPtr<FJsonObject> Fixup = Compiled.Result->GetArrayField(TEXT("fixups"))[0]->AsObject();
		TestEqual(TEXT("kind"), Fixup->GetStringField(TEXT("kind")), FString(TEXT("binding_removed")));
		TestTrue(TEXT("names the target"), Fixup->GetStringField(TEXT("target")).Contains(TEXT("Target")));
	}
	TestEqual(TEXT("binding really gone"), CountBindings(Path), BindingsBefore);

	// 적용 트랜잭션 안의 불량 바인딩 — 컴파일이 지운 것을 Undo 가 되돌린다(E5e A). Apply 의 fixups 분기와 같은 부품이다
	const AnimMcpStateTreeAsset::FBaseline Baseline = AnimMcpStateTreeAsset::CaptureBaseline(*Tree);
	const int32 Queue = GEditor->Trans->GetQueueLength();
	{
		FScopedTransaction Transaction(FText::FromString(TEXT("07 bad binding")));
		UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(Tree);
		Data->Modify();
		Data->AddPropertyBinding(BadSource, OptionalTarget);
	}
	const AnimMcpStateTreeAsset::FCompileResult Silent = AnimMcpStateTreeAsset::Compile(*Tree);
	TestTrue(TEXT("transaction: compile succeeds"), Silent.bOk);
	TestEqual(TEXT("transaction: fixup"), Silent.Fixups.Num(), 1);
	const AnimMcpStateTreeAsset::FRollback Rollback = AnimMcpStateTreeAsset::Recover(Baseline);
	TestEqual(TEXT("transaction: undo"), Rollback.Method, FString(TEXT("undo")));
	TestTrue(TEXT("transaction: verified"), Rollback.bVerified);
	TestEqual(TEXT("transaction: queue back"), GEditor->Trans->GetQueueLength(), Queue);
	TestFalse(TEXT("transaction: package clean"), Tree->GetPackage()->IsDirty());
	return true;
}

// ─── 8 ─── expected_revision 불일치 · 더티 애셋 · 허용 경로 밖 · 활성 트랜잭션
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeGuardsTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.08_Guards", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeGuardsTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewTree(TEXT("Guards"));
	const TCHAR* const AddState = TEXT(R"JSON([{"op":"add_state","name":"S"}])JSON");

	TestEqual(TEXT("stale revision refused"), Harness.Apply(Path, AddState, TEXT(",\"expected_revision\":\"00000000\"")).Code, FString(AnimMcpErrorCodes::RevisionMismatch));
	const FString Revision = Harness.Inspect(Path).Result->GetStringField(TEXT("revision"));
	TestTrue(TEXT("matching revision accepted"), Harness.Apply(Path, AddState, FString::Printf(TEXT(",\"expected_revision\":\"%s\""), *Revision)).bOk);

	// 저장 안 한 변경 — 수동 편집을 덮지 않는다
	TestTrue(TEXT("apply without save"), Harness.Apply(Path, TEXT(R"JSON([{"op":"add_state","name":"T"}])JSON"), TEXT(",\"save\":false")).bOk);
	TestTrue(TEXT("left dirty"), Harness.Inspect(Path).Result->GetBoolField(TEXT("package_dirty")));
	TestEqual(TEXT("dirty asset refused"), Harness.Apply(Path, AddState).Code, FString(AnimMcpErrorCodes::AssetDirty));
	const FCall Reverted = Harness.Asset(TEXT("revert_state_tree"), Path);
	TestTrue(FString::Printf(TEXT("revert: %s %s"), *Reverted.Code, *Reverted.Message), Reverted.bOk);
	TestTrue(TEXT("revert reports the cost"), Reverted.Result->GetBoolField(TEXT("undo_history_cleared")));
	TestNull(TEXT("unsaved state gone"), ChildState(Harness.Inspect(Path), TEXT("T")).Get());
	TestFalse(TEXT("clean after revert"), Harness.Inspect(Path).Result->GetBoolField(TEXT("package_dirty")));

	// 한 번도 저장 안 한 애셋도 더티다
	const FString Unsaved = Harness.NewTree(TEXT("Unsaved"), TEXT(",\"save\":false"));
	TestEqual(TEXT("never-saved asset refused"), Harness.Apply(Unsaved, AddState).Code, FString(AnimMcpErrorCodes::AssetDirty));
	FAnimMcpError SaveError;
	AnimMcpStateTreeAsset::Save(*FindTree(Unsaved), SaveError);

	// 허용 경로 밖
	const FString Outside = FString::Printf(TEXT("/Game/Temp/ST_P1_%s"), *FGuid::NewGuid().ToString());
	TestEqual(TEXT("create outside refused"), Harness.Asset(TEXT("create_state_tree"), Outside).Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
	TestNull(TEXT("no package outside"), FindPackage(nullptr, *Outside));
	TestEqual(TEXT("apply outside refused"), Harness.Apply(Outside, AddState).Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
	TestEqual(TEXT("compile outside refused"), Harness.Asset(TEXT("compile_state_tree"), Outside).Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
	TestEqual(TEXT("revert outside refused"), Harness.Asset(TEXT("revert_state_tree"), Outside).Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
	TestEqual(TEXT("path escape refused"), Harness.Asset(TEXT("create_state_tree"), TEXT("/Game/AI/../Temp/ST_P1")).Code, FString(AnimMcpErrorCodes::BadRequest));

	// 열린 트랜잭션 — 합쳐지면 Undo 도 재로드도 못 쓴다
	{
		FScopedTransaction Transaction(FText::FromString(TEXT("08 user drag")));
		TestEqual(TEXT("open transaction refused"), Harness.Apply(Path, AddState).Code, FString(AnimMcpErrorCodes::TransactionActive));
		Transaction.Cancel();
	}
	return true;
}

// ─── 8b ─── PIE 중 거부 — 실제 PIE 를 띄운다
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreePieGuardTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.08b_PieRefused", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreePieGuardTest::RunTest(const FString& Parameters)
{
	struct FContext
	{
		FHarness Harness;
		FString Path;
		FString Revision;
		int32 FramesWaiting = 0;
		bool bStarted = false;
	};
	TSharedRef<FContext> Ctx = MakeShared<FContext>();
	Ctx->Path = Ctx->Harness.NewTree(TEXT("Pie"));
	if (!TestFalse(TEXT("tree"), Ctx->Path.IsEmpty()) || !TestNull(TEXT("no PIE running"), GEditor->PlayWorld.Get()))
	{
		return false;
	}
	Ctx->Revision = Ctx->Harness.Inspect(Ctx->Path).Result->GetStringField(TEXT("revision"));

	Step([]() -> bool
	{
		FRequestPlaySessionParams Params;
		GEditor->RequestPlaySession(Params);
		return true;
	});
	Step([this, Ctx]() -> bool
	{
		UWorld* World = GEditor->PlayWorld;
		if (World && World->HasBegunPlay())
		{
			Ctx->bStarted = true;
			return true;
		}
		if (++Ctx->FramesWaiting > 600 && !GEditor->IsPlaySessionInProgress())
		{
			AddError(TEXT("PIE did not start"));
			return true;
		}
		return false;
	});
	Step([this, Ctx]() -> bool
	{
		if (Ctx->bStarted)
		{
			FHarness& Harness = Ctx->Harness;
			const TCHAR* const AddState = TEXT(R"JSON([{"op":"add_state","name":"S"}])JSON");
			TestEqual(TEXT("apply refused during PIE"), Harness.Apply(Ctx->Path, AddState).Code, FString(AnimMcpErrorCodes::PieActive));
			TestEqual(TEXT("compile refused during PIE"), Harness.Asset(TEXT("compile_state_tree"), Ctx->Path).Code, FString(AnimMcpErrorCodes::PieActive));
			TestEqual(TEXT("revert refused during PIE"), Harness.Asset(TEXT("revert_state_tree"), Ctx->Path).Code, FString(AnimMcpErrorCodes::PieActive));
			TestEqual(TEXT("create refused during PIE"), Harness.Asset(TEXT("create_state_tree"), Ctx->Path + TEXT("_B")).Code, FString(AnimMcpErrorCodes::PieActive));
			TestTrue(TEXT("inspect still reads during PIE"), Harness.Inspect(Ctx->Path).bOk);
			TestEqual(TEXT("nothing changed"), Harness.Inspect(Ctx->Path).Result->GetStringField(TEXT("revision")), Ctx->Revision);
		}
		GEditor->RequestEndPlayMap();
		return true;
	});
	Step([]() -> bool { return GEditor->PlayWorld == nullptr; });
	return true;
}

// ─── 9 ─── 저장 → 재로드 왕복, 같은 배치 반복 시 GUID 정규화 후 구조 동일
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeRoundTripTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.09_RoundTrip", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeRoundTripTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString First = Harness.NewStandardTree(TEXT("TripA"));
	const FString Second = Harness.NewStandardTree(TEXT("TripB"));
	if (!TestFalse(TEXT("first tree"), First.IsEmpty()) || !TestFalse(TEXT("second tree"), Second.IsEmpty()))
	{
		return false;
	}

	const FCall BeforeReload = Harness.Inspect(First);
	const FCall Reverted = Harness.Asset(TEXT("revert_state_tree"), First);
	TestTrue(FString::Printf(TEXT("reload: %s %s"), *Reverted.Code, *Reverted.Message), Reverted.bOk);
	const FCall AfterReload = Harness.Inspect(First);
	TestEqual(TEXT("identical after reload, GUIDs included"), AnimMcpJson::ToString(AfterReload.Result.ToSharedRef()), AnimMcpJson::ToString(BeforeReload.Result.ToSharedRef()));
	TestEqual(TEXT("up to date after reload"), AfterReload.Result->GetStringField(TEXT("compile_state")), FString(TEXT("up_to_date")));
	TestEqual(TEXT("bindings survive"), ArrayLength(AfterReload.Result, TEXT("bindings")), 2);

	const FCall Other = Harness.Inspect(Second);
	TestNotEqual(TEXT("GUIDs differ between runs"), Other.Result->GetStringField(TEXT("revision")), AfterReload.Result->GetStringField(TEXT("revision")));
	TestEqual(TEXT("same structure once GUIDs are normalized"), Normalize(Other.Result), Normalize(AfterReload.Result));
	return true;
}

// ─── 10 ─── Node GUID 중복 없음
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeUniqueIdsTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.10_UniqueIds", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeUniqueIdsTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewStandardTree(TEXT("Ids"));
	const UStateTreeEditorData* Data = FindData(Path);
	if (!TestNotNull(TEXT("tree"), Data))
	{
		return false;
	}
	TSet<FGuid> Ids;
	bool bDuplicate = false;
	Data->VisitAllNodes([&Ids, &bDuplicate](const UStateTreeState*, const FStateTreeBindableStructDesc& Desc, const FStateTreeDataView)
	{
		bool bAlready = false;
		Ids.Add(Desc.ID, &bAlready);
		bDuplicate |= bAlready;
		return EStateTreeVisitor::Continue;
	});
	TestFalse(TEXT("no duplicate struct IDs"), bDuplicate);
	TestTrue(TEXT("visited every node"), Ids.Num() >= 8);
	return true;
}

// ─── 11 ─── 실패 복구 2단 — Undo 경로에서 앞선 Undo 기록 유지, 트랜잭션이 버려진 경우 Undo 없이 재로드
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeRecoveryTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.11_Recovery", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeRecoveryTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	FCall TreeApplied, OtherApplied;
	const FString Path = Harness.NewStandardTree(TEXT("Recovery"), &TreeApplied);
	const FString Other = Harness.NewStandardTree(TEXT("RecoveryOther"), &OtherApplied);
	if (!TestFalse(TEXT("tree"), Path.IsEmpty()) || !TestFalse(TEXT("other tree"), Other.IsEmpty()))
	{
		return false;
	}
	FGuid OtherChaseId;
	FGuid::Parse(OtherApplied.Ref(TEXT("chase")), OtherChaseId);

	// A. Undo 경로 — 사용자가 다른 애셋에서 해 둔 편집이 Undo 기록에 남는다
	UStateTree* OtherTree = FindTree(Other);
	const uint32 OtherHash0 = UStateTreeEditingSubsystem::CalculateStateTreeHash(OtherTree);
	{
		FScopedTransaction Transaction(FText::FromString(TEXT("11 user edit")));
		UStateTreeState* Chase = AnimMcpStateTreeAsset::GetEditorData(OtherTree)->GetMutableStateByID(OtherChaseId);
		Chase->Modify();
		Chase->Description = TEXT("user edit");
	}
	const uint32 OtherHash1 = UStateTreeEditingSubsystem::CalculateStateTreeHash(OtherTree);
	const int32 QueueBefore = GEditor->Trans->GetQueueLength();

	const FString Revision = Harness.Inspect(Path).Result->GetStringField(TEXT("revision"));
	const FCall Failed = Harness.Apply(Path, TEXT(R"JSON([{"op":"add_enter_condition","state":"Chase","type":"{Distance}"}])JSON"));
	TestEqual(TEXT("A: compile failure"), Failed.Code, FString(AnimMcpErrorCodes::CompileFailed));
	TestEqual(TEXT("A: undo"), Failed.RollbackMethod(), FString(TEXT("undo")));
	TestTrue(TEXT("A: verified"), Failed.RollbackVerified());
	bool bCleared = true;
	Failed.Rollback()->TryGetBoolField(TEXT("undo_history_cleared"), bCleared);
	TestFalse(TEXT("A: history kept"), bCleared);
	TestEqual(TEXT("A: revision"), Harness.Inspect(Path).Result->GetStringField(TEXT("revision")), Revision);
	TestEqual(TEXT("A: queue unchanged"), GEditor->Trans->GetQueueLength(), QueueBefore);
	TestEqual(TEXT("A: user's asset untouched"), UStateTreeEditingSubsystem::CalculateStateTreeHash(OtherTree), OtherHash1);

	const FString UndoTitle = GEditor->Trans->GetUndoContext(false).Title.ToString();
	TestEqual(TEXT("A: user's edit is on top"), UndoTitle, FString(TEXT("11 user edit")));
	TestTrue(TEXT("A: user's undo still works"), GEditor->UndoTransaction());
	TestEqual(TEXT("A: user's edit undone"), UStateTreeEditingSubsystem::CalculateStateTreeHash(OtherTree), OtherHash0);
	GEditor->RedoTransaction();

	// B. 버려진 트랜잭션 — Modify 누락. 큐가 늘지 않았으니 Undo 하면 사용자 작업이 되돌아간다(E5e). 재로드로 가야 한다
	UStateTree* Tree = FindTree(Path);
	FGuid ChaseId;
	FGuid::Parse(TreeApplied.Ref(TEXT("chase")), ChaseId);
	const AnimMcpStateTreeAsset::FBaseline Baseline = AnimMcpStateTreeAsset::CaptureBaseline(*Tree);
	const int32 QueueB = GEditor->Trans->GetQueueLength();
	{
		FScopedTransaction Transaction(FText::FromString(TEXT("11 missing modify")));
		UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(Tree);
		Data->Modify();
		Data->GetMutableStateByID(ChaseId)->Description = TEXT("changed without Modify");
	}
	TestEqual(TEXT("B: engine dropped the transaction"), GEditor->Trans->GetQueueLength(), QueueB);
	TestEqual(TEXT("B: user's edit still on top"), GEditor->Trans->GetUndoContext(false).Title.ToString(), FString(TEXT("11 user edit")));

	const AnimMcpStateTreeAsset::FRollback Reload = AnimMcpStateTreeAsset::Recover(Baseline);
	TestEqual(TEXT("B: reload"), Reload.Method, FString(TEXT("reload")));
	TestTrue(TEXT("B: verified"), Reload.bVerified);
	TestTrue(TEXT("B: reports the cleared history"), Reload.bUndoHistoryCleared);
	TestEqual(TEXT("B: user's edit was not undone"), UStateTreeEditingSubsystem::CalculateStateTreeHash(FindTree(Other)), OtherHash1);
	TestTrue(TEXT("B: ready"), FindTree(Path)->IsReadyToRun());

	// 사용자 편집을 저장해 패키지를 깨끗하게 남긴다
	FAnimMcpError SaveError;
	AnimMcpStateTreeAsset::Save(*FindTree(Other), SaveError);

	// C. 실제 변경이 없으면 아무것도 하지 않는다 — 컴파일 실패 상태로 저장된 애셋에 같은 값을 다시 넣어 실패시킨다
	const FString Broken = Harness.NewTree(TEXT("Broken"));
	const FCall Stored = Harness.Apply(Broken, TEXT(R"JSON([
		{"op":"add_state","ref":"s","name":"S"},
		{"op":"add_task","ref":"t","state":"s","type":"{Delay}","values":{"Duration":1.0}},
		{"op":"add_enter_condition","state":"s","type":"{Distance}"}
	])JSON"), TEXT(",\"compile\":false"));
	TestTrue(TEXT("C: stored without compiling"), Stored.bOk);
	TestFalse(TEXT("C: manual compile fails"), Harness.Asset(TEXT("compile_state_tree"), Broken).Result->GetBoolField(TEXT("ok")));
	const FString BrokenRevision = Harness.Inspect(Broken).Result->GetStringField(TEXT("revision"));
	const int32 QueueC = GEditor->Trans->GetQueueLength();
	const FCall NoChange = Harness.Apply(Broken, FString::Printf(TEXT(R"JSON([{"op":"set_node_values","node":"%s","values":{"Duration":1.0}}])JSON"), *Stored.Ref(TEXT("t"))));
	TestEqual(TEXT("C: compile fails"), NoChange.Code, FString(AnimMcpErrorCodes::CompileFailed));
	TestEqual(TEXT("C: nothing to roll back"), NoChange.RollbackMethod(), FString(TEXT("none")));
	TestTrue(TEXT("C: verified"), NoChange.RollbackVerified());
	TestEqual(TEXT("C: queue unchanged"), GEditor->Trans->GetQueueLength(), QueueC);
	const FCall BrokenAfter = Harness.Inspect(Broken);
	TestEqual(TEXT("C: revision"), BrokenAfter.Result->GetStringField(TEXT("revision")), BrokenRevision);
	TestFalse(TEXT("C: not left dirty"), BrokenAfter.Result->GetBoolField(TEXT("package_dirty")));

	// D. 상태 객체 삭제 · FInstancedStruct 안의 함수 노드 추가/제거가 섞인 배치도 Undo 한 번으로 돌아온다
	FCall MixedApplied;
	const FString Mixed = Harness.NewStandardTree(TEXT("Mixed"), &MixedApplied);
	if (!TestFalse(TEXT("D: tree"), Mixed.IsEmpty()))
	{
		return false;
	}
	const FString Near = MixedApplied.Ref(TEXT("near"));
	const FString MixedBefore = AnimMcpJson::ToString(Harness.Inspect(Mixed).Result.ToSharedRef());
	const FString MixedMd5 = FileMd5(Mixed);
	const FCall MixedFailed = Harness.Apply(Mixed, FString::Printf(TEXT(R"JSON([
		{"op":"bind_property_function","ref":"f","function":"{ActorLocation}","target":{"node":"%s","path":"Target"}},
		{"op":"bind_property","source":{"struct":"Actor","path":""},"target":{"node":"f","path":"Input"}},
		{"op":"unbind_property","target":{"node":"%s","path":"Source"}},
		{"op":"remove_state","state":"Attack","cascade":true},
		{"op":"add_enter_condition","state":"Idle","type":"{Distance}"}
	])JSON"), *Near, *Near));
	TestEqual(TEXT("D: compile failure"), MixedFailed.Code, FString(AnimMcpErrorCodes::CompileFailed));
	TestEqual(TEXT("D: undo"), MixedFailed.RollbackMethod(), FString(TEXT("undo")));
	TestTrue(TEXT("D: verified"), MixedFailed.RollbackVerified());
	TestEqual(TEXT("D: identical to before, GUIDs included"), AnimMcpJson::ToString(Harness.Inspect(Mixed).Result.ToSharedRef()), MixedBefore);
	TestEqual(TEXT("D: disk untouched"), FileMd5(Mixed), MixedMd5);
	return true;
}

// ─── 12 ─── 컨텍스트 소스 오타 · 대상 오타도 사전 검증이 잡는다
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreePreflightTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.12_Preflight", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreePreflightTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	FCall Applied;
	const FString Path = Harness.NewStandardTree(TEXT("Preflight"), &Applied);
	if (!TestFalse(TEXT("standard tree"), Path.IsEmpty()))
	{
		return false;
	}
	const FString Near = Applied.Ref(TEXT("near"));
	const FString Move = Applied.Ref(TEXT("move"));
	const int32 Bindings = CountBindings(Path);

	const auto Bind = [](const TCHAR* Struct, const TCHAR* SourcePath, const FString& Node, const TCHAR* TargetPath)
	{
		return FString::Printf(TEXT(R"JSON([{"op":"bind_property","source":{"struct":"%s","path":"%s"},"target":{"node":"%s","path":"%s"}}])JSON"), Struct, SourcePath, *Node, TargetPath);
	};
	TestEqual(TEXT("context source typo"), Harness.Apply(Path, Bind(TEXT("Actor"), TEXT("NoSuchProperty"), Near, TEXT("Target"))).Code, FString(AnimMcpErrorCodes::BadSourcePath));
	TestEqual(TEXT("target typo"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"bind_property","source":{"struct":"%s","path":"Destination"},"target":{"node":"%s","path":"Tagret"}}])JSON"), *Move, *Near)).Code, FString(AnimMcpErrorCodes::BadTargetPath));
	TestEqual(TEXT("empty target path"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"bind_property","source":{"struct":"%s","path":"Destination"},"target":{"node":"%s","path":""}}])JSON"), *Move, *Near)).Code, FString(AnimMcpErrorCodes::BadTargetPath));
	TestEqual(TEXT("context target refused"), Harness.Apply(Path, Bind(TEXT("AIController"), TEXT(""), Move, TEXT("AIController"))).Code, FString(AnimMcpErrorCodes::BadTargetPath));

	// 같은 배치의 노드에도 경로 · 타입은 데이터 없이 잡힌다
	const FCall PlannedTypo = Harness.Preview(Path, TEXT(R"JSON([
		{"op":"add_state","ref":"n","name":"New"},
		{"op":"add_task","ref":"m","state":"n","type":"{MoveTo}"},
		{"op":"add_task","ref":"d","state":"n","type":"{Delay}"},
		{"op":"bind_property","source":{"struct":"m","path":"AcceptableRadiusTypo"},"target":{"node":"d","path":"Duration"}},
		{"op":"add_task","state":"n","type":"{Delay}"}
	])JSON"));
	TestFalse(TEXT("planned node typo: invalid"), PlannedTypo.Result->GetBoolField(TEXT("valid")));
	const TArray<TSharedPtr<FJsonValue>>& Planned = PlannedTypo.Result->GetArrayField(TEXT("planned"));
	TestEqual(TEXT("planned node typo: code"), Planned[3]->AsObject()->GetObjectField(TEXT("error"))->GetStringField(TEXT("code")), FString(AnimMcpErrorCodes::BadSourcePath));
	TestTrue(TEXT("later ops skipped"), Planned[4]->AsObject()->GetBoolField(TEXT("skipped")));
	TestEqual(TEXT("planned target typo"), Harness.Apply(Path, TEXT(R"JSON([
		{"op":"add_state","ref":"n","name":"New"},
		{"op":"add_task","ref":"d","state":"n","type":"{Delay}"},
		{"op":"bind_property","source":{"struct":"Actor","path":""},"target":{"node":"d","path":"Durationn"}}
	])JSON")).Code, FString(AnimMcpErrorCodes::BadTargetPath));

	TestEqual(TEXT("no binding added or lost"), CountBindings(Path), Bindings);
	TestNull(TEXT("no state added"), ChildState(Harness.Inspect(Path), TEXT("New")).Get());
	return true;
}

// ─── 13 ─── 메뉴에 없는 프로퍼티는 NOT_BINDABLE 로 거부 (§10 D-6)
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeNotBindableTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.13_NotBindable", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeNotBindableTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	const FString Path = Harness.NewTree(TEXT("NotBindable"), FString::Printf(TEXT(",\"schema_properties\":{\"ContextActorClass\":\"%s\"}"), Path_ProjectActor));
	if (!TestFalse(TEXT("tree with project context"), Path.IsEmpty()))
	{
		return false;
	}
	const FCall Added = Harness.Apply(Path, TEXT(R"JSON([
		{"op":"add_evaluator","ref":"eval","type":"{Evaluator}"},
		{"op":"add_state","ref":"s","name":"S"},
		{"op":"add_task","ref":"move","state":"s","type":"{MoveTo}"},
		{"op":"add_enter_condition","ref":"cond","state":"s","type":"{Bool}"},
		{"op":"bind_property","source":{"struct":"eval","path":"bOutFlag"},"target":{"node":"cond","path":"bLeft"}}
	])JSON"));
	if (!TestTrue(FString::Printf(TEXT("setup: %s %s"), *Added.Code, *Added.Message), Added.bOk))
	{
		return false;
	}
	const FString Cond = Added.Ref(TEXT("cond"));
	const FString Move = Added.Ref(TEXT("move"));
	const auto Bind = [](const TCHAR* SourcePath, const FString& Node, const TCHAR* TargetPath)
	{
		return FString::Printf(TEXT(R"JSON([{"op":"bind_property","source":{"struct":"Actor","path":"%s"},"target":{"node":"%s","path":"%s"}}])JSON"), SourcePath, *Node, TargetPath);
	};

	// protected EditAnywhere — 컴파일은 되지만 메뉴에 없다(Phase 0 E2). 메뉴 판정이 타입보다 먼저다
	const FCall Protected = Harness.Apply(Path, Bind(TEXT("bTelegraphAttackEnabled"), Cond, TEXT("bLeft")));
	TestEqual(TEXT("protected project property"), Protected.Code, FString(AnimMcpErrorCodes::NotBindable));
	TestEqual(TEXT("path through a non-menu segment"), Harness.Apply(Path, Bind(TEXT("RootComponent.RelativeLocation"), Move, TEXT("Destination"))).Code, FString(AnimMcpErrorCodes::NotBindable));

	// 소스 목록도 같은 규칙 — 숨긴 프로퍼티를 세기만 한다
	const FCall Sources = Harness.Asset(TEXT("list_state_tree_bindable_sources"), Path, FString::Printf(TEXT(",\"node\":\"%s\""), *Move));
	TestTrue(TEXT("list sources"), Sources.bOk);
	bool bFoundActor = false;
	for (const TSharedPtr<FJsonValue>& Value : Sources.Result->GetArrayField(TEXT("sources")))
	{
		const TSharedPtr<FJsonObject> Source = Value->AsObject();
		if (Source->GetStringField(TEXT("name")) == TEXT("Actor"))
		{
			bFoundActor = true;
			TestTrue(TEXT("menu-hidden properties are counted"), Source->GetNumberField(TEXT("hidden_properties")) > 0);
			TestFalse(TEXT("menu-hidden property not listed"), AnimMcpJson::ToString(Source.ToSharedRef()).Contains(TEXT("bTelegraphAttackEnabled")));
		}
	}
	TestTrue(TEXT("actor context listed"), bFoundActor);
	return true;
}

// ─── 14 ─── bind_property_function (§10 D-5)
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeFunctionTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.14_PropertyFunction", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeFunctionTest::RunTest(const FString& Parameters)
{
	FHarness Harness;
	FCall Applied;
	const FString Path = Harness.NewStandardTree(TEXT("Function"), &Applied);
	if (!TestFalse(FString::Printf(TEXT("standard tree: %s %s"), *Applied.Code, *Applied.Message), Path.IsEmpty()))
	{
		return false;
	}
	const FString Near = Applied.Ref(TEXT("near"));
	TestFalse(TEXT("ref resolved to the engine's GUID"), Applied.Ref(TEXT("self")).IsEmpty());

	// 재로드 왕복 — 필수 Input 을 함수가 채운 채 컴파일된다
	const FCall Inspected = Harness.Inspect(Path);
	TestEqual(TEXT("compiled"), Inspected.Result->GetStringField(TEXT("compile_state")), FString(TEXT("up_to_date")));
	TestEqual(TEXT("function plus input binding"), ArrayLength(Inspected.Result, TEXT("bindings")), 2);
	TestTrue(TEXT("reload"), Harness.Asset(TEXT("revert_state_tree"), Path).bOk);
	const FCall Reloaded = Harness.Inspect(Path);
	TestEqual(TEXT("survives reload"), ArrayLength(Reloaded.Result, TEXT("bindings")), 2);
	TestEqual(TEXT("same revision"), Reloaded.Result->GetStringField(TEXT("revision")), Inspected.Result->GetStringField(TEXT("revision")));
	TestTrue(TEXT("function is reported"), AnimMcpJson::ToString(Reloaded.Result.ToSharedRef()).Contains(Path_ActorLocation));

	const auto Function = [&Near](const TCHAR* Type, const TCHAR* Output, const TCHAR* TargetPath)
	{
		return FString::Printf(TEXT(R"JSON([{"op":"bind_property_function","function":"%s"%s,"target":{"node":"%s","path":"%s"}}])JSON"), Type, Output, *Near, TargetPath);
	};
	TestEqual(TEXT("unknown function"), Harness.Apply(Path, Function(TEXT("/Script/GameplayStateTreeModule.NoSuchFunction"), TEXT(""), TEXT("Target"))).Code, FString(AnimMcpErrorCodes::TypeNotFound));
	TestEqual(TEXT("not a function"), Harness.Apply(Path, Function(Path_Delay, TEXT(""), TEXT("Target"))).Code, FString(AnimMcpErrorCodes::TypeNotAllowed));
	TestEqual(TEXT("output typo"), Harness.Apply(Path, Function(Path_ActorLocation, TEXT(",\"output\":\"Outptu\""), TEXT("Target"))).Code, FString(AnimMcpErrorCodes::BadSourcePath));
	TestEqual(TEXT("input is not an output"), Harness.Apply(Path, Function(Path_ActorLocation, TEXT(",\"output\":\"Input\""), TEXT("Target"))).Code, FString(AnimMcpErrorCodes::BadSourcePath));
	TestEqual(TEXT("type mismatch"), Harness.Apply(Path, Function(Path_ActorLocation, TEXT(""), TEXT("Distance"))).Code, FString(AnimMcpErrorCodes::IncompatibleTypes));
	TestEqual(TEXT("target typo"), Harness.Apply(Path, Function(Path_ActorLocation, TEXT(""), TEXT("Tagret"))).Code, FString(AnimMcpErrorCodes::BadTargetPath));

	// unbind 는 함수 입력까지 지운다 — 남으면 컴파일이 조용히 지워 fixups 가 된다
	const FCall Second = Harness.Apply(Path, FString::Printf(TEXT(R"JSON([
		{"op":"bind_property_function","ref":"other","function":"{ActorLocation}","target":{"node":"%s","path":"Target"}},
		{"op":"bind_property","source":{"struct":"Actor","path":""},"target":{"node":"other","path":"Input"}}
	])JSON"), *Near));
	TestTrue(FString::Printf(TEXT("second function: %s %s"), *Second.Code, *Second.Message), Second.bOk);
	TestEqual(TEXT("four bindings"), CountBindings(Path), 4);
	const FCall Unbound = Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"unbind_property","target":{"node":"%s","path":"Target"}}])JSON"), *Near));
	TestTrue(FString::Printf(TEXT("unbind: %s %s"), *Unbound.Code, *Unbound.Message), Unbound.bOk);
	TestEqual(TEXT("function chain gone"), CountBindings(Path), 2);
	TestEqual(TEXT("unbinding nothing refused"), Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"unbind_property","target":{"node":"%s","path":"Target"}}])JSON"), *Near)).Code, FString(AnimMcpErrorCodes::BadTargetPath));

	// 다시 묶으면 대체된다 — 일반 바인딩이 함수 바인딩을 덮어도 입력이 남지 않는다
	const FCall Rebound = Harness.Apply(Path, FString::Printf(TEXT(R"JSON([{"op":"bind_property","source":{"struct":"%s","path":"Destination"},"target":{"node":"%s","path":"Source"}}])JSON"), *Applied.Ref(TEXT("move")), *Near));
	TestTrue(FString::Printf(TEXT("rebind: %s %s"), *Rebound.Code, *Rebound.Message), Rebound.bOk);
	TestEqual(TEXT("function replaced"), CountBindings(Path), 1);
	return true;
}

// ─── 15 ─── 열린 편집기 — 적용 알림 · Undo 복구 · revert 의 재오픈 (§2-9). 뷰모델과 편집기 수만 본다 — 화면은 사람 확인 몫(Feasibility §7)
IMPLEMENT_CUSTOM_SIMPLE_AUTOMATION_TEST(FAnimMcpStateTreeOpenEditorTest, AnimMcpStateTreeTests::FTestBase, "AnimGraphMcp.StateTree.15_OpenEditor", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAnimMcpStateTreeOpenEditorTest::RunTest(const FString& Parameters)
{
	struct FContext
	{
		FHarness Harness;
		FString Path;
		double WaitUntil = 0.0;
		int32 AssetChanged = 0;
	};
	TSharedRef<FContext> Ctx = MakeShared<FContext>();
	Ctx->Path = Ctx->Harness.NewStandardTree(TEXT("OpenEditor"));
	if (!TestFalse(TEXT("standard tree"), Ctx->Path.IsEmpty()))
	{
		return false;
	}
	TestTrue(TEXT("editor opened"), GEditor->GetEditorSubsystem<UAssetEditorSubsystem>()->OpenEditorForAsset(FindTree(Ctx->Path)));
	Ctx->WaitUntil = FPlatformTime::Seconds() + 3.0;

	Step([this, Ctx]() -> bool
	{
		if (FPlatformTime::Seconds() < Ctx->WaitUntil)
		{
			return false;
		}
		FHarness& Harness = Ctx->Harness;
		UAssetEditorSubsystem* AssetEditors = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
		UStateTreeEditingSubsystem* Subsystem = GEditor->GetEditorSubsystem<UStateTreeEditingSubsystem>();
		UStateTree* Tree = FindTree(Ctx->Path);
		TSharedPtr<FStateTreeViewModel> ViewModel = Subsystem->FindViewModel(Tree);
		if (!TestTrue(TEXT("view model while the editor is open"), ViewModel.IsValid()))
		{
			return true;
		}
		const int32 Editors = AssetEditors->FindEditorsForAsset(Tree).Num();
		TWeakPtr<FContext> WeakCtx = Ctx;
		const FDelegateHandle Handle = ViewModel->GetOnAssetChanged().AddLambda([WeakCtx]()
		{
			if (TSharedPtr<FContext> Pinned = WeakCtx.Pin())
			{
				++Pinned->AssetChanged;
			}
		});

		// 성공한 적용 — 열린 편집기에 알린다
		const FCall Applied = Harness.Apply(Ctx->Path, TEXT(R"JSON([{"op":"add_state","name":"AddedWhileOpen"}])JSON"));
		TestTrue(FString::Printf(TEXT("apply: %s %s"), *Applied.Code, *Applied.Message), Applied.bOk);
		TestTrue(TEXT("view notified"), Ctx->AssetChanged > 0);
		TestEqual(TEXT("same view model after apply"), Subsystem->FindViewModel(Tree), ViewModel);

		// 실패한 적용 — Undo 복구는 편집기를 건드리지 않는다
		const FCall Failed = Harness.Apply(Ctx->Path, TEXT(R"JSON([{"op":"add_enter_condition","state":"AddedWhileOpen","type":"{Distance}"}])JSON"));
		TestEqual(TEXT("compile failure"), Failed.Code, FString(AnimMcpErrorCodes::CompileFailed));
		TestEqual(TEXT("undo"), Failed.RollbackMethod(), FString(TEXT("undo")));
		TestTrue(TEXT("verified"), Failed.RollbackVerified());
		TestEqual(TEXT("editor stays open"), AssetEditors->FindEditorsForAsset(Tree).Num(), Editors);
		TestEqual(TEXT("same view model after undo"), Subsystem->FindViewModel(Tree), ViewModel);

		ViewModel->GetOnAssetChanged().Remove(Handle);
		ViewModel.Reset();

		// revert — 편집기가 닫혔다 열린다. 옛 Tree 포인터는 여기서 무효다
		Tree = nullptr;
		const FCall Reverted = Harness.Asset(TEXT("revert_state_tree"), Ctx->Path);
		TestTrue(FString::Printf(TEXT("revert: %s %s"), *Reverted.Code, *Reverted.Message), Reverted.bOk);
		TestTrue(TEXT("revert reports the reopened editor"), Reverted.bOk && Reverted.Result->GetBoolField(TEXT("editor_reopened")));
		TestTrue(TEXT("revert reports the cleared history"), Reverted.bOk && Reverted.Result->GetBoolField(TEXT("undo_history_cleared")));
		Ctx->WaitUntil = FPlatformTime::Seconds() + 3.0;
		return true;
	});

	Step([this, Ctx]() -> bool
	{
		if (FPlatformTime::Seconds() < Ctx->WaitUntil)
		{
			return false;
		}
		UAssetEditorSubsystem* AssetEditors = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
		UStateTree* Tree = FindTree(Ctx->Path);
		if (TestNotNull(TEXT("tree after reload"), Tree))
		{
			TestEqual(TEXT("editor reopened on the reloaded asset"), AssetEditors->FindEditorsForAsset(Tree).Num(), 1);
			TestTrue(TEXT("view model for the reloaded asset"), GEditor->GetEditorSubsystem<UStateTreeEditingSubsystem>()->FindViewModel(Tree).IsValid());
			TestFalse(TEXT("package clean"), Tree->GetPackage()->IsDirty());
			AssetEditors->CloseAllEditorsForAsset(Tree);
		}
		return true;
	});
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
