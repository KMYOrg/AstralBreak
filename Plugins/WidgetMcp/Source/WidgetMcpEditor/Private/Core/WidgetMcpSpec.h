#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpBrushMaterials.h"
#include "Core/WidgetMcpCommon.h"
#include "Core/WidgetMcpTextMaterials.h"

class UMaterialInterface;
class UPanelSlot;
class UTexture2D;
class UWidget;

/**
 * spec(JSON) ↔ UMG 위젯 하나 — 타입 어휘 · 기본값 · 슬롯 · 스타일 · 글자 (설계 §4-3, Tools/uigen/core/spec.py 와 같은 규칙).
 *
 * 기본값 표는 Tools/uigen/core/spec.py 와 같다(5.7.4 UMG 생성자 기본값). 파이프라인은 정규화한(전부 명시한) spec 을 보내므로
 * 여기 기본값은 대화형 · 부분 spec 일 때만 쓰인다. 브러시는 생략 = 그 위젯 클래스 CDO 의 브러시.
 * 적용은 '목표값을 전부 쓴다'(멱등) — 바뀐 것만 고르는 일은 조정기(WidgetMcpBlueprint)가 보고용으로 한다.
 */
namespace WidgetMcpSpec
{
	/** spec 타입 → UMG 클래스 (어휘 밖이면 nullptr) */
	UClass* ClassForType(const FString& Type);
	/** UMG 위젯 → spec 타입 ("" = 어휘 밖 — export 의 unsupported). 승격 경로 아래 WBP 의 인스턴스는 "UserWidget"(칸) */
	FString TypeForWidget(const UWidget* Widget);

	/** 칸(uigen Phase 3-2) — 다른 화면에 놓이는, 승격된 WBP 하나. spec 은 {type: UserWidget, class: 패키지 경로, props} */
	inline const TCHAR* const UserWidgetType = TEXT("UserWidget");
	/** 목표 위젯의 UMG 클래스 — UserWidget 이면 class 를 풀고(승격 경로 아래 · 컴파일된 WBP 만), 아니면 타입 표. 어휘 밖이면 nullptr + 빈 OutError, 거절이면 OutError */
	UClass* ResolveClass(const FJsonObject& Widget, const FString& Type, FString& OutError);
	/** 부모 타입 → 자식 슬롯 kind ("" = 자식을 못 가짐) */
	FString ChildSlotKind(const FString& ParentType);
	bool IsSingleChild(const FString& Type);
	bool IsPanelType(const FString& Type);

	/** 요청의 assets 맵({asset_id: 텍스처 경로})을 푼 것 + (적용 때만) 조정기가 run 폴더에 준비한 글자 그라데이션 머티리얼 */
	struct FAssets
	{
		TMap<FString, UTexture2D*> Textures;
		TMap<FString, FVector2D> Sizes;
		TMap<FString, FString> IdByPackage;
		/** WidgetMcpTextMaterials::GradientKey → MIC (1b 후속 D — font.gradient). 비어 있으면 그라데이션 글자는 적용 오류 */
		TMap<FString, UMaterialInterface*> TextGradients;
		/** WidgetMcpTextMaterials::GlowKey → MIC (1b 후속 F — font.glow, 외곽선 층 머티리얼). 비어 있으면 빛 글자는 적용 오류 */
		TMap<FString, UMaterialInterface*> TextGlows;
		/** 위젯 id → 원형 닦기 MIC (전투 HUD 동작 — Image brush.wipe). 비어 있으면 닦는 이미지는 적용 오류 */
		TMap<FString, UMaterialInterface*> BrushWipes;
	};
	bool LoadAssets(const TSharedPtr<FJsonObject>& AssetsMap, FAssets& Out, FEditorMcpError& OutError);

	/** 위젯 하나 정규화 — core/spec.py normalize_widget 과 같은 결과(키 · 기본값 · 색 표기) */
	TSharedRef<FJsonObject> NormalizeWidget(const TSharedRef<FJsonObject>& Widget, const FString& ParentType, const FAssets& Assets);
	/** 정규화한 위젯의 font.gradient → Out[키] = (위, 아래) — 조정기가 적용 전에 머티리얼을 준비할 목록 */
	void CollectTextGradients(const FJsonObject& NormalizedWidget, TMap<FString, TPair<FLinearColor, FLinearColor>>& Out);
	/** 정규화한 위젯의 font.glow → Out[키] = (색, 외곽선 em) — 조정기가 적용 전에 빛 머티리얼을 준비할 목록 */
	void CollectTextGlows(const FJsonObject& NormalizedWidget, TMap<FString, WidgetMcpTextMaterials::FGlowSpec>& Out);
	/** 정규화한 위젯의 Image brush.wipe → Out[위젯 id] = 닦기 값(텍스처는 Assets 에서) — 조정기가 적용 전에 머티리얼을 준비할 목록 */
	void CollectBrushWipes(const FJsonObject& NormalizedWidget, const FAssets& Assets, TMap<FString, WidgetMcpBrushMaterials::FRadialWipe>& Out);
	/** WBP 가 담는 것만 — bbox_intent · binding · note 를 빼고 글자는 {value} 만 */
	TSharedRef<FJsonObject> WbpView(const TSharedRef<FJsonObject>& NormalizedWidget);

	/** 적용 전 검사(색 · 열거값 · 에셋 · 타입별 키) — 실패면 false + OutError(사람이 읽을 문장) */
	bool ValidateWidget(const FJsonObject& Widget, const FString& Type, const FAssets& Assets, FString& OutError);

	// ---- 브러시 하나 — 위젯 밖(버튼 스타일 애셋)에서도 같은 어휘로 쓴다
	bool ValidateBrushJson(const FJsonObject& Brush, const FAssets& Assets, const FString& Where, FString& OutError);
	TSharedRef<FJsonObject> NormalizeBrushJson(const TSharedRef<FJsonObject>& Brush, const FAssets& Assets);
	bool BrushFrom(const FJsonObject& Brush, const FAssets& Assets, FSlateBrush& Out, FString& OutError);
	TSharedRef<FJsonObject> BrushTo(const FSlateBrush& Brush, const FAssets* Assets, const FString& Where, TArray<TSharedPtr<FJsonValue>>& OutUnsupported);

	bool ApplySlot(UPanelSlot* Slot, const FJsonObject& SlotJson, FString& OutError);
	bool ApplyWidget(UWidget* Widget, const FJsonObject& WidgetJson, const FAssets& Assets, FString& OutError);

	/** 슬롯 → JSON(kind 포함). 루트 · 어휘 밖 슬롯이면 null */
	TSharedPtr<FJsonObject> ExportSlot(const UPanelSlot* Slot);
	/** 위젯 속성(visibility · style · text · font · justification)을 Out 에 쓴다. Assets 가 있으면 텍스처를 asset_id 로, 없으면 패키지 경로로 */
	void ExportWidgetProps(const UWidget* Widget, const FAssets* Assets, const TSharedRef<FJsonObject>& Out, TArray<TSharedPtr<FJsonValue>>& OutUnsupported);
	/** 이 위젯이 쓰는 텍스처(브러시 리소스) */
	void CollectTextures(const UWidget* Widget, TArray<UTexture2D*>& Out);
}
