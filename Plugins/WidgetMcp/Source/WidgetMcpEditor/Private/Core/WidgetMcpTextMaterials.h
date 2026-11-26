#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UMaterialInterface;

/**
 * 글자 세로 그라데이션 머티리얼 (1b 후속 D — spec font.gradient{top_color, bottom_color}).
 *
 * [소스] SlateCore ElementBatcher.cpp:3780-3790 — 폰트 머티리얼이 있으면 글자 사각형마다 줄 기준 UV(U = 글자 순번 / 글자 수,
 * V = 줄 위 0 → 아래 1)를 넘긴다 — [실측 D] 머티리얼 TexCoord[0] 으로 읽힌다. 그래서 UI 도메인 머티리얼 하나(V 로 위 색 → 아래 색 Lerp)로
 * 줄 전체에 이어지는 그라데이션이 된다. V 는 줄 상자 기준이라 VTop · VBottom(기본 0.25 · 0.80 — 글자 몸통 범위 실측)으로 다시 편다.
 * [실측 D] 새로 만든 머티리얼은 PostEditChange 만으로는 Slate 셰이더가 없어 그 배치가 빠졌다(외곽선만 보임) → ForceRecompileForRendering + 컴파일 대기.
 *
 * 애셋은 WBP 와 같은 run 폴더(/Game/_AutoGen/<run_id>/)에만 만든다 — 부모 M_TextGradient 하나 + 색 쌍마다 MI_TextGradient_<키>.
 * 조정기(WidgetMcpBlueprint)가 적용 직전에 Prepare 로 만들고(미리보기 · 검사에서는 만들지 않음), 적용은 키로 찾아 FontMaterial 에 넣는다.
 * 저장은 save_widget_run(run 폴더 일괄) · 폐기는 discard_run_packages 가 같이 한다. 그라데이션 색의 알파는 쓰지 않는다(불투명도는 font.color 알파).
 */
namespace WidgetMcpTextMaterials
{
	/** 정규화한 #RRGGBBAA 두 개 → 키 "RRGGBBAA_RRGGBBAA" */
	FString GradientKey(const FString& TopHex, const FString& BottomHex);

	/** Folder(= WBP 의 run 폴더) 안에 부모 · 키마다 MIC 를 찾거나 만든다 → Out[키]. 실패면 false + OutError */
	bool Prepare(const FString& Folder, const TMap<FString, TPair<FLinearColor, FLinearColor>>& Gradients, TMap<FString, UMaterialInterface*>& Out, FString& OutError);

	/** 진단 — 경로 · UI 도메인 · 셰이더 맵 유무 · 컴파일 완료 · 오류 수 (apply 결과 text_materials[]) */
	TSharedRef<FJsonObject> Describe(const UMaterialInterface* Material);

	/** FontMaterial 이 이 모듈이 만든 그라데이션 MIC 면 true + 위 · 아래 색 */
	bool ReadGradient(const UObject* FontMaterial, FLinearColor& OutTop, FLinearColor& OutBottom);

	// ---- 글자 빛 (1b 후속 F — spec font.glow{size, color}) ---------------------------------------------------------------
	// [소스] SlateElementPixelShader.usf:316-335 · ElementBatcher.cpp:3436-3460 · FontCache.cpp:1346-1349 — 거리장(SDF) 글꼴이면 외곽선 층의
	// 거리장 바깥 퍼짐이 외곽선 크기만큼 늘고, 글꼴 · 외곽선 머티리얼은 FontSignedDistance 노드(x = 외곽선 경계 기준 em 부호 거리, 안 = +)를 받는다.
	// 비스텐실(기본)이면 최종 알파 = 머티리얼 불투명도 × 거리장 불투명도(외곽선 경계에서 0). 그래서 외곽선 층을 M_TextGlow 로 그리면
	// 불투명도 = GlowAlpha × saturate(x / OutlineEm)^Gamma — 획 가장자리(x = OutlineEm)에서 GlowAlpha, 외곽선 경계에서 0 으로 부드럽게 번진다.
	// 비트맵 글꼴이면 x = 0 이라 빛이 안 보인다(오류 아님 — 파이프라인이 SDF 글꼴로 바꾼다). OutlineEm = 외곽선 px / (글자 크기 × 96/72).

	struct FGlowSpec
	{
		FLinearColor Color = FLinearColor::White;   // 알파 = GlowAlpha
		float OutlineEm = 0.1f;
	};

	/** 정규화한 #RRGGBBAA · 외곽선 px · 글자 크기 → 키 "RRGGBBAA_S<px>_F<크기×10>" */
	FString GlowKey(const FString& ColorHex, int32 SizePx, double FontSize);
	/** 외곽선 px / (글자 크기 pt × 96 / 72) — FontCache.cpp:1346 의 EmOutlineSize(FontScale 은 분자 · 분모에서 같이 빠짐) */
	float OutlineEmFor(int32 SizePx, double FontSize);

	/** Folder 안에 부모 M_TextGlow · 키마다 MI_TextGlow_<키> 를 찾거나 만든다 → Out[키]. 실패면 false + OutError */
	bool PrepareGlows(const FString& Folder, const TMap<FString, FGlowSpec>& Glows, TMap<FString, UMaterialInterface*>& Out, FString& OutError);

	/** OutlineMaterial 이 이 모듈이 만든 빛 MIC 면 true + 색(알파 = GlowAlpha) */
	bool ReadGlow(const UObject* OutlineMaterial, FLinearColor& OutColor);
}
