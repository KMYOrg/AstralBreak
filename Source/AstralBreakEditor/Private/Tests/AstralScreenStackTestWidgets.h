// 화면 체계 시험(AstralBreak.UI.ScreenStack)이 쓰는 C++ 화면 — WBP 없이 버튼 둘짜리 메뉴 화면

#pragma once

#include "CoreMinimal.h"
#include "CommonButtonBase.h"
#include "UI/Foundation/AstralActivatableWidget.h"
#include "AstralScreenStackTestWidgets.generated.h"

/** 크기만 있는 버튼 */
UCLASS(MinimalAPI)
class UAstralScreenTestButton : public UCommonButtonBase
{
	GENERATED_BODY()

public:
	virtual bool Initialize() override;

	/** 안쪽 SButton — UCommonButtonInternalBase 는 크기 상자(SBox)로 한 번 더 감싼다 */
	TSharedPtr<SWidget> GetInnerSlateButton() const;
};

/** 버튼 둘을 세로로 둔 메뉴 화면 — 첫 초점은 첫 버튼 */
UCLASS(MinimalAPI)
class UAstralScreenTestMenu : public UAstralActivatableWidget
{
	GENERATED_BODY()

public:
	UAstralScreenTestMenu(const FObjectInitializer& ObjectInitializer);

	UPROPERTY(Transient)
	TObjectPtr<UAstralScreenTestButton> FirstButton;

	UPROPERTY(Transient)
	TObjectPtr<UAstralScreenTestButton> SecondButton;

protected:
	virtual void NativeOnInitialized() override;
	virtual UWidget* NativeGetDesiredFocusTarget() const override;
};

/** 위에 겹쳐 여는 두 번째 메뉴 화면 */
UCLASS(MinimalAPI)
class UAstralScreenTestSubMenu : public UAstralScreenTestMenu
{
	GENERATED_BODY()
};

/** Modal 층에 여는 확인 창 */
UCLASS(MinimalAPI)
class UAstralScreenTestDialog : public UAstralScreenTestMenu
{
	GENERATED_BODY()
};
