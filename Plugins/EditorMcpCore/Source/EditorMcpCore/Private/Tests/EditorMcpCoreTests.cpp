// 에디터 MCP 코어 시험 (2026-11-14 플러그인 분리) — 애셋 · 에디터 상태를 건드리지 않는다(메모리의 ini · 로컬 디스패처만).
// 실행: run_automation_tests {filter:"EditorMcpCore."}

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/EditorMcpGuard.h"
#include "Core/EditorMcpSettings.h"
#include "Misc/ConfigCacheIni.h"

namespace EditorMcpCoreTests
{
	FAnimMcpHandler Echo(const TCHAR* Value)
	{
		const FString Captured(Value);
		return [Captured](FAnimMcpContext&, FAnimMcpError&) -> TSharedPtr<FJsonObject>
		{
			TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
			Result->SetStringField(TEXT("value"), Captured);
			return Result;
		};
	}

	FString ErrorCode(const FString& Envelope)
	{
		TSharedPtr<FJsonObject> Parsed;
		FString ParseError;
		FString Code;
		const TSharedPtr<FJsonObject>* Error = nullptr;
		if (AnimMcpJson::Parse(Envelope, Parsed, ParseError) && Parsed->TryGetObjectField(TEXT("error"), Error) && Error)
		{
			(*Error)->TryGetStringField(TEXT("code"), Code);
		}
		return Code;
	}
}

// [EditorMcp] 와 옛 [AnimGraphMcp] 를 둘 다 읽는 규칙 — 배열은 합치고(새 섹션 먼저), 값은 새 섹션 우선
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEditorMcpCoreSettingsTest, "EditorMcpCore.Settings", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FEditorMcpCoreSettingsTest::RunTest(const FString& Parameters)
{
	FConfigFile Both;
	Both.CombineFromBuffer(TEXT(
		"[EditorMcp]\n"
		"+StateTreeEditPaths=/Game/New/\n"
		"Port=19000\n"
		"[AnimGraphMcp]\n"
		"+StateTreeEditPaths=/Game/AI/\n"
		"+ProtectedPaths=/Game/Assets/\n"
		"Port=18765\n"
		"MaxThing=7\n"), TEXT("EditorMcpCoreTest_Both"));

	const TArray<FString> EditPaths = EditorMcpSettings::GetArrayFromFile(Both, TEXT("StateTreeEditPaths"));
	TestEqual(TEXT("merged array count"), EditPaths.Num(), 2);
	if (EditPaths.Num() == 2)
	{
		TestEqual(TEXT("new section first"), EditPaths[0], FString(TEXT("/Game/New/")));
		TestEqual(TEXT("legacy section second"), EditPaths[1], FString(TEXT("/Game/AI/")));
	}
	const TArray<FString> Protected = EditorMcpSettings::GetArrayFromFile(Both, TEXT("ProtectedPaths"));
	TestEqual(TEXT("legacy-only array"), Protected.Num(), 1);

	int32 Port = 0;
	TestTrue(TEXT("Port found"), EditorMcpSettings::GetIntFromFile(Both, TEXT("Port"), Port));
	TestEqual(TEXT("new section value wins"), Port, 19000);
	int32 MaxThing = 0;
	TestTrue(TEXT("legacy-only value found"), EditorMcpSettings::GetIntFromFile(Both, TEXT("MaxThing"), MaxThing));
	TestEqual(TEXT("legacy-only value"), MaxThing, 7);
	int32 Missing = 42;
	TestFalse(TEXT("missing key"), EditorMcpSettings::GetIntFromFile(Both, TEXT("NoSuchKey"), Missing));
	TestEqual(TEXT("missing key leaves value"), Missing, 42);

	// 기존 프로젝트 ini 처럼 옛 섹션만 있을 때 — 분리 전과 같은 값
	FConfigFile LegacyOnly;
	LegacyOnly.CombineFromBuffer(TEXT("[AnimGraphMcp]\n+StateTreeEditPaths=/Game/AI/\nPort=18765\n"), TEXT("EditorMcpCoreTest_Legacy"));
	TestEqual(TEXT("legacy-only edit paths"), EditorMcpSettings::GetArrayFromFile(LegacyOnly, TEXT("StateTreeEditPaths")).Num(), 1);
	Port = 0;
	TestTrue(TEXT("legacy Port"), EditorMcpSettings::GetIntFromFile(LegacyOnly, TEXT("Port"), Port) && Port == 18765);

	// 쓰기 허용 경로의 '/' 경계
	const TArray<FString> Prefixes = { EditorMcpGuard::NormalizePrefix(TEXT("/Game/_AutoGen")) };
	TestEqual(TEXT("prefix normalized"), Prefixes[0], FString(TEXT("/Game/_AutoGen/")));
	TestTrue(TEXT("asset under prefix"), EditorMcpGuard::IsUnderAnyPrefix(TEXT("/Game/_AutoGen/R1/WBP_X.WBP_X"), Prefixes));
	TestTrue(TEXT("folder itself"), EditorMcpGuard::IsUnderAnyPrefix(TEXT("/Game/_AutoGen/"), Prefixes));
	TestFalse(TEXT("sibling with same stem"), EditorMcpGuard::IsUnderAnyPrefix(TEXT("/Game/_AutoGenX/WBP_X"), Prefixes));
	TestFalse(TEXT("mount root is not a valid prefix"), EditorMcpGuard::IsValidPrefix(TEXT("/Game/")));
	TestTrue(TEXT("folder below mount root is valid"), EditorMcpGuard::IsValidPrefix(TEXT("/Game/_AutoGen/")));
	return true;
}

