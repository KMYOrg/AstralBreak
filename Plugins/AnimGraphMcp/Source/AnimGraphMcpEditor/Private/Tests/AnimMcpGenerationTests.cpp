// AI 애니 생성 Phase 1 — 공통 가드(Core/AnimMcpGeneration) 단위 테스트. 경로 허용 목록의 '/' 경계, 임포트 원본 검사,
// 전역 더티 집합 비교가 허용 목록 밖 패키지를 실제로 잡는지(UNEXPECTED_DIRTY)를 메모리 안 임시 패키지로 확인한다 — 디스크에는 쓰지 않는다.
// run_automation_tests {filter:"AnimGraphMcp.Generation"} 로 돈다. 기대값은 프로젝트 ini 의 첫 GenerationOutputPaths · ImportSourceRoots 기준.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpGeneration.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"
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

#endif // WITH_DEV_AUTOMATION_TESTS
