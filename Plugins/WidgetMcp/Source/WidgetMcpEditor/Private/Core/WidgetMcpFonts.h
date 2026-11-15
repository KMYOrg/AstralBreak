#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"

/**
 * import_font_family — 폰트 파일(TTF/OTF) → UFontFace 여러 개 + 컴포지트 UFont 하나 (설계 §11 '1b 착수 때 정한 것' · 1b-3).
 *
 * 엔진 UFontFileImportFactory::FactoryCreateBinary(EditorFactories.cpp:5077)와 같은 순서를 대화창 없이 밟는다:
 *   UFontFace — SourceFilename · FontFaceData->SetData(파일 바이트) · CacheSubFaces (Hinting · LoadingPolicy 는 기본값)
 *   UFont     — FontCacheType = Runtime(UFontFactory 와 같음) · CompositeFont.DefaultTypeface.Fonts = [{Name = 타입페이스, Font = FFontData(Face)}]
 * 타입페이스 이름은 spec 굵기 어휘가 고르는 이름(WidgetMcpSpec Weights — Regular · Bold · Light · Italic · Bold Italic)만 받는다.
 * 그래야 spec font.family = 이 UFont 경로, font.weight = regular/bold 가 그대로 그 타입페이스를 고른다.
 *
 * 안전장치: 대상 폴더는 [WidgetMcp] WidgetFontOutputPaths 아래 하위 폴더만(접두 자체는 거부) · 원본 파일은 WidgetImportSourceRoots 안 ·
 * 덮어쓰기 거부(이름이 하나라도 있으면 아무것도 안 만듦) · 전역 더티 비교(WidgetFontOutputPaths 밖이 더티가 되면 만든 것을 내리고 거부).
 * save(기본 true) — 프로젝트 폰트는 run 산출물이 아니라 커밋 대상이라 이 Tool 이 직접 저장한다.
 */
namespace WidgetMcpFonts
{
	struct FFace
	{
		FString File;
		FString Typeface;
	};

	struct FRequest
	{
		FString DestFolder;   // "/Game/UI/Fonts/Pretendard"
		FString Family;       // "Pretendard" → F_Pretendard · FF_Pretendard_<Typeface>
		TArray<FFace> Faces;
		bool bSave = true;
		/** 1b 후속 F — UFontFace bEnableDistanceFieldRendering(거리장 SDF 글꼴 — 글자 빛 font.glow 가 쓴다). 프로젝트 설정
		 *  UserInterfaceSettings.bEnableDistanceFieldFontRasterization · CVar UI.SlateSDFText.RasterizationMode 가 켜져 있어야 실제로 SDF 로 그린다 */
		bool bDistanceField = false;
	};

	/** spec 굵기 어휘가 고르는 타입페이스 이름 */
	const TArray<FString>& AllowedTypefaces();

	TSharedPtr<FJsonObject> ImportFamily(const WidgetMcp::FSettings& Settings, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError);
}
