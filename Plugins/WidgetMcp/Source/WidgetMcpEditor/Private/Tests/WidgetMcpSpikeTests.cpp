// Phase 0 스파이크 시험 — 설계 Docs/Design/ui-autogen-pipeline.md §12-1 A6 · A7.
// 손 spec → WBP(/Game/_AutoGen/Spike/ 메모리에만, 저장 안 함) → 컴파일 → FWidgetRenderer 3회 → PNG · report.json (Tools/mcp/results/widget_spike/<시각>/ — git 무시).
// 판정: 파이프라인이 끝까지 돌고(컴파일 오류 0 · PNG 3장) geometry 가 캔버스 슬롯과 1 px 안에서 맞으면 통과. 가정의 참 · 거짓(팩토리 루트 · 그림 안정 · 한글)은 report 에 기록만 한다.
// 실행: run_automation_tests {filter:"WidgetMcp.Spike"}

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/DateTime.h"
#include "Misc/Paths.h"
#include "Spike/WidgetMcpSpike.h"

namespace WidgetMcpSpikeTests
{
	/** 손으로 쓴 작은 spec — M4 HUD 의 축소판(패널 · 아이콘 · 제목 · 게이지 · 구석 글자 · 한글) */
	const TCHAR* const Spec = TEXT(R"JSON({
  "canvas": [640, 360],
  "root": "Root",
  "widgets": [
    { "id": "Root", "type": "CanvasPanel" },
    { "id": "Panel", "type": "Border", "parent": "Root", "slot": { "position": [40, 40], "size": [320, 140] }, "color": "#202838" },
    { "id": "PanelText", "type": "TextBlock", "parent": "Panel", "text": "Panel", "size": 12, "color": "#8090A0" },
    { "id": "Icon", "type": "Image", "parent": "Root", "slot": { "position": [60, 64], "size": [64, 64] } },
    { "id": "TitleLatin", "type": "TextBlock", "parent": "Root", "slot": { "position": [140, 60], "size": [200, 30] }, "text": "ULT GAUGE", "size": 20, "color": "#FFF3D6" },
    { "id": "TitleKorean", "type": "TextBlock", "parent": "Root", "slot": { "position": [140, 92], "size": [200, 30] }, "text": "오의 게이지", "size": 20, "color": "#FFF3D6" },
    { "id": "Gauge", "type": "ProgressBar", "parent": "Root", "slot": { "position": [140, 136], "size": [200, 20] }, "percent": 0.7, "fill": "#E8B54A" },
    { "id": "Corner", "type": "TextBlock", "parent": "Root", "slot": { "anchors": [1, 1, 1, 1], "alignment": [1, 1], "position": [-16, -16], "size": [140, 28] }, "text": "READY", "size": 16, "color": "#FFFFFF" }
  ],
  "color_probes": [
    { "id": "panel", "at": [350, 170], "expect": "#202838" },
    { "id": "checker_gold", "at": [70, 66], "expect": "#E8B54A" },
    { "id": "checker_dark", "at": [62, 66], "expect": "#282828" }
  ]
})JSON");
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpSpikeBuildRenderTest, "WidgetMcp.Spike.BuildRender", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpSpikeBuildRenderTest::RunTest(const FString& Parameters)
{
	const FString Stamp = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
	const FString AssetPath = FString::Printf(TEXT("/Game/_AutoGen/Spike/WBP_Spike_%s"), *Stamp);
	const FString OutputDir = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(), TEXT("Tools/mcp/results/widget_spike"), Stamp));

	WidgetMcpSpike::FResult Result;
	FString Error;
	const bool bOk = WidgetMcpSpike::Run(WidgetMcpSpikeTests::Spec, AssetPath, OutputDir, Result, Error);

	AddInfo(FString::Printf(TEXT("report: %s"), *Result.ReportPath));
	AddInfo(FString::Printf(TEXT("A7 factory root without dialog: %s (%s), template selector %s, default root %s"),
		Result.bFactoryRootSet ? TEXT("yes") : TEXT("no"), *Result.FactoryRootClass,
		Result.bUseWidgetTemplateSelector ? TEXT("on") : TEXT("off"), *Result.DefaultRootWidget));
	FString Diffs;
	for (int32 D : Result.DiffPixelsVsPrev) { Diffs += FString::Printf(TEXT("%d "), D); }
	AddInfo(FString::Printf(TEXT("A6 diff pixels draw2-vs-1 / draw3-vs-2: %s, max geometry error %.2f px"), *Diffs, Result.MaxGeometryErrorPx));
	for (const TPair<FString, TArray<int32>>& Pair : Result.TextInk)
	{
		FString Per;
		for (int32 V : Pair.Value) { Per += FString::Printf(TEXT("%d "), V); }
		AddInfo(FString::Printf(TEXT("text ink %s: %s"), *Pair.Key, *Per));
	}

	TestTrue(FString::Printf(TEXT("spike pipeline ran (%s)"), *Error), bOk);
	TestTrue(TEXT("compiled"), Result.bCompiled);
	TestEqual(TEXT("compile errors"), Result.CompileErrors, 0);
	TestEqual(TEXT("every widget has a GUID entry"), Result.MissingGuids.Num(), 0);
	TestEqual(TEXT("three PNGs"), Result.Pngs.Num(), 3);
	TestTrue(TEXT("geometry within 1 px of the canvas slots"), Result.MaxGeometryErrorPx >= 0.0 && Result.MaxGeometryErrorPx <= 1.0);
	if (const TArray<int32>* Latin = Result.TextInk.Find(TEXT("TitleLatin")))
	{
		TestTrue(TEXT("latin text drawn by the last draw"), Latin->Num() > 0 && Latin->Last() > 0);
	}
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
