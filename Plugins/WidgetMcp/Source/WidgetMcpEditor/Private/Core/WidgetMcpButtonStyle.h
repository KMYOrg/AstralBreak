#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"
#include "Core/WidgetMcpSpec.h"

class UCommonButtonStyle;
class UTexture2D;
class UWidgetBlueprint;

/**
 * 버튼 스타일 애셋 — CommonButton 의 상태 그림 일곱을 담는 UCommonButtonStyle 파생 블루프린트 (설계 §11 'Phase 3 설계' ②).
 *
 * CommonButton 은 스타일을 '클래스 기본 객체'에서만 읽고 가상 함수가 아니다(CommonButtonBase.cpp BuildStyles) → 상태 그림은 클래스 애셋이어야 한다.
 * 일곱을 다 채워야 한다 — 특히 Disabled 브러시가 NoDrawType 이면 Slate 가 기본 그림에 흐림 효과를 쓴다(SButton::GetShowDisabledEffect).
 * 그림이 아닌 값(눌린 글자 이동 등)은 부모 클래스(프로젝트의 UCommonButtonStyle 파생)가 더한 속성만 props 로 쓴다 — 플러그인은 프로젝트 클래스를 모른다.
 */
namespace WidgetMcpButtonStyle
{
	struct FRequest
	{
		FString AssetPath;
		FString ParentClass;
		TSharedPtr<FJsonObject> Brushes;
		TSharedPtr<FJsonObject> Props;
		FIntPoint MinSize = FIntPoint::ZeroValue;
		/** 이 run 에서 이미 만든 스타일을 새 값으로 다시 쓴다(에셋이 바뀐 재시도). 다른 종류의 애셋이 있으면 언제나 거절 */
		bool bReplace = false;
	};

	/** 상태 일곱의 이름 — spec · 도구 · 렌더 덮어쓰기가 같이 쓴다 */
	const TArray<FString>& BrushNames();

	TSharedPtr<FJsonObject> Create(const WidgetMcp::FSettings& Settings, const FRequest& Request, const WidgetMcpSpec::FAssets& Assets, FEditorMcpContext& Context, FEditorMcpError& OutError);

	/** 스타일 클래스 → {class, parent_class, brushes{일곱}, min_size, props} */
	TSharedRef<FJsonObject> Describe(const UCommonButtonStyle* Style, const WidgetMcpSpec::FAssets* Assets, TArray<TSharedPtr<FJsonValue>>& OutUnsupported);
	void CollectTextures(const UCommonButtonStyle* Style, TArray<UTexture2D*>& Out);

	// ---- WBP 의 클래스 기본값(버튼 WBP 만 — 부모가 UCommonButtonBase) ------------------------------------------------
	bool IsButtonBlueprint(const UWidgetBlueprint* WBP);
	/** 지금 WBP 에 걸린 스타일(없으면 nullptr) */
	const UCommonButtonStyle* StyleOf(const UWidgetBlueprint* WBP);
	/** {"Style": 패키지 경로} — 버튼 WBP 가 아니거나 스타일이 없으면 빈 객체 */
	TSharedRef<FJsonObject> ExportDefaults(const UWidgetBlueprint* WBP);
	/** spec defaults 검사 → 걸 스타일 클래스(defaults 가 없으면 nullptr). 허용하는 것은 버튼 WBP 의 Style 하나이고, 같은 폴더나 승격 경로의 것만 */
	bool ResolveDefaults(const WidgetMcp::FSettings& Settings, const UWidgetBlueprint* WBP, const TSharedPtr<FJsonObject>& Defaults, UClass*& OutStyle, FString& OutError);
	bool ApplyStyle(UWidgetBlueprint* WBP, UClass* StyleClass);
}
