// AI 애니 생성 Phase 8-2 — 대상 메시 캡처(Core/AnimMcpCapture)의 계산부 · 출력 폴더 규칙 단위 테스트.
// 카메라 맞춤 · 시트 축소 · 시각 펼치기 · 샘플 프레임은 Blender 소스 골격 렌더(Tools/mcp/anim_gen/blender/review_render.py)와 같은 입력 → 같은 출력이어야
// 두 시트가 나란히 맞는다(기대값은 그 Python 수식으로 손 계산). 출력 폴더 검사는 CaptureOutputRoots 첫 루트 아래 임시 폴더로 보고 지운다.
// run_automation_tests {filter:"AnimGraphMcp.Generation.Capture"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpCapture.h"
#include "Core/AnimMcpGeneration.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpCaptureTest, "AnimGraphMcp.Generation.Capture", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpCaptureTest::RunTest(const FString& Parameters)
{
	using namespace AnimMcpCapture;

	// ---- 부착물 offset (Phase 8-4a): {location, rotation [pitch, yaw, roll], scale} → 상대 변환, 빈 값 = 항등, 모르는 키 · 0 스케일 · 형식 오류 거부 ----
	{
		FTransform X;
		FString Why;
		TestTrue(TEXT("offset: null = identity"), ParseOffset(nullptr, X, Why) && X.Equals(FTransform::Identity));
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetArrayField(TEXT("location"), { MakeShared<FJsonValueNumber>(-8.5), MakeShared<FJsonValueNumber>(4.0), MakeShared<FJsonValueNumber>(56.0) });
		Obj->SetArrayField(TEXT("rotation"), { MakeShared<FJsonValueNumber>(10.0), MakeShared<FJsonValueNumber>(20.0), MakeShared<FJsonValueNumber>(30.0) });
		TestTrue(TEXT("offset: parsed"), ParseOffset(Obj, X, Why));
		TestTrue(TEXT("offset: location · rotation(pitch, yaw, roll) · default scale"), X.Equals(FTransform(FRotator(10.0, 20.0, 30.0).Quaternion(), FVector(-8.5, 4.0, 56.0)), 1e-6));
		Obj->SetArrayField(TEXT("scale"), { MakeShared<FJsonValueNumber>(0.0), MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(1.0) });
		TestFalse(TEXT("offset: zero scale refused"), ParseOffset(Obj, X, Why));
		TSharedRef<FJsonObject> Bad = AnimMcpJson::MakeObject();
		Bad->SetArrayField(TEXT("translation"), { MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(1.0) });
		TestFalse(TEXT("offset: unknown key refused"), ParseOffset(Bad, X, Why));
		TSharedRef<FJsonObject> Short = AnimMcpJson::MakeObject();
		Short->SetArrayField(TEXT("location"), { MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(1.0) });
		TestFalse(TEXT("offset: two numbers refused"), ParseOffset(Short, X, Why));
	}

	// ---- 카메라 맞춤: 좁은 범위 = 폭 하한(1/max_aspect) · 세로 기준, 넓은 범위 = 비율대로 · 가로 기준, 바닥 z = 0 포함 ----
	{
		FRange Range;
		Range.Add(-30.0, 0.0, -10.0);
		Range.Add(30.0, 170.0, 20.0);
		const FViewFit Fit = FitView(Range, 0.08, 512, 2.0);
		TestEqual(TEXT("narrow: width clamped to 1/max_aspect"), Fit.Width, 256);
		TestEqual(TEXT("narrow: cell height"), Fit.Height, 512);
		TestTrue(TEXT("narrow: scale = need_h 197.2"), FMath::IsNearlyEqual(Fit.Scale, 197.2, 1e-6));
		TestTrue(TEXT("narrow: extent w = scale × 0.5"), FMath::IsNearlyEqual(Fit.ExtentW, 98.6, 1e-6));
		TestTrue(TEXT("narrow: centre v"), FMath::IsNearlyEqual(Fit.CenterV, 85.0, 1e-9));
		TestTrue(TEXT("narrow: depth range kept"), FMath::IsNearlyEqual(Fit.DMin, -10.0, 1e-9) && FMath::IsNearlyEqual(Fit.DMax, 20.0, 1e-9));
	}
	{
		FRange Range;
		Range.Add(0.0, 10.0, 0.0);      // 바닥보다 위에서 시작해도 v 하한은 0
		Range.Add(300.0, 170.0, 0.0);
		const FViewFit Fit = FitView(Range, 0.08, 512, 2.0);
		TestEqual(TEXT("wide: width = round(512 × 1.7647 / 2) × 2"), Fit.Width, 904);
		TestTrue(TEXT("wide: scale = max(need_w, need_h × r)"), FMath::IsNearlyEqual(Fit.Scale, 197.2 * 904.0 / 512.0, 1e-6));
		TestTrue(TEXT("wide: extent h = need_h"), FMath::IsNearlyEqual(Fit.ExtentH, 197.2, 1e-6));
		TestTrue(TEXT("wide: floor included (centre v 85)"), FMath::IsNearlyEqual(Fit.CenterV, 85.0, 1e-9));
		TestTrue(TEXT("wide: centre u"), FMath::IsNearlyEqual(Fit.CenterU, 150.0, 1e-9));
	}

	// ---- 시트 축소 · 시각 펼치기 · 샘플 프레임 ----
	TestTrue(TEXT("sheet scale = (3000 − 42) / (512 × 6)"), FMath::IsNearlyEqual(SheetScale({ 256, 904 }, 512, 6, 6, 3000.0), (3000.0 - 42.0) / 3072.0, 1e-9));
	TestEqual(TEXT("sheet scale never enlarges"), SheetScale({ 100 }, 100, 1, 6, 3000.0), 1.0);
	{
		const TArray<double> Times = Spread(4, 4.0);
		TestEqual(TEXT("spread count"), Times.Num(), 4);
		TestTrue(TEXT("spread first/last"), Times[0] == 0.0 && Times[3] == 4.0);
		TestTrue(TEXT("spread rounded to 4 decimals"), FMath::IsNearlyEqual(Times[1], 1.3333, 1e-9));
		const TArray<double> One = Spread(1, 4.0);
		TestTrue(TEXT("spread of one = first frame"), One.Num() == 1 && One[0] == 0.0);
	}
	TestEqual(TEXT("sample frames: short clip = every frame"), SampleFrames(0, 120, 600, { 25 }).Num(), 121);
	{
		const TArray<int32> Frames = SampleFrames(0, 999, 300, { 1 });
		TestEqual(TEXT("sample frames: step 4 + last + extra"), Frames.Num(), 252);
		TestTrue(TEXT("sample frames: sorted with last"), Frames[0] == 0 && Frames[1] == 1 && Frames.Last() == 999);
	}

	// ---- 출력 폴더: 상대 · 루트 자체 · 루트 밖 거부, 새 하위 폴더 허용, 비지 않은 폴더 거부 ----
	const TArray<FString>& Roots = AnimMcpGeneration::GetSettings().CaptureOutputRoots;
	if (Roots.Num() == 0)
	{
		AddWarning(TEXT("No [AnimGraphMcp] CaptureOutputRoots configured — output folder checks skipped"));
		return true;
	}
	const FString Root = Roots[0];
	FString Absolute;
	{
		FAnimMcpError Error;
		TestFalse(TEXT("relative folder refused"), AnimMcpGeneration::ResolveCaptureDir(TEXT("Tools/x"), Absolute, Error));
		TestEqual(TEXT("relative -> BAD_REQUEST"), Error.Code, FString(AnimMcpErrorCodes::BadRequest));
		Error = FAnimMcpError();
		TestFalse(TEXT("root itself refused"), AnimMcpGeneration::ResolveCaptureDir(Root, Absolute, Error));
		TestEqual(TEXT("root -> OUTPUT_PATH_NOT_ALLOWED"), Error.Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
		Error = FAnimMcpError();
		TestFalse(TEXT("'..' escape refused"), AnimMcpGeneration::ResolveCaptureDir(Root + TEXT("../escape"), Absolute, Error));
		TestEqual(TEXT("escape -> OUTPUT_PATH_NOT_ALLOWED"), Error.Code, FString(AnimMcpErrorCodes::OutputPathNotAllowed));
	}
	const FString Probe = Root + TEXT("__CaptureProbe_") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
	{
		FAnimMcpError Error;
		TestTrue(TEXT("new folder below root allowed"), AnimMcpGeneration::ResolveCaptureDir(Probe + TEXT("/"), Absolute, Error));
		TestEqual(TEXT("normalized without trailing '/'"), Absolute, Probe);
		TestTrue(TEXT("probe file written"), FFileHelper::SaveStringToFile(TEXT("x"), *(Probe / TEXT("x.txt"))));
		Error = FAnimMcpError();
		TestFalse(TEXT("non-empty folder refused"), AnimMcpGeneration::ResolveCaptureDir(Probe, Absolute, Error));
		TestTrue(TEXT("non-empty -> OUTPUT_DIR_NOT_EMPTY"), Error.Details.IsValid() && Error.Details->GetStringField(TEXT("reason")) == TEXT("OUTPUT_DIR_NOT_EMPTY"));
		// 비교 칸 이미지(Phase 8-3) — 앞선 캡처 결과(캡처 루트 아래 파일)도 받는다, 없는 파일 · 두 루트 밖은 거부
		Error = FAnimMcpError();
		TestTrue(TEXT("compare image below the capture root allowed"), AnimMcpGeneration::ResolveCompareImage(Probe / TEXT("x.txt"), Absolute, Error));
		TestEqual(TEXT("compare image normalized"), Absolute, Probe / TEXT("x.txt"));
		Error = FAnimMcpError();
		TestFalse(TEXT("missing compare image refused"), AnimMcpGeneration::ResolveCompareImage(Probe / TEXT("none.png"), Absolute, Error));
		TestTrue(TEXT("missing -> FILE_NOT_FOUND"), Error.Details.IsValid() && Error.Details->GetStringField(TEXT("reason")) == TEXT("FILE_NOT_FOUND"));
		Error = FAnimMcpError();
		TestFalse(TEXT("compare image outside both roots refused"), AnimMcpGeneration::ResolveCompareImage(Root + TEXT("../outside.png"), Absolute, Error));
		TestEqual(TEXT("outside -> IMPORT_SOURCE_NOT_ALLOWED"), Error.Code, FString(AnimMcpErrorCodes::ImportSourceNotAllowed));
		IFileManager::Get().DeleteDirectory(*Probe, /*RequireExists*/ false, /*Tree*/ true);
		TestFalse(TEXT("probe folder removed"), IFileManager::Get().DirectoryExists(*Probe));
	}
	return true;
}

#endif
