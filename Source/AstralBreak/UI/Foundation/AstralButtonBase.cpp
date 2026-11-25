#include "AstralButtonBase.h"

#include "Components/TextBlock.h"
#include "Layout/Children.h"
#include "Styling/SlateTypes.h"
#include "Widgets/SCompoundWidget.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralButtonBase)

namespace AstralButtonPrivate
{
	/**
	 * 안쪽 버튼을 감싸 엔진 초점 테두리를 막는다 — Slate 는 초점을 받은 위젯에서 바깥으로 올라가며 처음 답한 위젯의 답을 쓴다
	 * (SlateApplication.cpp SetUserFocus 의 OnQueryShowFocus). 초점 모양을 스스로 그리는 이 버튼에만 걸리고 다른 화면 · 위젯은 그대로다
	 */
	class SFocusRingBlocker : public SCompoundWidget
	{
	public:
		SLATE_BEGIN_ARGS(SFocusRingBlocker) { _Visibility = EVisibility::SelfHitTestInvisible; }
			SLATE_DEFAULT_SLOT(FArguments, Content)
		SLATE_END_ARGS()

		void Construct(const FArguments& InArgs)
		{
			ChildSlot[InArgs._Content.Widget];
		}

		virtual TOptional<bool> OnQueryShowFocus(const EFocusCause InFocusCause) const override
		{
			return false;
		}
	};
}

UAstralButtonBase::UAstralButtonBase(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// 누르면 부모가 SetIsSelected(!bSelected) 를 부르지만 bSelectable 이 꺼져 있으면 아무 일도 없다 — 요청과 모양을 가른다
	bSelectable = false;
	// 선택된(예: 준비된) 버튼을 다시 눌러 풀 수 있어야 한다
	bInteractableWhenSelected = true;
}

void UAstralButtonBase::SetButtonText(const FText& InText)
{
	ButtonText = InText;
	if (ButtonLabel)
	{
		ButtonLabel->SetText(ButtonText);
	}
}

void UAstralButtonBase::SetSelectedLook(bool bInSelected)
{
	if (GetSelected() != bInSelected)
	{
		SetSelectedInternal(bInSelected, /*bAllowSound*/ false, /*bBroadcast*/ false);
	}
}

TSharedRef<SWidget> UAstralButtonBase::RebuildWidget()
{
	return SNew(AstralButtonPrivate::SFocusRingBlocker)
		[
			Super::RebuildWidget()
		];
}

void UAstralButtonBase::NativeOnInitialized()
{
	Super::NativeOnInitialized();
	OnFocusReceived().AddUObject(this, &ThisClass::HandleFocusIn);
	OnFocusLost().AddUObject(this, &ThisClass::HandleFocusOut);
}

void UAstralButtonBase::NativePreConstruct()
{
	Super::NativePreConstruct();
	if (ButtonLabel && !ButtonText.IsEmpty())
	{
		ButtonLabel->SetText(ButtonText);
	}
}

UCommonButtonInternalBase* UAstralButtonBase::ConstructInternalButton()
{
	InternalButton = Super::ConstructInternalButton();
	return InternalButton;
}

void UAstralButtonBase::NativeOnCurrentTextStyleChanged()
{
	Super::NativeOnCurrentTextStyleChanged();
	// 부모는 선택 · 켜짐이 바뀔 때마다 스타일을 통째로 다시 걸고 이 함수를 부른다(CommonButtonBase.cpp SetButtonStyle) — 초점 모양을 다시 입는다
	RefreshRestBrush();
}

void UAstralButtonBase::NativeOnPressed()
{
	Super::NativeOnPressed();
	const UAstralButtonStyle* AstralStyle = Cast<UAstralButtonStyle>(GetStyle());
	if (ButtonLabel && AstralStyle)
	{
		ButtonLabel->SetRenderTranslation(AstralStyle->PressedTextOffset);
	}
}

void UAstralButtonBase::NativeOnReleased()
{
	if (ButtonLabel)
	{
		ButtonLabel->SetRenderTranslation(FVector2D::ZeroVector);
	}
	Super::NativeOnReleased();
}

void UAstralButtonBase::HandleFocusIn()
{
	// 초점이 온 까닭 — 방향키(Navigation)로 온 초점만 모양을 입는다(엔진 초점 테두리의 기본 규칙과 같다). 마우스로 누른 버튼 · 화면이 열리며 받은 첫 초점은 그대로
	const TSharedPtr<SWidget> Box = InternalButton ? InternalButton->GetCachedWidget() : nullptr;
	FChildren* Children = Box ? Box->GetChildren() : nullptr;
	TOptional<EFocusCause> Cause;
	if (Children && Children->Num() > 0)
	{
		Cause = Children->GetChildAt(0)->HasAnyUserFocus();      // UCommonButtonInternalBase 의 Slate 는 크기 상자이고 초점은 그 자식(SCommonButton)이 받는다
	}
	bShowingFocusLook = Cause.IsSet() && Cause.GetValue() == EFocusCause::Navigation;
	RefreshRestBrush();
}

void UAstralButtonBase::HandleFocusOut()
{
	bShowingFocusLook = false;
	RefreshRestBrush();
}

void UAstralButtonBase::RefreshRestBrush()
{
	const UCommonButtonStyle* ButtonStyle = GetStyle();
	if (!InternalButton || !ButtonStyle || ButtonStyle->bSingleMaterial)
	{
		return;
	}
	FSlateBrush Rest;
	if (GetSelected())
	{
		bShowingFocusLook ? ButtonStyle->GetSelectedHoveredBrush(Rest) : ButtonStyle->GetSelectedBaseBrush(Rest);
	}
	else
	{
		bShowingFocusLook ? ButtonStyle->GetNormalHoveredBrush(Rest) : ButtonStyle->GetNormalBaseBrush(Rest);
	}
	FButtonStyle Look = InternalButton->GetStyle();
	if (!(Look.Normal == Rest))
	{
		Look.Normal = Rest;
		InternalButton->SetStyle(Look);
	}
}
