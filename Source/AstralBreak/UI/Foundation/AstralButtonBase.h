#pragma once

#include "CoreMinimal.h"
#include "CommonButtonBase.h"
#include "AstralButtonBase.generated.h"

class UCommonButtonInternalBase;
class UTextBlock;

/**
 * 버튼 모양 하나의 애셋 클래스 — 상태 그림 일곱은 부모(UCommonButtonStyle)가 담고, 여기에는 그림이 아닌 공용 테마 값만 둔다.
 * 애셋(BS_…)은 uigen 이 만든다(Tools/uigen/config/theme_*.yaml 의 식 → WidgetMcp create_button_style)
 */
UCLASS(Abstract, Blueprintable)
class ASTRALBREAK_API UAstralButtonStyle : public UCommonButtonStyle
{
	GENERATED_BODY()

public:
	/** 눌린 동안 글자를 옮기는 거리(px) */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral")
	FVector2D PressedTextOffset = FVector2D::ZeroVector;
};

/**
 * 프로젝트의 버튼 — 손으로 쓴 클래스 하나이고 모양마다 애셋(WBP + UAstralButtonStyle)만 다르다(설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ②).
 *  - 눌러도 스스로 선택되지 않는다(bSelectable 꺼짐). 선택 모양은 값의 원천이 바뀐 통지에서 SetSelectedLook 으로만 바꾼다.
 *  - 키보드 방향키 초점은 올림이 아니라서(실측) 그 모양을 스스로 입는다 — 스타일의 '기본' 그림을 같은 묶음의 '올림' 그림으로 갈아 끼운다.
 *    엔진 초점 테두리는 이 버튼에서만 끈다(같은 뜻의 표시가 둘이 되지 않게)
 */
UCLASS(Blueprintable)
class ASTRALBREAK_API UAstralButtonBase : public UCommonButtonBase
{
	GENERATED_BODY()

public:
	UAstralButtonBase(const FObjectInitializer& ObjectInitializer);

	/** 버튼 글자 */
	UFUNCTION(BlueprintCallable, Category = "Astral|Button")
	void SetButtonText(const FText& InText);

	const FText& GetButtonText() const { return ButtonText; }

	/** 선택 모양을 켜고 끈다 — 누름 · 소리 · 방송 없이 모양만 */
	UFUNCTION(BlueprintCallable, Category = "Astral|Button")
	void SetSelectedLook(bool bInSelected);

	/** 초점 모양(= 올림 그림)을 입고 있는가 */
	bool IsShowingFocusLook() const { return bShowingFocusLook; }

protected:
	//~UWidget interface
	virtual TSharedRef<SWidget> RebuildWidget() override;
	//~End of UWidget interface

	//~UUserWidget interface
	virtual void NativeOnInitialized() override;
	virtual void NativePreConstruct() override;
	//~End of UUserWidget interface

	//~UCommonButtonBase interface
	virtual UCommonButtonInternalBase* ConstructInternalButton() override;
	virtual void NativeOnCurrentTextStyleChanged() override;
	virtual void NativeOnPressed() override;
	virtual void NativeOnReleased() override;
	//~End of UCommonButtonBase interface

private:
	void HandleFocusIn();
	void HandleFocusOut();

	/** 지금 선택 · 초점에 맞는 '기본' 그림을 안쪽 버튼에 건다(다를 때만) */
	void RefreshRestBrush();

	/** 글자 자리 — 버튼 WBP 가 반드시 갖는다 */
	UPROPERTY(meta = (BindWidget))
	TObjectPtr<UTextBlock> ButtonLabel;

	/** 버튼 글자(놓는 화면이 정한다). 비우면 WBP 에 쓰인 글자 그대로 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Button", meta = (AllowPrivateAccess = "true"))
	FText ButtonText;

	/** 부모가 만드는 안쪽 버튼 — 스타일(상태 그림)이 걸리는 곳 */
	UPROPERTY(Transient)
	TObjectPtr<UCommonButtonInternalBase> InternalButton;

	bool bShowingFocusLook = false;
};
