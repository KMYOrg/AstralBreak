#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"

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
	/** UMG 위젯 → spec 타입 ("" = 어휘 밖 — export 의 unsupported) */
	FString TypeForWidget(const UWidget* Widget);
	/** 부모 타입 → 자식 슬롯 kind ("" = 자식을 못 가짐) */
	FString ChildSlotKind(const FString& ParentType);
	bool IsSingleChild(const FString& Type);
	bool IsPanelType(const FString& Type);

	/** 요청의 assets 맵({asset_id: 텍스처 경로})을 푼 것 */
	struct FAssets
	{
		TMap<FString, UTexture2D*> Textures;
		TMap<FString, FVector2D> Sizes;
		TMap<FString, FString> IdByPackage;
	};
	bool LoadAssets(const TSharedPtr<FJsonObject>& AssetsMap, FAssets& Out, FEditorMcpError& OutError);

	/** 위젯 하나 정규화 — core/spec.py normalize_widget 과 같은 결과(키 · 기본값 · 색 표기) */
	TSharedRef<FJsonObject> NormalizeWidget(const TSharedRef<FJsonObject>& Widget, const FString& ParentType, const FAssets& Assets);
	/** WBP 가 담는 것만 — bbox_intent · binding · note 를 빼고 글자는 {value} 만 */
	TSharedRef<FJsonObject> WbpView(const TSharedRef<FJsonObject>& NormalizedWidget);

	/** 적용 전 검사(색 · 열거값 · 에셋 · 타입별 키) — 실패면 false + OutError(사람이 읽을 문장) */
	bool ValidateWidget(const FJsonObject& Widget, const FString& Type, const FAssets& Assets, FString& OutError);

	bool ApplySlot(UPanelSlot* Slot, const FJsonObject& SlotJson, FString& OutError);
	bool ApplyWidget(UWidget* Widget, const FJsonObject& WidgetJson, const FAssets& Assets, FString& OutError);

	/** 슬롯 → JSON(kind 포함). 루트 · 어휘 밖 슬롯이면 null */
	TSharedPtr<FJsonObject> ExportSlot(const UPanelSlot* Slot);
	/** 위젯 속성(visibility · style · text · font · justification)을 Out 에 쓴다. Assets 가 있으면 텍스처를 asset_id 로, 없으면 패키지 경로로 */
	void ExportWidgetProps(const UWidget* Widget, const FAssets* Assets, const TSharedRef<FJsonObject>& Out, TArray<TSharedPtr<FJsonValue>>& OutUnsupported);
	/** 이 위젯이 쓰는 텍스처(브러시 리소스) */
	void CollectTextures(const UWidget* Widget, TArray<UTexture2D*>& Out);
}
