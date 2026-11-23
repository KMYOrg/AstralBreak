#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UMaterialInterface;
class UTexture2D;

/**
 * 이미지 브러시 머티리얼 — 원형 닦기 (전투 HUD 동작 11-23 — spec Image style.brush.wipe{kind radial, mode, center, track_alpha} + style.percent).
 *
 * 텍스처를 중심에서 본 각도로 닦아 남은 비율을 보인다(체인 남은 시간 고리). 부모 M_RadialWipe 하나 + 위젯마다 MI_RadialWipe_<위젯>,
 * 글자 머티리얼(WidgetMcpTextMaterials)과 같이 WBP 의 run 폴더에만 만든다 — 저장(save_widget_run) · 폐기 · 승격(promote_widget)이 같이 간다.
 * 런타임은 UImage::GetDynamicMaterial() 의 "Percent" 를 움직인다(생성 베이스 setter — Tools/uigen/core/cppgen.py progress_image).
 *
 * 닦기 식은 Tools/uigen/gen/radial.py wipe_factor 와 같다(오프라인 합성 · 진단이 같은 그림을 본다): 12시 = 0 · 시계 방향 +,
 * clockwise = 12시에서 시계 방향으로 (1 − Percent) 바퀴를 지움, mirror = 12시에서 좌우로 같이 (1 − Percent) 반 바퀴씩. 끝은 부호 거리(px) ± 0.5.
 * Percent 1 이상 = 전부(12시 이음매 없음), 0 이하 = 전부 TrackAlpha(지나간 자리에 남기는 흔적).
 * [소스] SlateElementPixelShader.usf:198-206 — Slate 머티리얼은 정점 색(브러시 틴트)을 곱하지 않는다 → 머티리얼 안에서 곱한다.
 */
namespace WidgetMcpBrushMaterials
{
	struct FRadialWipe
	{
		UTexture2D* Texture = nullptr;
		float Percent = 1.f;
		/** 닦는 중심 · 그리는 크기(브러시 image_size) — px */
		FVector2D Center = FVector2D::ZeroVector;
		FVector2D Size = FVector2D(32.0, 32.0);
		bool bMirror = false;
		float TrackAlpha = 0.f;
	};

	/** Folder(= WBP 의 run 폴더) 안에 부모 · 위젯마다 MIC 를 찾거나 만들고 값을 쓴다 → Out[위젯 id]. 실패면 false + OutError */
	bool Prepare(const FString& Folder, const TMap<FString, FRadialWipe>& Wipes, TMap<FString, UMaterialInterface*>& Out, FString& OutError);

	/** 브러시 리소스가 이 모듈이 만든 닦기 MIC(또는 그것으로 만든 동적 머티리얼)면 true + 값 */
	bool ReadRadialWipe(const UObject* BrushResource, FRadialWipe& Out);

	/** 런타임 · 렌더 덮어쓰기가 움직이는 스칼라 파라미터 이름 */
	FName PercentParameter();
}
