#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"

class UWidgetBlueprint;

/**
 * render_widget — 컴파일된 WBP 를 오프스크린으로 그려 PNG + 같은 그리기의 위젯 geometry 를 낸다 (설계 §6 · §12-1 A6).
 *
 * FWidgetRenderer(gamma=true) + CreateTargetFor(…, true)(B8G8R8A8 · SRGB=0, WidgetRenderer.cpp:81-100) 로 그리면 색에 sRGB 가 한 번 더
 * 걸린다(A6-색 실측) → 읽은 8비트 값에 채널마다 sRGB→선형 변환을 1회(LUT) 해서 지정색으로 되돌린 PNG 를 쓴다. 알파는 255(검은 바탕).
 * Scale 을 직접 주므로 DPI 곡선이 끼지 않고, GetPaintSpaceGeometry 가 픽셀 좌표 그대로다(오차 0 px 실측).
 * 출력은 [WidgetMcp] WidgetRenderOutputRoots 아래의 새 · 빈 폴더만.
 *
 * States 가 있으면 한 요청에서 상태마다 새 인스턴스를 만들어 같은 길로 그린다(uigen Phase 2) — SDF 글꼴 준비 대기(2 초)는 모든 상태를 한 번씩 미리 그린 뒤
 * 한 번만. 출력은 <output_dir>/<이름>/<이름>_WxH.png(상태 폴더마다 새 · 빈 폴더), geometry · probes 는 내지 않는다.
 */
namespace WidgetMcpRender
{
	/**
	 * 위젯 하나의 덮어쓰기. 키 = 위젯 이름 · "." (그리는 위젯 자신 — 버튼 칸) · "칸/안쪽 위젯"(칸 안까지).
	 * enabled · button 은 안 먹으면 경고가 아니라 오류다(OVERRIDE_NOT_APPLIED) — 크기 상자(SBox)에 보낸 마우스 이벤트처럼 조용히 아무 일도 없는 길이 있다(uigen 3-1 실측)
	 */
	struct FOverride
	{
		TOptional<bool> bVisible;
		TOptional<float> Percent;
		TOptional<FString> Text;
		TOptional<bool> bEnabled;
		/** 버튼 상태 — hovered · pressed · selected · selected_hovered · selected_pressed(UCommonButtonBase 만) */
		FString Button;
	};

	struct FState
	{
		FString Name;
		TMap<FString, FOverride> Overrides;
	};

	struct FRequest
	{
		FString OutputDir;
		TArray<FIntPoint> Resolutions;
		bool bForceVisible = false;
		TMap<FString, FOverride> Overrides;
		float Scale = 1.f;
		int32 Draws = 2;
		FString Prefix = TEXT("render");
		/** 탐침 — {id, at:[x,y]} 의 LUT 적용 뒤 색(첫 해상도) */
		TArray<TPair<FString, FIntPoint>> Probes;
		/** 상태 묶음 — Overrides · Probes 와 같이 쓰지 않는다. Prefix 는 상태 이름 */
		TArray<FState> States;
	};

	TSharedPtr<FJsonObject> Render(const WidgetMcp::FSettings& Settings, UWidgetBlueprint* WBP, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError);
}
