#pragma once

#include "CoreMinimal.h"
#include "CommonActivatableWidget.h"
#include "AstralActivatableWidget.generated.h"

/** 이 위젯이 켜져 있는 동안의 입력 — Lyra ELyraWidgetInputMode 와 같은 꼴 */
UENUM(BlueprintType)
enum class EAstralWidgetInputMode : uint8
{
	/** 따로 정하지 않음 — 바깥(부모) 화면의 것을 따른다 */
	Default,
	/** 게임과 메뉴가 같이 받음 */
	GameAndMenu,
	/** 게임만 */
	Game,
	/** 메뉴만 — 커서가 나오고 게임 입력이 막힌다 */
	Menu
};

/**
 * 켜지고 꺼지는 화면의 베이스 — 켜져 있는 동안의 입력 모드를 스스로 말하고, 뒤로 액션(UI.Action.Back)에 닫힌다.
 * 커서 · 게임 입력 막기 · 눌린 키 비우기 · 첫 초점과 되돌리기는 CommonUI 라우터가 한다(설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ③).
 * 화면을 여는 길은 UAstralUISubsystem::OpenScreen 하나다. uigen 이 만드는 조작 화면의 생성 베이스도 이 클래스를 부모로 쓴다(Phase 3-3)
 */
UCLASS(Abstract, Blueprintable)
class ASTRALBREAK_API UAstralActivatableWidget : public UCommonActivatableWidget
{
	GENERATED_BODY()

public:
	UAstralActivatableWidget(const FObjectInitializer& ObjectInitializer);

	//~UCommonActivatableWidget interface
	virtual TOptional<FUIInputConfig> GetDesiredInputConfig() const override;
	//~End of UCommonActivatableWidget interface

	/**
	 * Modal 층에 오를 때 켠다 — 라우터가 이 화면을 따로 선 뿌리로 보므로 아래(Menu 층) 화면은 켜져 있어도 액션을 못 받는다.
	 * 안 켜면 Menu 화면과 Modal 화면이 형제가 되고, 형제는 먼저 열린 쪽이 키를 먼저 받는다(UIActionRouterTypes.cpp FActivatableTreeNode::ProcessNormalInput).
	 * 층에 올리기 전(Slate 위젯이 만들어지기 전)에 불러야 한다
	 */
	void SetTreatedAsModal(bool bInModal);

protected:
	//~UUserWidget interface
	virtual void NativeOnInitialized() override;
	//~End of UUserWidget interface

	/** 뒤로 액션이 이 화면에 왔다. 기본은 닫기(끄기) — 층이 위젯을 걷는다 */
	virtual void HandleBackActionTriggered();

	/** 켜져 있는 동안의 입력 모드 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Input")
	EAstralWidgetInputMode InputConfig = EAstralWidgetInputMode::Default;

	/** 게임이 입력을 받을 때의 마우스 — 프로젝트 기본값(DefaultInput.ini DefaultViewportMouseCaptureMode)과 같게 둔다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Input")
	EMouseCaptureMode GameMouseCaptureMode = EMouseCaptureMode::CapturePermanently_IncludingInitialMouseDown;

	/** 뒤로 액션에 닫히는가 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Input")
	bool bClosesOnBackAction = true;
};
