#pragma once

#include "CoreMinimal.h"
#include "Input/UIActionBindingHandle.h"
#include "UI/Foundation/AstralActivatableWidget.h"
#include "UI/Foundation/AstralUITypes.h"
#include "AstralRootLayout.generated.h"

class AAstralGameState;
class UCommonActivatableWidgetStack;
class UOverlay;

/**
 * 플레이어 한 사람의 화면 전체 — 층 넷을 아래에서 위로 겹친다(Lyra PrimaryGameLayout 의 층을 줄인 것). 만드는 곳은 UAstralUISubsystem 하나.
 *
 *   HUD     맵의 목록(AAstralGameState::ContextHUDWidgets). 보기만 하는 층이라 클릭을 받지 않는다
 *   Debug   개발용 글자 — HUD 위 · 메뉴 아래
 *   Menu    메뉴 화면 스택 · Modal 확인 창 스택 — UAstralUISubsystem::OpenScreen 으로 연다
 *
 * 늘 켜져 있고 Game 입력을 원한다. 라우터는 마지막 화면이 닫혀도 입력 설정을 되돌리지 않으므로(CommonUIActionRouterBase.cpp HandleRootNodeDeactivated)
 * 이 설정이 없으면 메뉴를 닫은 뒤에도 커서가 남고 게임 입력이 막힌다
 */
UCLASS()
class ASTRALBREAK_API UAstralRootLayout : public UAstralActivatableWidget
{
	GENERATED_BODY()

public:
	UAstralRootLayout(const FObjectInitializer& ObjectInitializer);

	//~UCommonActivatableWidget interface
	/**
	 * 늘 Game. 단 화면이 바뀌는 중에는 다음에 설 화면의 설정 — 스택은 위 화면을 먼저 끄고 다음 것을 켜므로, 그 사이 Game 으로 떨어지면
	 * 커서가 숨었다 화면 가운데로 튀고(라우터 ApplyUIInputConfig) 게임 입력이 한순간 열린다
	 */
	virtual TOptional<FUIInputConfig> GetDesiredInputConfig() const override;
	//~End of UCommonActivatableWidget interface

	/** 이 맵의 HUD 층과 여는 액션을 GameState 의 목록대로 다시 짠다. nullptr 이면 비운다 */
	void ApplyContext(const AAstralGameState* GameState);

	/** 층에 화면을 올린다. 같은 종류가 이미 맨 위에 켜져 있으면 그것을 돌려준다 */
	UAstralActivatableWidget* PushScreen(TSubclassOf<UAstralActivatableWidget> ScreenClass, EAstralUILayer Layer);

	/** 그 층의 맨 위 화면 — 없으면 nullptr */
	UAstralActivatableWidget* GetTopScreen(EAstralUILayer Layer) const;

	/** HUD 층에 떠 있는 위젯 — 그 클래스거나 파생. 없으면 nullptr */
	UUserWidget* FindHUDWidget(const UClass* WidgetClass) const;

	/** 개발용 위젯을 Debug 층에 올린다. 같은 종류가 이미 있으면 그것을 돌려준다 */
	UUserWidget* ShowDebugWidget(TSubclassOf<UUserWidget> WidgetClass);

protected:
	//~UUserWidget interface
	virtual void NativeOnInitialized() override;
	//~End of UUserWidget interface

private:
	UUserWidget* AddToOverlay(UOverlay* Overlay, TSubclassOf<UUserWidget> WidgetClass);
	UCommonActivatableWidgetStack* GetStack(EAstralUILayer Layer) const;

	void HandleContextScreenAction(TSoftClassPtr<UAstralActivatableWidget> ScreenClass);

	UPROPERTY(Transient)
	TObjectPtr<UOverlay> HUDLayer;

	UPROPERTY(Transient)
	TObjectPtr<UOverlay> DebugLayer;

	UPROPERTY(Transient)
	TObjectPtr<UCommonActivatableWidgetStack> MenuStack;

	UPROPERTY(Transient)
	TObjectPtr<UCommonActivatableWidgetStack> ModalStack;

	/** 이 맵의 여는 액션들 — 목록을 다시 짤 때 푼다 */
	TArray<FUIActionBindingHandle> ContextBindings;
};
