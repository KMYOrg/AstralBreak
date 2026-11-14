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
 */
namespace WidgetMcpRender
{
	struct FOverride
	{
		TOptional<bool> bVisible;
		TOptional<float> Percent;
		TOptional<FString> Text;
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
	};

	TSharedPtr<FJsonObject> Render(const WidgetMcp::FSettings& Settings, UWidgetBlueprint* WBP, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError);
}
