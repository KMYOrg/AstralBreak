// AI 애니 생성 Phase 1 — 공통 가드(Core/AnimMcpGeneration) 단위 테스트. 경로 허용 목록의 '/' 경계, 임포트 원본 검사,
// 전역 더티 집합 비교가 허용 목록 밖 패키지를 실제로 잡는지(UNEXPECTED_DIRTY)를 메모리 안 임시 패키지로 확인한다 — 디스크에는 쓰지 않는다.
// run_automation_tests {filter:"AnimGraphMcp.Generation"} 로 돈다. 기대값은 프로젝트 ini 의 첫 GenerationOutputPaths · ImportSourceRoots 기준.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetProtection.h"
#include "Core/AnimMcpGeneration.h"
#include "Core/AnimMcpPromote.h"
#include "Curves/CurveFloat.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"
#include "Tools/AnimMcpTools.h"
#include "UObject/Package.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpGenerationGuardTest, "AnimGraphMcp.Generation.Guard", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpGenerationGuardTest::RunTest(const FString& Parameters)
{
	const AnimMcpGeneration::FSettings& Settings = AnimMcpGeneration::GetSettings();
	TestEqual(TEXT("NormalizeFolderPath strips trailing '/'"), AnimMcpGeneration::NormalizeFolderPath(TEXT("/Game/A/B/")), FString(TEXT("/Game/A/B")));

	if (Settings.OutputPaths.Num() == 0)
	{
		AddWarning(TEXT("No [AnimGraphMcp] GenerationOutputPaths configured — path and dirty-guard checks skipped"));
		return true;
	}

	// ---- 출력 경로: 접두 폴더 자체 · 하위 애셋 허용, 이름이 이어진 형제 폴더("…/TestX") · 밖 경로 거부 ----
	const FString Prefix = Settings.OutputPaths[0];                // "/Game/Animation/Test/"
	const FString PrefixFolder = Prefix.LeftChop(1);                // "/Game/Animation/Test"
	TestTrue(TEXT("prefix folder itself is allowed"), AnimMcpGeneration::IsOutputPathAllowed(PrefixFolder));
	TestTrue(TEXT("asset below prefix is allowed"), AnimMcpGeneration::IsOutputPathAllowed(Prefix + TEXT("Sub/AS_X.AS_X")));
	TestFalse(TEXT("sibling folder sharing the name prefix is refused"), AnimMcpGeneration::IsOutputPathAllowed(PrefixFolder + TEXT("_AnimMcpSibling/AS_X")));
	{
		FAnimMcpError Error;
		TestFalse(TEXT("mount root refused"), AnimMcpGeneration::EnsureOutputPathAllowed(TEXT("/Game/AS_X"), TEXT("path"), Error));
		TestEqual(TEXT("mount root -> OUTPUT_PATH_NOT_ALLOWED"), Error.Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
		Error = FAnimMcpError();
		TestFalse(TEXT("invalid path refused"), AnimMcpGeneration::EnsureOutputPathAllowed(TEXT("Game//bad path"), TEXT("path"), Error));
		TestEqual(TEXT("invalid path -> BAD_REQUEST"), Error.Code, FString(AnimMcpErrorCodes::BadRequest));
	}

	// ---- 임포트 원본: 상대 경로 · 루트 밖(.. 탈출) · 없는 파일 ----
	{
		FString Absolute;
		FAnimMcpError Error;
		TestFalse(TEXT("relative import path refused"), AnimMcpGeneration::ResolveImportSource(TEXT("Saved/x.fbx"), Absolute, Error));
		TestEqual(TEXT("relative -> BAD_REQUEST"), Error.Code, FString(AnimMcpErrorCodes::BadRequest));
		if (Settings.ImportSourceRoots.Num() > 0)
		{
			const FString Root = Settings.ImportSourceRoots[0];
			Error = FAnimMcpError();
			TestFalse(TEXT("'..' escape refused"), AnimMcpGeneration::ResolveImportSource(Root + TEXT("../../escape.fbx"), Absolute, Error));
			TestEqual(TEXT("'..' escape -> IMPORT_SOURCE_NOT_ALLOWED"), Error.Code, FString(AnimMcpErrorCodes::ImportSourceNotAllowed));
			Error = FAnimMcpError();
			TestFalse(TEXT("missing file refused"), AnimMcpGeneration::ResolveImportSource(Root + FGuid::NewGuid().ToString() + TEXT(".fbx"), Absolute, Error));
			TestEqual(TEXT("missing file -> BAD_REQUEST"), Error.Code, FString(AnimMcpErrorCodes::BadRequest));
		}
	}

	// ---- 전역 더티 가드: 허용 목록 밖 새 더티는 UNEXPECTED_DIRTY, 안쪽은 통과 (메모리 패키지만, 끝나면 깨끗이) ----
	const FString Suffix = FGuid::NewGuid().ToString(EGuidFormats::Digits);
	UPackage* Outside = CreatePackage(*FString::Printf(TEXT("/Game/__AnimMcpGuardProbe_%s"), *Suffix));
	UPackage* Inside = CreatePackage(*FString::Printf(TEXT("%s__AnimMcpGuardProbe_%s"), *Prefix, *Suffix));
	{
		const AnimMcpGeneration::FDirtyGuard Guard;
		Inside->SetDirtyFlag(true);
		FAnimMcpError Error;
		TestTrue(TEXT("dirty package inside GenerationOutputPaths passes"), Guard.Check(Error));
		TArray<FString> Allowed, Unexpected;
		Guard.GetNewlyDirty(Allowed, Unexpected);
		TestTrue(TEXT("inside package reported as allowed"), Allowed.Contains(Inside->GetName()));

		Outside->SetDirtyFlag(true);
		Error = FAnimMcpError();
		TestFalse(TEXT("dirty package outside GenerationOutputPaths fails"), Guard.Check(Error));
		TestEqual(TEXT("outside -> UNEXPECTED_DIRTY"), Error.Code, FString(AnimMcpErrorCodes::UnexpectedDirty));
		const TArray<TSharedPtr<FJsonValue>>* Listed = nullptr;
		const bool bListed = Error.Details.IsValid() && Error.Details->TryGetArrayField(TEXT("unexpected"), Listed)
			&& Listed->ContainsByPredicate([Outside](const TSharedPtr<FJsonValue>& V) { return V->AsString() == Outside->GetName(); });
		TestTrue(TEXT("details.unexpected lists the outside package"), bListed);
	}
	{
		// 호출 전부터 더티였던 패키지는 비교에서 빠진다
		const AnimMcpGeneration::FDirtyGuard Guard;
		FAnimMcpError Error;
		TestTrue(TEXT("package already dirty before the guard is not reported"), Guard.Check(Error));
	}
	Inside->SetDirtyFlag(false);
	Outside->SetDirtyFlag(false);
	Inside->MarkAsGarbage();
	Outside->MarkAsGarbage();
	return true;
}

namespace
{
	FString ReasonOf(const FAnimMcpError& Error)
	{
		FString Reason;
		if (Error.Details.IsValid()) { Error.Details->TryGetStringField(TEXT("reason"), Reason); }
		return Reason;
	}
}

// AI 애니 생성 Phase 7 — promote_animation 의 경로 규칙(PromotionPaths 정규화 · 생성 경로와 겹침 · '/' 경계) · dest 검사(후보 경로 · 허용 목록 밖 ·
// 보호 · 메모리에만 있는 같은 이름) · confirm · 후보 아닌 소스 · FDirtyGuard 추가 허용 집합. 실제 이동은 통합 테스트(anim_gen_phase7_test.py promote).
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpGenerationPromoteTest, "AnimGraphMcp.Generation.Promote", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpGenerationPromoteTest::RunTest(const FString& Parameters)
{
	// ---- 정규화: 마운트 루트 · 생성 경로와 겹치는 항목(어느 쪽이 안이든)은 뺀다 ----
	{
		TArray<FString> Ignored;
		const TArray<FString> Normalized = AnimMcpGeneration::NormalizePromotionPaths(
			{ TEXT("/Game/Animation/Hero"), TEXT("/Game/"), TEXT("/Game/Animation/"), TEXT("/Game/Animation/Test/Sub/"), TEXT("Game/Promoted") },
			{ TEXT("/Game/Animation/Generated/"), TEXT("/Game/Animation/Test/") }, &Ignored);
		TestEqual(TEXT("two promotion paths survive"), Normalized.Num(), 2);
		TestTrue(TEXT("trailing '/' added"), Normalized.Contains(TEXT("/Game/Animation/Hero/")));
		TestTrue(TEXT("leading '/' added"), Normalized.Contains(TEXT("/Game/Promoted/")));
		TestEqual(TEXT("mount root + two overlaps ignored"), Ignored.Num(), 3);
	}

	const AnimMcpGeneration::FSettings& Settings = AnimMcpGeneration::GetSettings();
	if (Settings.PromotionPaths.Num() == 0 || Settings.OutputPaths.Num() == 0)
	{
		AddWarning(TEXT("No [AnimGraphMcp] PromotionPaths / GenerationOutputPaths configured — promotion path checks skipped"));
		return true;
	}
	const FString Prefix = Settings.PromotionPaths[0];               // "/Game/Animation/Hero/"
	const FString PrefixFolder = Prefix.LeftChop(1);
	TestTrue(TEXT("asset below a promotion path is allowed"), AnimMcpGeneration::IsPromotionPathAllowed(Prefix + TEXT("Sub/AS_X.AS_X")));
	TestFalse(TEXT("sibling folder sharing the name prefix is refused"), AnimMcpGeneration::IsPromotionPathAllowed(PrefixFolder + TEXT("_AnimMcpSibling/AS_X")));
	TestFalse(TEXT("candidate path is not a promotion path"), AnimMcpGeneration::IsPromotionPathAllowed(Settings.OutputPaths[0] + TEXT("AS_X")));
	TestTrue(TEXT("get_editor_status lists promotion_paths"), AnimMcpGeneration::DescribeSettings()->HasField(TEXT("promotion_paths")));

	// ---- dest 검사 ----
	auto ExpectDest = [this](const FString& Dest, const TCHAR* Code, const TCHAR* Reason, const TCHAR* What)
	{
		FString ObjectPath;
		FAnimMcpError Error;
		TestFalse(What, AnimMcpPromote::ValidateDest(Dest, TEXT("dest"), ObjectPath, Error));
		TestEqual(FString(What) + TEXT(" → code"), Error.Code, FString(Code));
		if (Reason) { TestEqual(FString(What) + TEXT(" → reason"), ReasonOf(Error), FString(Reason)); }
	};
	const FString Suffix = FGuid::NewGuid().ToString(EGuidFormats::Digits);
	ExpectDest(Prefix + TEXT("Sub/"), AnimMcpErrorCodes::BadRequest, TEXT("DEST_NOT_ASSET_PATH"), TEXT("folder dest refused"));
	ExpectDest(Prefix + TEXT("Sub/AS_X.AS_Y"), AnimMcpErrorCodes::BadRequest, TEXT("OBJECT_NAME_MISMATCH"), TEXT("object name mismatch refused"));
	ExpectDest(Settings.OutputPaths[0] + TEXT("AS_X"), AnimMcpErrorCodes::OutputPathNotAllowed, TEXT("DEST_IS_CANDIDATE_PATH"), TEXT("candidate path dest refused"));
	ExpectDest(FString::Printf(TEXT("/Game/__AnimMcpPromoteProbe_%s/AS_X"), *Suffix), AnimMcpErrorCodes::OutputPathNotAllowed, TEXT("OUTSIDE_PROMOTION_PATHS"), TEXT("dest outside PromotionPaths refused"));
	int32 ProtectedChecked = 0;
	for (const FString& Rule : AnimMcpAssetProtection::GetRules().Assets)
	{
		if (AnimMcpGeneration::IsPromotionPathAllowed(Rule))
		{
			ExpectDest(Rule, AnimMcpErrorCodes::AssetProtected, TEXT("DEST_PROTECTED"), TEXT("protected dest refused before ASSET_EXISTS"));
			++ProtectedChecked;
		}
	}
	if (ProtectedChecked == 0)
	{
		AddInfo(TEXT("No ProtectedAssets entry lies inside PromotionPaths — protection check skipped"));
	}
	{
		// 메모리에만 있는 같은 이름 객체(디스크에는 없음)도 ASSET_EXISTS — 레지스트리 조회(bIncludeOnlyOnDiskAssets=false)가 메모리 애셋도 보므로
		// 사유는 DEST_EXISTS(실측) 또는 DEST_IN_MEMORY(레지스트리가 그 클래스를 애셋으로 안 볼 때)
		const FString Folder = FString::Printf(TEXT("%s__AnimMcpPromoteProbe_%s"), *Prefix, *Suffix);
		UPackage* Probe = CreatePackage(*(Folder + TEXT("/AS_Probe")));
		UCurveFloat* Object = NewObject<UCurveFloat>(Probe, TEXT("AS_Probe"), RF_Transient);
		FString ObjectPath;
		FAnimMcpError Error;
		TestFalse(TEXT("in-memory object at dest refused"), AnimMcpPromote::ValidateDest(Folder + TEXT("/AS_Probe"), TEXT("dest"), ObjectPath, Error));
		TestEqual(TEXT("in-memory object at dest → ASSET_EXISTS"), Error.Code, FString(AnimMcpErrorCodes::AssetExists));
		TestTrue(TEXT("in-memory object at dest → DEST_EXISTS | DEST_IN_MEMORY"), ReasonOf(Error) == TEXT("DEST_EXISTS") || ReasonOf(Error) == TEXT("DEST_IN_MEMORY"));
		Error = FAnimMcpError();
		TestTrue(TEXT("free dest inside PromotionPaths passes"), AnimMcpPromote::ValidateDest(Folder + TEXT("/AS_Free"), TEXT("dest"), ObjectPath, Error));
		TestEqual(TEXT("dest normalized to the object path"), ObjectPath, Folder + TEXT("/AS_Free.AS_Free"));
		Object->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty);
		Object->MarkAsGarbage();
		Probe->MarkAsGarbage();
	}

	// ---- confirm · 후보가 아닌 소스 ----
	{
		const FAnimMcpRequest Raw(TEXT("promote_animation"), FString(), AnimMcpJson::MakeObject());
		FAnimMcpContext Context(Raw);
		AnimMcpPromote::FRequest Request;
		Request.Items.Add({ Settings.OutputPaths[0] + TEXT("AS_X"), Prefix + TEXT("Sub/AS_X") });
		FAnimMcpError Error;
		TestFalse(TEXT("no confirm refused"), AnimMcpPromote::Run(Request, Context, Error).IsValid());
		TestEqual(TEXT("no confirm → MISSING_CONFIRM"), ReasonOf(Error), FString(TEXT("MISSING_CONFIRM")));

		Request.bDryRun = true;
		Request.Items[0].Source = Prefix + TEXT("Sub/AS_NotACandidate");
		Error = FAnimMcpError();
		TestFalse(TEXT("dry_run with a non-candidate source refused"), AnimMcpPromote::Run(Request, Context, Error).IsValid());
		TestEqual(TEXT("non-candidate → OUTPUT_PATH_NOT_ALLOWED"), Error.Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
		TestEqual(TEXT("non-candidate → SOURCE_NOT_CANDIDATE"), ReasonOf(Error), FString(TEXT("SOURCE_NOT_CANDIDATE")));
	}

	// ---- FDirtyGuard 추가 허용 집합 — 허용 목록 밖이어도 명시한 패키지(승격 dest · allow_referencers)는 허용 쪽 ----
	{
		UPackage* Outside = CreatePackage(*FString::Printf(TEXT("/Game/__AnimMcpPromoteDirtyProbe_%s"), *Suffix));
		const AnimMcpGeneration::FDirtyGuard Guard;
		Outside->SetDirtyFlag(true);
		FAnimMcpError Error;
		TestFalse(TEXT("outside dirty package fails without extra allowance"), Guard.Check(Error));
		const TSet<FName> Extra = { Outside->GetFName() };
		Error = FAnimMcpError();
		TestTrue(TEXT("outside dirty package passes when listed as extra allowed"), Guard.Check(Error, &Extra));
		TArray<FString> Allowed, Unexpected;
		Guard.GetNewlyDirty(Allowed, Unexpected, &Extra);
		TestTrue(TEXT("extra allowed package reported as allowed"), Allowed.Contains(Outside->GetName()) && Unexpected.Num() == 0);
		Outside->SetDirtyFlag(false);
		Outside->MarkAsGarbage();
	}
	return true;
}

// AI 애니 생성 Phase 7 — 기존 쓰기 Tool 6개의 옵트인 generation_guard. 꺼짐(기본) = 기존 동작(경로 검사 없음 — 없는 애셋이라 ASSET_NOT_FOUND 까지 간다),
// 켬 = 허용 목록 밖 OUTPUT_PATH_NOT_ALLOWED · overwrite 거부 · 전역 더티 비교. 실제 핸들러를 로컬 디스패처로 부른다 — 애셋은 만들지 않는다.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpGenerationWriteGuardTest, "AnimGraphMcp.Generation.WriteGuard", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpGenerationWriteGuardTest::RunTest(const FString& Parameters)
{
	const AnimMcpGeneration::FSettings& Settings = AnimMcpGeneration::GetSettings();
	if (Settings.OutputPaths.Num() == 0)
	{
		AddWarning(TEXT("No [AnimGraphMcp] GenerationOutputPaths configured — generation_guard checks skipped"));
		return true;
	}
	FAnimMcpDispatcher Dispatcher;
	AnimMcpTools::RegisterMontageTools(Dispatcher);
	AnimMcpTools::RegisterAssetTools(Dispatcher);
	AnimMcpTools::RegisterSequenceTools(Dispatcher);
	AnimMcpTools::RegisterGraphTools(Dispatcher);

	const FString Suffix = FGuid::NewGuid().ToString(EGuidFormats::Digits);
	const FString Outside = FString::Printf(TEXT("/Game/__AnimMcpGuardProbe_%s/AS_X"), *Suffix);
	const FString Inside = FString::Printf(TEXT("%s__AnimMcpGuardProbe_%s/AS_X"), *Settings.OutputPaths[0], *Suffix);
	const FString Missing = FString::Printf(TEXT("%s__AnimMcpGuardProbe_%s/AS_Missing"), *Settings.OutputPaths[0], *Suffix);

	// 봉투 → (code, reason)
	auto Call = [&Dispatcher](const TCHAR* Tool, const FString& Body, bool bGuard, FString& OutReason)
	{
		TSharedPtr<FJsonObject> Params;
		FString ParseError;
		AnimMcpJson::Parse(Body, Params, ParseError);
		Params->SetBoolField(TEXT("generation_guard"), bGuard);
		int32 Status = 0;
		TSharedPtr<FJsonObject> Envelope;
		AnimMcpJson::Parse(Dispatcher.Dispatch(Tool, AnimMcpJson::ToString(Params.ToSharedRef()), Status), Envelope, ParseError);
		FString Code;
		OutReason.Reset();
		const TSharedPtr<FJsonObject>* Error = nullptr;
		if (Envelope.IsValid() && Envelope->TryGetObjectField(TEXT("error"), Error) && Error)
		{
			(*Error)->TryGetStringField(TEXT("code"), Code);
			const TSharedPtr<FJsonObject>* Details = nullptr;
			if ((*Error)->TryGetObjectField(TEXT("details"), Details) && Details) { (*Details)->TryGetStringField(TEXT("reason"), OutReason); }
		}
		return Code;
	};
	auto Expect = [&](const TCHAR* Tool, const FString& Body, const TCHAR* OffCode, const TCHAR* OnCode, const TCHAR* OnReason = nullptr)
	{
		FString Reason;
		TestEqual(FString::Printf(TEXT("%s guard off → %s (existing behaviour)"), Tool, OffCode), Call(Tool, Body, false, Reason), FString(OffCode));
		TestEqual(FString::Printf(TEXT("%s guard on → %s"), Tool, OnCode), Call(Tool, Body, true, Reason), FString(OnCode));
		if (OnReason) { TestEqual(FString::Printf(TEXT("%s guard on → reason %s"), Tool, OnReason), Reason, FString(OnReason)); }
	};
	const FString Axes = TEXT("\"dimensions\": 1, \"axes\": [{\"name\": \"Speed\", \"min\": 0, \"max\": 100}]");

	// 허용 목록 밖 경로 — 꺼짐은 지금처럼 다음 검사(없는 애셋)까지, 켬은 그 전에 OUTPUT_PATH_NOT_ALLOWED
	Expect(TEXT("create_anim_montage"), FString::Printf(TEXT("{\"asset_path\": \"%s\", \"animation\": \"%s\"}"), *Outside, *Missing), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::OutputPathNotAllowed);
	Expect(TEXT("set_montage_sections"), FString::Printf(TEXT("{\"asset_path\": \"%s\", \"sections\": [{\"name\": \"Default\", \"start\": 0}]}"), *Outside), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::OutputPathNotAllowed);
	Expect(TEXT("create_blendspace"), FString::Printf(TEXT("{\"asset_path\": \"%s\", \"skeleton\": \"%s\", %s}"), *Outside, *Missing, *Axes), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::OutputPathNotAllowed);
	Expect(TEXT("set_sequence_additive"), FString::Printf(TEXT("{\"asset_path\": \"%s\"}"), *Outside), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::OutputPathNotAllowed);
	Expect(TEXT("duplicate_animation_blueprint"), FString::Printf(TEXT("{\"source_path\": \"%s\", \"dest_path\": \"%s\"}"), *Missing, *Outside), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::OutputPathNotAllowed);
	Expect(TEXT("apply_graph_operations"), FString::Printf(TEXT("{\"asset_path\": \"%s\", \"operations\": []}"), *Outside), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::OutputPathNotAllowed);

	// 허용 목록 안 + overwrite — 켬은 덮어쓰기를 받지 않는다
	Expect(TEXT("create_anim_montage"), FString::Printf(TEXT("{\"asset_path\": \"%s\", \"animation\": \"%s\", \"overwrite\": true}"), *Inside, *Missing), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::BadRequest, TEXT("OVERWRITE_NOT_ALLOWED"));
	Expect(TEXT("create_blendspace"), FString::Printf(TEXT("{\"asset_path\": \"%s\", \"skeleton\": \"%s\", \"overwrite\": true, %s}"), *Inside, *Missing, *Axes), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::BadRequest, TEXT("OVERWRITE_NOT_ALLOWED"));
	Expect(TEXT("duplicate_animation_blueprint"), FString::Printf(TEXT("{\"source_path\": \"%s\", \"dest_path\": \"%s\", \"overwrite\": true}"), *Missing, *Inside), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::BadRequest, TEXT("OVERWRITE_NOT_ALLOWED"));

	// 허용 목록 안 · 덮어쓰기 없음 — 켬도 경로는 통과하고 다음 검사(없는 애셋)로 간다
	Expect(TEXT("set_sequence_additive"), FString::Printf(TEXT("{\"asset_path\": \"%s\"}"), *Missing), AnimMcpErrorCodes::AssetNotFound, AnimMcpErrorCodes::AssetNotFound);

	// ---- 전역 더티 비교 — 꺼짐은 보지 않고, 켬은 허용 목록 밖 새 더티를 UNEXPECTED_DIRTY 로 ----
	UPackage* OutsidePackage = CreatePackage(*FString::Printf(TEXT("/Game/__AnimMcpGuardDirtyProbe_%s"), *Suffix));
	UPackage* InsidePackage = CreatePackage(*FString::Printf(TEXT("%s__AnimMcpGuardDirtyProbe_%s"), *Settings.OutputPaths[0], *Suffix));
	{
		const FAnimMcpRequest Off(TEXT("probe"), FString(), AnimMcpJson::MakeObject());
		TSharedRef<FJsonObject> OnParams = AnimMcpJson::MakeObject();
		OnParams->SetBoolField(TEXT("generation_guard"), true);
		const FAnimMcpRequest On(TEXT("probe"), FString(), OnParams);
		AnimMcpGeneration::FWriteGuard GuardOff(Off);
		AnimMcpGeneration::FWriteGuard GuardOn(On);
		TestFalse(TEXT("guard off by default"), GuardOff.IsEnabled());
		TestTrue(TEXT("guard on when requested"), GuardOn.IsEnabled());

		InsidePackage->SetDirtyFlag(true);
		FAnimMcpError Error;
		TestTrue(TEXT("guard on: inside dirty passes"), GuardOn.Check(Error));
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		GuardOn.Describe(Result);
		const TSharedPtr<FJsonObject>* GuardObj = nullptr;
		const TArray<TSharedPtr<FJsonValue>>* NewlyDirty = nullptr;
		TestTrue(TEXT("guard on: result guard.newly_dirty lists the inside package"),
			Result->TryGetObjectField(TEXT("guard"), GuardObj) && (*GuardObj)->TryGetArrayField(TEXT("newly_dirty"), NewlyDirty)
			&& NewlyDirty->ContainsByPredicate([InsidePackage](const TSharedPtr<FJsonValue>& V) { return V->AsString() == InsidePackage->GetName(); }));

		OutsidePackage->SetDirtyFlag(true);
		Error = FAnimMcpError();
		TestFalse(TEXT("guard on: outside dirty fails"), GuardOn.Check(Error));
		TestEqual(TEXT("guard on: outside dirty → UNEXPECTED_DIRTY"), Error.Code, FString(AnimMcpErrorCodes::UnexpectedDirty));
		Error = FAnimMcpError();
		TestTrue(TEXT("guard off: dirty diff not checked"), GuardOff.Check(Error));
		TSharedRef<FJsonObject> OffResult = AnimMcpJson::MakeObject();
		GuardOff.Describe(OffResult);
		TestFalse(TEXT("guard off: result has no guard field"), OffResult->HasField(TEXT("guard")));
	}
	InsidePackage->SetDirtyFlag(false);
	OutsidePackage->SetDirtyFlag(false);
	InsidePackage->MarkAsGarbage();
	OutsidePackage->MarkAsGarbage();
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