// Tool 소유 기능 — 기능 플러그인이 내려갈 때 그 기능의 Tool 만 빠지고, 캐시된 봉투도 남지 않는다
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FEditorMcpCoreDispatcherTest, "EditorMcpCore.Dispatcher", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FEditorMcpCoreDispatcherTest::RunTest(const FString& Parameters)
{
	using namespace EditorMcpCoreTests;

	FAnimMcpDispatcher Dispatcher;
	Dispatcher.BeginFeature(TEXT("FeatureA"));
	Dispatcher.RegisterTool(TEXT("a_one"), TEXT("a1"), Echo(TEXT("a1")));
	Dispatcher.RegisterTool(TEXT("a_two"), TEXT("a2"), Echo(TEXT("a2")));
	Dispatcher.EndFeature();
	Dispatcher.BeginFeature(TEXT("FeatureB"));
	Dispatcher.RegisterTool(TEXT("b_one"), TEXT("b1"), Echo(TEXT("b1")));
	Dispatcher.EndFeature();
	Dispatcher.RegisterTool(TEXT("loose"), TEXT("no feature"), Echo(TEXT("loose")));

	TestEqual(TEXT("owner of a_one"), Dispatcher.GetToolFeature(TEXT("a_one")), FName(TEXT("FeatureA")));
	TestEqual(TEXT("owner of loose"), Dispatcher.GetToolFeature(TEXT("loose")), FName(NAME_None));
	TestEqual(TEXT("FeatureA tools"), Dispatcher.CountFeatureTools(TEXT("FeatureA")), 2);

	int32 Status = 0;
	const FString First = Dispatcher.Dispatch(TEXT("a_one"), TEXT("{\"request_id\":\"same\"}"), Status);
	TestEqual(TEXT("a_one ok"), Status, 200);

	const TArray<FName> Removed = Dispatcher.RemoveFeature(TEXT("FeatureA"));
	TestEqual(TEXT("removed count"), Removed.Num(), 2);
	TestFalse(TEXT("a_one gone"), Dispatcher.HasTool(TEXT("a_one")));
	TestTrue(TEXT("b_one kept"), Dispatcher.HasTool(TEXT("b_one")));
	TestTrue(TEXT("loose kept"), Dispatcher.HasTool(TEXT("loose")));

	// 같은 request_id 재전송 — 캐시가 비워져 이제 TOOL_NOT_FOUND
	const FString Again = Dispatcher.Dispatch(TEXT("a_one"), TEXT("{\"request_id\":\"same\"}"), Status);
	TestEqual(TEXT("removed tool is not replayed from cache"), ErrorCode(Again), FString(AnimMcpErrorCodes::ToolNotFound));
	TestEqual(TEXT("removing an unknown feature is a no-op"), Dispatcher.RemoveFeature(TEXT("NoSuchFeature")).Num(), 0);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
