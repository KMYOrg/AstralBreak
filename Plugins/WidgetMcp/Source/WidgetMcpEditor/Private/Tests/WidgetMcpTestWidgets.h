#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
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

/** 부모로 쓰면 거부돼야 하는 Abstract 베이스(생성 베이스 ViewBase 흉내) */
UCLASS(Abstract, HideDropdown)
class UWidgetMcpTestAbstractHud : public UUserWidget
{
	GENERATED_BODY()
};
