// 화면 체계 시험(AstralBreak.UI.ScreenStack)이 쓰는 C++ 화면 — WBP 없이 버튼 셋짜리 메뉴 화면(프로젝트 버튼 둘 + 견줄 엔진 버튼 하나)

#pragma once

#include "CoreMinimal.h"
#include "CommonButtonBase.h"
#include "UI/Foundation/AstralActivatableWidget.h"
#include "UI/Foundation/AstralButtonBase.h"
#include "AstralScreenStackTestWidgets.generated.h"

/** 상태마다 색이 다른 스타일 */
UCLASS(MinimalAPI)
class UAstralScreenTestButtonStyle : public UAstralButtonStyle
{
	GENERATED_BODY()

public:
	UAstralScreenTestButtonStyle();
};

/** 크기만 있는 프로젝트 버튼 */
UCLASS(MinimalAPI)
class UAstralScreenTestButton : public UAstralButtonBase
{
	GENERATED_BODY()

public:
	virtual bool Initialize() override;
};

/** 견줄 것 — 엔진 버튼 그대로(초점 테두리가 나온다) */
UCLASS(MinimalAPI)
class UAstralScreenTestPlainButton : public UCommonButtonBase
{
	GENERATED_BODY()

public:
	virtual bool Initialize() override;
};

/** 버튼 셋을 세로로 둔 메뉴 화면 — 첫 초점은 첫 버튼 */
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

	UPROPERTY(Transient)
	TObjectPtr<UAstralScreenTestPlainButton> PlainButton;

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
