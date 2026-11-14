#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"

class UTexture2D;

/**
 * import_ui_textures — PNG 를 Interchange 로 임포트하고 UI 텍스처 설정을 단다 (설계 §6 · §12-1 '텍스처 임포트 경로 — 1a 첫 작업').
 *
 * 경로: UInterchangeManager::ImportAssetWithResult(동기 — InterchangeManager.cpp:1720-1726) + 기본 'Textures' 스택의 파이프라인
 * (BaseEngine.ini → /Interchange/Pipelines/DefaultTexturePipeline)을 트랜지언트로 복제해 고친 것.
 *   - bAllowNonPowerOfTwo = true   기본값 false 면 200×50 같은 UI 텍스처를 걸러 낸다(InterchangeGenericTexturePipeline.h:70)
 *   - bDetectNormalMapTexture = false · bImportUDIMs = false · AssetName = 요청 이름
 * 임포트 뒤 압축 · 그룹 · 밉 · 스트리밍 · sRGB 를 직접 넣고 PostEditChange → 텍스처 빌드를 끝까지 기다린다(렌더 전에 써야 하므로).
 * 저장하지 않는다 — 저장은 save_widget_run(finalize)만.
 */
namespace WidgetMcpTextures
{
	struct FRequest
	{
		FString File;
		FString Name;
		FString Compression = TEXT("TC_EditorIcon");
		FString LodGroup = TEXT("TEXTUREGROUP_UI");
		FString MipGen = TEXT("TMGS_NoMipmaps");
		bool bNeverStream = true;
		bool bSRGB = true;
	};

	TSharedPtr<FJsonObject> Import(const WidgetMcp::FSettings& Settings, const FString& DestFolder, const TArray<FRequest>& Requests,
		FEditorMcpContext& Context, FEditorMcpError& OutError);

	/** 텍스처 설정 — verify 의 '텍스처 설정' 게이트가 manifest 와 비교한다 */
	TSharedRef<FJsonObject> Describe(const UTexture2D* Texture);
}
