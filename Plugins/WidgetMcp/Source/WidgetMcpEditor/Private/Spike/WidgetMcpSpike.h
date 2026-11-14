#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

/**
 * Phase 0 스파이크 — 설계 §12-1 가정 A6 · A7 확인용 (정식 Tool 아님, Phase 1a 에서 apply_widget_spec · render_widget 로 대체).
 *
 *   A7  UWidgetBlueprintFactory 를 대화창 없이(ConfigureProperties 생략) FactoryCreateNew 만 불러도 루트 위젯이 정해지는가.
 *       아니면 CanvasPanel 루트를 직접 만들고 OnVariableAdded 를 부른다(설계 §12-1 '틀리면').
 *   A6  ConstructWidget + OnVariableAdded 로 손 spec 을 짓고 컴파일 → FWidgetRenderer 로 세 번 그려 PNG 와 GetPaintSpaceGeometry 를 읽는다.
 *       두 번째 · 세 번째 그림이 같은가(폰트 · 텍스처 로딩 지연), geometry 가 spec 의 캔버스 슬롯과 맞는가, 글자(라틴 · 한글)가 그려지는가.
 *
 * 애셋은 메모리에만 만들고 저장하지 않는다(경로는 호출자가 /Game/_AutoGen/ 아래로 준다). PNG · report.json 은 OutputDir(Saved 밖)에 쓴다.
 */
namespace WidgetMcpSpike
{
	struct FResult
	{
		/** A7 — 팩토리만으로 루트가 생겼는가 · 그 클래스 · 프로젝트 설정 */
		bool bFactoryRootSet = false;
		FString FactoryRootClass;
		bool bUseWidgetTemplateSelector = false;
		FString DefaultRootWidget;

		bool bCompiled = false;
		int32 CompileErrors = 0;
		int32 CompileWarnings = 0;

		/** OnVariableAdded 로 GUID 맵에 들어간 이름 수 · 빠진 이름 */
		int32 GuidMapCount = 0;
		TArray<FString> MissingGuids;

		TArray<FString> Pngs;
		/** 그림 i 와 i-1 의 다른 픽셀 수 (i = 2, 3) */
		TArray<int32> DiffPixelsVsPrev;
		/** 캔버스 슬롯 기대값 대비 GetPaintSpaceGeometry 최대 오차(px) — 마지막 그림 기준 */
		double MaxGeometryErrorPx = -1.0;
		/** TextBlock 마다 bbox 안 밝은 픽셀 수 — 그림별 */
		TMap<FString, TArray<int32>> TextInk;

		FString ReportPath;
		TSharedPtr<FJsonObject> Report;
	};

	/** Spec(JSON) → WBP(메모리) → 컴파일 → 3회 렌더. 파이프라인 자체가 깨지면 false + OutError (가정이 틀린 것은 Result 에 기록하고 true) */
	bool Run(const FString& SpecJson, const FString& AssetPath, const FString& OutputDir, FResult& Out, FString& OutError);
}
