#include "AstralScreenStackTestWidgets.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/SizeBox.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralScreenStackTestWidgets)

namespace AstralScreenTest
{
	/** WBP 가 하는 일(루트 위젯)을 대신한다 — 부모의 Initialize 가 이 루트를 안쪽 버튼으로 감싼다 */
	void BuildRoot(UUserWidget& Button)
	{
		if (!Button.WidgetTree && !Button.HasAnyFlags(RF_ClassDefaultObject))
		{
			Button.WidgetTree = NewObject<UWidgetTree>(&Button, TEXT("WidgetTree"), RF_Transient);
			USizeBox* Box = Button.WidgetTree->ConstructWidget<USizeBox>();
			Box->SetWidthOverride(240.f);
			Box->SetHeightOverride(60.f);
			Button.WidgetTree->RootWidget = Box;
		}
	}
}

UAstralScreenTestButtonStyle::UAstralScreenTestButtonStyle()
{
	const auto Colored = [](const FLinearColor& Color)
	{
		FSlateBrush Brush;
		Brush.DrawAs = ESlateBrushDrawType::Image;
		Brush.TintColor = Color;
		return Brush;
	};
	NormalBase = Colored(FLinearColor(0.1f, 0.1f, 0.1f));
	NormalHovered = Colored(FLinearColor(0.2f, 0.2f, 0.1f));
	NormalPressed = Colored(FLinearColor(0.05f, 0.05f, 0.05f));
	SelectedBase = Colored(FLinearColor(0.4f, 0.4f, 0.3f));
	SelectedHovered = Colored(FLinearColor(0.5f, 0.5f, 0.4f));
	SelectedPressed = Colored(FLinearColor(0.3f, 0.3f, 0.2f));
	Disabled = Colored(FLinearColor(0.02f, 0.02f, 0.02f));
}

bool UAstralScreenTestButton::Initialize()
{
	AstralScreenTest::BuildRoot(*this);
	const bool bInitializedNow = Super::Initialize();
	if (bInitializedNow && !HasAnyFlags(RF_ClassDefaultObject))
	{
		SetStyle(UAstralScreenTestButtonStyle::StaticClass());
	}
	return bInitializedNow;
}

bool UAstralScreenTestPlainButton::Initialize()
{
	AstralScreenTest::BuildRoot(*this);
	return Super::Initialize();
}

UAstralScreenTestMenu::UAstralScreenTestMenu(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InputConfig = EAstralWidgetInputMode::Menu;
}

void UAstralScreenTestMenu::NativeOnInitialized()
{
	UOverlay* Root = WidgetTree->ConstructWidget<UOverlay>();
	WidgetTree->RootWidget = Root;

	UVerticalBox* Box = WidgetTree->ConstructWidget<UVerticalBox>();
	UOverlaySlot* BoxSlot = Root->AddChildToOverlay(Box);
	BoxSlot->SetHorizontalAlignment(HAlign_Center);
	BoxSlot->SetVerticalAlignment(VAlign_Center);

	FirstButton = WidgetTree->ConstructWidget<UAstralScreenTestButton>(UAstralScreenTestButton::StaticClass(), TEXT("FirstButton"));
	SecondButton = WidgetTree->ConstructWidget<UAstralScreenTestButton>(UAstralScreenTestButton::StaticClass(), TEXT("SecondButton"));
	PlainButton = WidgetTree->ConstructWidget<UAstralScreenTestPlainButton>(UAstralScreenTestPlainButton::StaticClass(), TEXT("PlainButton"));
	for (UCommonButtonBase* Button : TArray<UCommonButtonBase*>{ FirstButton, SecondButton, PlainButton })
	{
		Box->AddChildToVerticalBox(Button)->SetPadding(FMargin(0.f, 8.f));
	}

	Super::NativeOnInitialized();
}

UWidget* UAstralScreenTestMenu::NativeGetDesiredFocusTarget() const
{
	return FirstButton;
}
