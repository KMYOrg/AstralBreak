#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "CommonButtonBase.h"
#include "Components/TextBlock.h"
#include "WidgetMcpTestWidgets.generated.h"

class UProgressBar;
class UTextBlock;

/**
 * WidgetMcp 자동 시험 전용 부모 클래스 — 게임 코드는 쓰지 않는다(드롭다운에서 숨김).
 * 바인딩 계약: Gauge(ProgressBar, 필수) · Label(TextBlock, 선택). codegen 이 만드는 ViewBase/스텁과 같은 모양을 흉내 낸다.
 */
UCLASS(HideDropdown, meta = (DisplayName = "WidgetMcp Test HUD (automation only)"))
class UWidgetMcpTestHud : public UUserWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(meta = (BindWidget))
	TObjectPtr<UProgressBar> Gauge;

	UPROPERTY(meta = (BindWidgetOptional))
	TObjectPtr<UTextBlock> Label;
};

/** 버튼 스타일 부모 흉내 — 그림이 아닌 값 하나를 더한다(uigen Phase 3-2) */
UCLASS(Abstract, HideDropdown)
class UWidgetMcpTestButtonStyle : public UCommonButtonStyle
{
	GENERATED_BODY()

public:
	UPROPERTY(EditDefaultsOnly, Category = "Test")
	FVector2D PressedTextOffset = FVector2D::ZeroVector;
};

/** 버튼 칸의 손으로 쓴 부모 흉내 — 글자 값(ButtonText)을 놓는 화면이 정한다 */
UCLASS(HideDropdown, meta = (DisplayName = "WidgetMcp Test Button (automation only)"))
class UWidgetMcpTestButton : public UCommonButtonBase
{
	GENERATED_BODY()

public:
	UPROPERTY(meta = (BindWidget))
	TObjectPtr<UTextBlock> ButtonLabel;

	UPROPERTY(EditAnywhere, Category = "Test")
	FText ButtonText;

	UWidgetMcpTestButton(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer) { bInteractableWhenSelected = true; }

protected:
	virtual void NativePreConstruct() override
	{
		Super::NativePreConstruct();
		if (ButtonLabel && !ButtonText.IsEmpty()) { ButtonLabel->SetText(ButtonText); }
	}
};

/** 부모로 쓰면 거부돼야 하는 Abstract 베이스(생성 베이스 ViewBase 흉내) */
UCLASS(Abstract, HideDropdown)
class UWidgetMcpTestAbstractHud : public UUserWidget
{
	GENERATED_BODY()
};
