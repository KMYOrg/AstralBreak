#include "AstralScreenStackTestWidgets.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/SizeBox.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Layout/Children.h"
#include "Widgets/SWidget.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralScreenStackTestWidgets)

bool UAstralScreenTestButton::Initialize()
{
	// WBP 가 하는 일(루트 위젯)을 대신한다 — 부모의 Initialize 가 이 루트를 안쪽 버튼으로 감싼다
	if (!WidgetTree && !HasAnyFlags(RF_ClassDefaultObject))
	{
		WidgetTree = NewObject<UWidgetTree>(this, TEXT("WidgetTree"), RF_Transient);
		USizeBox* Box = WidgetTree->ConstructWidget<USizeBox>();
		Box->SetWidthOverride(240.f);
		Box->SetHeightOverride(60.f);
		WidgetTree->RootWidget = Box;
	}
	return Super::Initialize();
}

TSharedPtr<SWidget> UAstralScreenTestButton::GetInnerSlateButton() const
{
	const UWidget* Root = WidgetTree ? WidgetTree->RootWidget.Get() : nullptr;
	const TSharedPtr<SWidget> Box = Root ? Root->GetCachedWidget() : nullptr;
	FChildren* Children = Box ? Box->GetChildren() : nullptr;
	return (Children && Children->Num() > 0) ? Children->GetChildAt(0).ToSharedPtr() : nullptr;
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
	for (UAstralScreenTestButton* Button : { FirstButton.Get(), SecondButton.Get() })
	{
		Box->AddChildToVerticalBox(Button)->SetPadding(FMargin(0.f, 8.f));
	}

	Super::NativeOnInitialized();
}

UWidget* UAstralScreenTestMenu::NativeGetDesiredFocusTarget() const
{
	return FirstButton;
}
